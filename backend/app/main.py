"""FastAPI application — production-grade Serverless Image Resizer API."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import DATA_DIR, ensure_directories, settings
from app.schemas import (
    ConfirmUploadRequest,
    DeleteResponse,
    HealthResponse,
    ImageListResponse,
    PresignResponse,
    ResizeResponse,
    UploadResponse,
)
from app.services.image_service import ImageService

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("image_resizer")

# ── Boot ─────────────────────────────────────────────────────
ensure_directories()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production-grade serverless image resizing API with AWS S3, Lambda, and CloudFront support.",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files only in local mode
if not settings.is_aws_mode():
    app.mount("/assets", StaticFiles(directory=DATA_DIR), name="assets")


# ── Request middleware ───────────────────────────────────────

@app.middleware("http")
async def add_request_metadata(request: Request, call_next):
    """Add request ID and timing to every request."""
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.monotonic()

    response = await call_next(request)

    elapsed = (time.monotonic() - start) * 1000
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
    logger.info(
        "[%s] %s %s → %d (%.1fms)",
        request_id, request.method, request.url.path,
        response.status_code, elapsed,
    )
    return response


# ── Exception handler ────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("[%s] Unhandled exception: %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": request_id},
    )


# ── Helpers ──────────────────────────────────────────────────

def get_image_service(request: Request) -> ImageService:
    return ImageService(base_url=str(request.base_url).rstrip("/"))


# ── Endpoints ────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(
        version=settings.app_version,
        storage_backend=settings.storage_backend,
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
) -> UploadResponse:
    """Upload an image and generate preset size variants."""
    service = get_image_service(request)
    record = await service.create_image_record(file)
    return UploadResponse(image=record)


@app.get("/image/{image_id}", response_model=UploadResponse)
def get_image(image_id: str, request: Request) -> UploadResponse:
    """Fetch image metadata and variant URLs by image ID."""
    service = get_image_service(request)
    record = service.get_image_record(image_id)
    return UploadResponse(message="Image fetched successfully.", image=record)


@app.delete("/image/{image_id}", response_model=DeleteResponse)
def delete_image(image_id: str, request: Request) -> DeleteResponse:
    """Delete an image and all its variants."""
    service = get_image_service(request)
    service.delete_image(image_id)
    return DeleteResponse(image_id=image_id)


@app.get("/images", response_model=ImageListResponse)
def list_images(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ImageListResponse:
    """List recently uploaded images with pagination."""
    service = get_image_service(request)
    records, total = service.list_images(limit=limit, offset=offset)
    return ImageListResponse(
        images=records, total=total, limit=limit, offset=offset,
    )


@app.get("/resize", response_model=ResizeResponse)
def resize_image(
    request: Request,
    image_id: str = Query(...),
    width: int = Query(..., ge=1, le=4000),
    height: int = Query(..., ge=1, le=4000),
    output_format: str | None = Query(default=None, alias="format"),
) -> ResizeResponse:
    """Create a custom-sized variant of an existing image."""
    service = get_image_service(request)
    variant = service.create_dynamic_resize(image_id, width, height, output_format)
    return ResizeResponse(image_id=image_id, variant=variant)


@app.get("/presign", response_model=PresignResponse)
def get_presigned_url(
    request: Request,
    filename: str = Query(..., description="Original filename with extension"),
    content_type: str = Query(default="image/jpeg"),
) -> PresignResponse:
    """Get a pre-signed S3 URL for direct browser upload (S3 mode only)."""
    service = get_image_service(request)
    result = service.generate_presigned_upload(filename, content_type)
    return PresignResponse(**result)


@app.post("/confirm-upload", response_model=UploadResponse)
def confirm_upload(
    request: Request,
    body: ConfirmUploadRequest,
) -> UploadResponse:
    """Confirm a direct S3 upload and trigger resizing (S3 mode only)."""
    service = get_image_service(request)
    record = service.confirm_s3_upload(
        image_id=body.image_id,
        key=body.key,
        original_filename=body.original_filename,
        content_type=body.content_type,
    )
    return UploadResponse(image=record)
