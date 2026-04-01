"""Metadata persistence — local JSON files.

Keeps the simple JSON approach for metadata storage. The service reads/writes
ImageRecord objects to the local metadata directory.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import METADATA_DIR
from app.schemas import ImageRecord

logger = logging.getLogger(__name__)


class MetadataService:
    """Read and write image metadata as JSON files on local disk."""

    def __init__(self) -> None:
        METADATA_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, record: ImageRecord) -> None:
        path = METADATA_DIR / f"{record.image_id}.json"
        path.write_text(json.dumps(record.model_dump(mode="json"), indent=2))
        logger.info("Saved metadata for image_id=%s", record.image_id)

    def load(self, image_id: str) -> ImageRecord | None:
        path = METADATA_DIR / f"{image_id}.json"
        if not path.exists():
            return None
        return ImageRecord.model_validate_json(path.read_text())

    def exists(self, image_id: str) -> bool:
        return (METADATA_DIR / f"{image_id}.json").exists()

    def list_recent(self, limit: int = 20, offset: int = 0) -> list[ImageRecord]:
        """Return recent image records sorted by creation time (newest first)."""
        files = sorted(
            METADATA_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        records: list[ImageRecord] = []
        for path in files[offset: offset + limit]:
            try:
                records.append(ImageRecord.model_validate_json(path.read_text()))
            except Exception:
                logger.warning("Skipping corrupt metadata file: %s", path.name)
        return records

    def delete(self, image_id: str) -> bool:
        """Delete metadata for an image. Returns True if deleted."""
        path = METADATA_DIR / f"{image_id}.json"
        if path.exists():
            path.unlink()
            logger.info("Deleted metadata for image_id=%s", image_id)
            return True
        return False

    def count(self) -> int:
        return len(list(METADATA_DIR.glob("*.json")))
