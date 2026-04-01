"""Amazon S3 storage operations with retry and CloudFront URL generation."""

from __future__ import annotations

import logging
import time
from io import BytesIO
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

# Retry config for boto3 (exponential backoff)
_BOTO_CONFIG = BotoConfig(
    region_name=settings.aws_region,
    retries={"max_attempts": 3, "mode": "adaptive"},
)

_CONTENT_TYPE_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class S3StorageService:
    """Wrapper around boto3 S3 operations for the image resizer."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            config=_BOTO_CONFIG,
        )
        self.input_bucket = settings.s3_input_bucket
        self.output_bucket = settings.s3_output_bucket

    # ── Pre-signed upload URL ────────────────────────────────
    def generate_presigned_upload_url(
        self,
        key: str,
        content_type: str = "image/jpeg",
        expires: int | None = None,
    ) -> dict[str, Any]:
        """Generate a pre-signed PUT URL for direct browser → S3 upload."""
        expiry = expires or settings.s3_presign_expiry
        try:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.input_bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expiry,
            )
            logger.info("Generated pre-signed URL for key=%s", key)
            return {
                "upload_url": url,
                "key": key,
                "bucket": self.input_bucket,
                "expires_in": expiry,
            }
        except ClientError:
            logger.exception("Failed to generate pre-signed URL for key=%s", key)
            raise

    # ── Upload ───────────────────────────────────────────────
    def upload_file(
        self,
        bucket: str,
        key: str,
        body: bytes | BytesIO,
        content_type: str = "image/jpeg",
    ) -> str:
        """Upload bytes to an S3 bucket. Returns the object key."""
        data = body if isinstance(body, bytes) else body.getvalue()
        start = time.monotonic()
        try:
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            elapsed = time.monotonic() - start
            logger.info(
                "Uploaded %s/%s (%d bytes) in %.2fs",
                bucket, key, len(data), elapsed,
            )
            return key
        except ClientError:
            logger.exception("Failed to upload %s/%s", bucket, key)
            raise

    def upload_to_input(self, key: str, body: bytes, content_type: str = "image/jpeg") -> str:
        return self.upload_file(self.input_bucket, key, body, content_type)

    def upload_to_output(self, key: str, body: bytes, content_type: str = "image/jpeg") -> str:
        return self.upload_file(self.output_bucket, key, body, content_type)

    # ── Download ─────────────────────────────────────────────
    def download_file(self, bucket: str, key: str) -> bytes:
        """Download an object from S3 and return its bytes."""
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError:
            logger.exception("Failed to download %s/%s", bucket, key)
            raise

    def download_from_input(self, key: str) -> bytes:
        return self.download_file(self.input_bucket, key)

    # ── URL generation ───────────────────────────────────────
    def generate_public_url(self, key: str, bucket: str | None = None) -> str:
        """Return the CloudFront URL if configured, otherwise the S3 URL."""
        base = settings.get_asset_base_url()
        target_bucket = bucket or self.output_bucket
        if base and target_bucket == self.output_bucket:
            return f"{base}/{key}"
        return f"https://{target_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"

    def generate_presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        """Generate a pre-signed GET URL for temporary access to a private object."""
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )
            return url
        except ClientError:
            logger.exception("Failed to generate pre-signed GET URL for %s/%s", bucket, key)
            raise

    # ── Delete ───────────────────────────────────────────────
    def delete_file(self, bucket: str, key: str) -> None:
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
            logger.info("Deleted %s/%s", bucket, key)
        except ClientError:
            logger.exception("Failed to delete %s/%s", bucket, key)
            raise

    # ── Helpers ──────────────────────────────────────────────
    @staticmethod
    def content_type_for(extension: str) -> str:
        return _CONTENT_TYPE_MAP.get(extension.lower().lstrip("."), "application/octet-stream")
