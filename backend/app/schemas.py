"""Pydantic request / response schemas for all API endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Image data models ────────────────────────────────────────

class ImageVariant(BaseModel):
    label: str
    width: int
    height: int
    format: str
    url: str
    size_bytes: int = 0


class ImageRecord(BaseModel):
    image_id: str
    original_filename: str
    original_format: str
    created_at: datetime
    original_url: str
    variants: list[ImageVariant]
    processing_time_ms: float = 0.0
    is_ai_generated: bool | None = None
    ai_confidence: float | None = None


# ── Responses ────────────────────────────────────────────────

class UploadResponse(BaseModel):
    message: str = "Image uploaded and resized successfully."
    image: ImageRecord


class ResizeResponse(BaseModel):
    image_id: str
    variant: ImageVariant


class PresignResponse(BaseModel):
    upload_url: str
    key: str
    bucket: str
    expires_in: int
    image_id: str


class ConfirmUploadRequest(BaseModel):
    image_id: str
    key: str
    original_filename: str
    content_type: str = "image/jpeg"


class ImageListResponse(BaseModel):
    images: list[ImageRecord]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    version: str = Field(default="1.0.0")
    storage_backend: str = Field(default="local")


class DeleteResponse(BaseModel):
    message: str = "Image deleted successfully."
    image_id: str


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None
