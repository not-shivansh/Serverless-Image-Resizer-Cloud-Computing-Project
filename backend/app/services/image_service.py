"""Core image processing service — dual-mode (local filesystem / AWS S3)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.config import PROCESSED_DIR, UPLOADS_DIR, settings
from app.schemas import ImageRecord, ImageVariant
from app.services.metadata_service import MetadataService
from app.services.ai_detection_service import AIDetectionService

logger = logging.getLogger(__name__)

PRESET_SIZES: dict[str, tuple[int, int]] = {
    "thumbnail": (100, 100),
    "medium": (300, 300),
    "large": (800, 800),
}

FORMAT_MAP: dict[str, str] = {
    "jpg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
}

# JPEG quality for compression optimization
JPEG_QUALITY = 95
WEBP_QUALITY = 95


class ImageService:
    """Handles image upload, resize, and storage for both local and S3 modes."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.metadata = MetadataService()
        self._s3: "S3StorageService | None" = None

        if settings.is_aws_mode():
            from app.services.s3_service import S3StorageService
            self._s3 = S3StorageService()

    # ── Upload + process ─────────────────────────────────────

    async def create_image_record(self, file: UploadFile) -> ImageRecord:
        self._validate_extension(file.filename or "")
        file_bytes = await file.read()
        self._validate_size(file_bytes)

        image = self._open_image(file_bytes)
        image_id = uuid4().hex
        original_extension = self._normalized_extension(file.filename or "")
        start_time = time.monotonic()

        # Save original
        original_url = self._store_original(image_id, original_extension, file_bytes)

        # Generate preset variants
        variants = [
            self._save_variant(
                source_image=image,
                image_id=image_id,
                label=label,
                size=size,
                output_format=original_extension,
            )
            for label, size in PRESET_SIZES.items()
        ]

        processing_time = (time.monotonic() - start_time) * 1000
        
        # Determine if AI generated
        ai_result = AIDetectionService.analyze_image(file_bytes, file.filename or "")

        record = ImageRecord(
            image_id=image_id,
            original_filename=file.filename or f"{image_id}.{original_extension}",
            original_format=original_extension,
            created_at=datetime.now(UTC),
            original_url=original_url,
            variants=variants,
            processing_time_ms=round(processing_time, 2),
            is_ai_generated=ai_result["is_ai_generated"],
            ai_confidence=ai_result["ai_confidence"],
        )
        self.metadata.save(record)
        logger.info(
            "Created image record id=%s variants=%d time=%.1fms",
            image_id, len(variants), processing_time,
        )
        return record

    # ── Lookup ───────────────────────────────────────────────

    def get_image_record(self, image_id: str) -> ImageRecord:
        record = self.metadata.load(image_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found.",
            )
        return record

    def list_images(self, limit: int = 20, offset: int = 0) -> tuple[list[ImageRecord], int]:
        records = self.metadata.list_recent(limit=limit, offset=offset)
        total = self.metadata.count()
        return records, total

    def delete_image(self, image_id: str) -> None:
        """Delete an image, all its variants, and metadata."""
        # Verify it exists first
        record = self.metadata.load(image_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found.",
            )

        # Clean up files
        if settings.is_aws_mode() and self._s3:
            # Delete from S3 input bucket
            try:
                key = f"uploads/{image_id}/original.{record.original_format}"
                self._s3.delete_file(self._s3.input_bucket, key)
            except Exception:
                logger.warning("Failed to delete original from S3 for %s", image_id)

            # Delete variants from S3 output bucket
            for variant in record.variants:
                try:
                    key = f"processed/{image_id}/{variant.label}.{variant.format}"
                    self._s3.delete_file(self._s3.output_bucket, key)
                except Exception:
                    logger.warning("Failed to delete variant %s from S3", variant.label)
        else:
            # Delete local files
            import shutil
            upload_dir = UPLOADS_DIR / image_id
            processed_dir = PROCESSED_DIR / image_id
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
            if processed_dir.exists():
                shutil.rmtree(processed_dir)

        # Delete metadata
        self.metadata.delete(image_id)
        logger.info("Deleted image id=%s", image_id)

    def create_dynamic_resize(
        self,
        image_id: str,
        width: int,
        height: int,
        output_format: str | None,
    ) -> ImageVariant:
        record = self.get_image_record(image_id)
        original_extension = record.original_format
        target_extension = self._normalized_output_format(output_format or original_extension)

        image = self._load_original_image(image_id, original_extension)

        variant = self._save_variant(
            source_image=image,
            image_id=image_id,
            label=f"custom-{width}x{height}",
            size=(width, height),
            output_format=target_extension,
        )
        image.close()

        # Update metadata with new variant
        variants = [item for item in record.variants if item.label != variant.label]
        variants.append(variant)
        updated = record.model_copy(update={"variants": variants})
        self.metadata.save(updated)
        return variant

    # ── Pre-signed URL (S3 mode only) ────────────────────────

    def generate_presigned_upload(
        self,
        filename: str,
        content_type: str,
    ) -> dict:
        if not self._s3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pre-signed uploads are only available in S3 mode.",
            )
        self._validate_extension(filename)
        image_id = uuid4().hex
        extension = self._normalized_extension(filename)
        key = f"uploads/{image_id}/original.{extension}"

        result = self._s3.generate_presigned_upload_url(key, content_type)
        result["image_id"] = image_id
        return result

    def confirm_s3_upload(
        self,
        image_id: str,
        key: str,
        original_filename: str,
        content_type: str,
    ) -> ImageRecord:
        """After client uploads to S3, process the image."""
        if not self._s3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirm upload is only available in S3 mode.",
            )

        file_bytes = self._s3.download_from_input(key)
        self._validate_size(file_bytes)
        image = self._open_image(file_bytes)

        extension = self._normalized_extension(original_filename)
        start_time = time.monotonic()

        variants = [
            self._save_variant(
                source_image=image,
                image_id=image_id,
                label=label,
                size=size,
                output_format=extension,
            )
            for label, size in PRESET_SIZES.items()
        ]

        processing_time = (time.monotonic() - start_time) * 1000
        original_url = self._s3.generate_public_url(key, bucket=self._s3.input_bucket)
        
        # Determine if AI generated
        ai_result = AIDetectionService.analyze_image(file_bytes, original_filename)

        record = ImageRecord(
            image_id=image_id,
            original_filename=original_filename,
            original_format=extension,
            created_at=datetime.now(UTC),
            original_url=original_url,
            variants=variants,
            processing_time_ms=round(processing_time, 2),
            is_ai_generated=ai_result["is_ai_generated"],
            ai_confidence=ai_result["ai_confidence"],
        )
        self.metadata.save(record)
        return record

    # ── Internal helpers ─────────────────────────────────────

    def _store_original(self, image_id: str, extension: str, file_bytes: bytes) -> str:
        if settings.is_aws_mode() and self._s3:
            key = f"uploads/{image_id}/original.{extension}"
            content_type = self._s3.content_type_for(extension)
            self._s3.upload_to_input(key, file_bytes, content_type)
            return self._s3.generate_public_url(key, bucket=self._s3.input_bucket)
        else:
            upload_dir = UPLOADS_DIR / image_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            original_path = upload_dir / f"original.{extension}"
            original_path.write_bytes(file_bytes)
            return self._to_asset_url(original_path)

    def _load_original_image(self, image_id: str, extension: str) -> Image.Image:
        if settings.is_aws_mode() and self._s3:
            key = f"uploads/{image_id}/original.{extension}"
            file_bytes = self._s3.download_from_input(key)
            image = Image.open(BytesIO(file_bytes))
            image.load()
            return image
        else:
            original_path = UPLOADS_DIR / image_id / f"original.{extension}"
            if not original_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Original image file is missing.",
                )
            return Image.open(original_path)

    def _save_variant(
        self,
        source_image: Image.Image,
        image_id: str,
        label: str,
        size: tuple[int, int],
        output_format: str,
    ) -> ImageVariant:
        image = source_image.copy()
        image.thumbnail(size, resample=Image.Resampling.LANCZOS)

        final_width, final_height = image.size
        suffix = self._normalized_output_format(output_format)
        pil_format = FORMAT_MAP[suffix]

        # Apply compression optimization
        save_kwargs: dict = {"optimize": True}
        if pil_format == "JPEG":
            image = image.convert("RGB")
            save_kwargs["quality"] = JPEG_QUALITY
            save_kwargs["progressive"] = True
        elif pil_format == "WEBP":
            save_kwargs["quality"] = WEBP_QUALITY

        if settings.is_aws_mode() and self._s3:
            buffer = BytesIO()
            image.save(buffer, pil_format, **save_kwargs)
            buffer.seek(0)
            key = f"processed/{image_id}/{label}.{suffix}"
            content_type = self._s3.content_type_for(suffix)
            self._s3.upload_to_output(key, buffer.getvalue(), content_type)
            url = self._s3.generate_public_url(key)
            size_bytes = buffer.tell()
        else:
            output_path = PROCESSED_DIR / image_id / f"{label}.{suffix}"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, pil_format, **save_kwargs)
            url = self._to_asset_url(output_path)
            size_bytes = output_path.stat().st_size

        return ImageVariant(
            label=label,
            width=final_width,
            height=final_height,
            format=suffix,
            url=url,
            size_bytes=size_bytes,
        )

    # ── Validation ───────────────────────────────────────────

    def _validate_extension(self, filename: str) -> None:
        extension = Path(filename).suffix.lower()
        if extension not in settings.allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type. Allowed: {', '.join(settings.allowed_extensions)}",
            )

    def _validate_size(self, file_bytes: bytes) -> None:
        size_limit = settings.max_file_size_mb * 1024 * 1024
        if len(file_bytes) > size_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds {settings.max_file_size_mb}MB limit.",
            )

    def _open_image(self, file_bytes: bytes) -> Image.Image:
        try:
            image = Image.open(BytesIO(file_bytes))
            image.load()
            return image
        except UnidentifiedImageError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or corrupted image file.",
            ) from exc

    def _to_asset_url(self, path: Path) -> str:
        relative_path = path.relative_to(UPLOADS_DIR.parent).as_posix()
        return f"{self.base_url}/assets/{relative_path}"

    def _normalized_extension(self, filename: str) -> str:
        return self._canonical_extension(Path(filename).suffix.lower().lstrip("."))

    def _normalized_output_format(self, value: str) -> str:
        normalized = self._canonical_extension(value.lower().replace(".", ""))
        if normalized not in FORMAT_MAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported output format. Use jpg, png, or webp.",
            )
        return normalized

    def _canonical_extension(self, value: str) -> str:
        return "jpg" if value == "jpeg" else value
