"""AWS Lambda handler — triggered by S3 PutObject events.

When an image is uploaded to the input S3 bucket, this Lambda function:
1. Downloads the original image
2. Resizes it to all preset sizes (thumbnail, medium, large)
3. Uploads processed variants to the output bucket
4. Logs structured metrics to CloudWatch
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from io import BytesIO
from urllib.parse import unquote_plus

import boto3
from PIL import Image

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration ────────────────────────────────────────────

PRESET_SIZES = {
    "thumbnail": (100, 100),
    "medium": (300, 300),
    "large": (800, 800),
}

FORMAT_MAP = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
}

CONTENT_TYPE_MAP = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

JPEG_QUALITY = 85
WEBP_QUALITY = 80

# Will be set from environment in production, fallback for local testing
import os

OUTPUT_BUCKET = os.environ.get(
    "IMAGE_RESIZER_S3_OUTPUT_BUCKET",
    "serverless-image-resizer-buckets-output",
)
CLOUDFRONT_DOMAIN = os.environ.get("IMAGE_RESIZER_CLOUDFRONT_DOMAIN", "")

s3_client = boto3.client("s3")


# ── Lambda Handler ───────────────────────────────────────────

def handler(event, context):
    """Process S3 PutObject events and create resized variants."""
    logger.info("Received event: %s", json.dumps(event, default=str))

    results = []
    for record in event.get("Records", []):
        try:
            result = _process_record(record)
            results.append(result)
        except Exception:
            logger.exception("Failed to process record: %s", record)
            results.append({"status": "error", "record": str(record)})

    response = {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Processed {len(results)} image(s).",
            "results": results,
        }),
    }
    logger.info("Lambda response: %s", response)
    return response


def _process_record(record: dict) -> dict:
    """Download source image from S3, resize, and upload variants."""
    s3_info = record["s3"]
    source_bucket = s3_info["bucket"]["name"]
    source_key = unquote_plus(s3_info["object"]["key"])
    source_size = s3_info["object"].get("size", 0)

    logger.info(
        "Processing: bucket=%s key=%s size=%d",
        source_bucket, source_key, source_size,
    )

    start_time = time.monotonic()

    # Download original
    response = s3_client.get_object(Bucket=source_bucket, Key=source_key)
    image_bytes = response["Body"].read()

    # Parse key to extract image_id and extension
    # Expected format: uploads/{image_id}/original.{ext}
    parts = source_key.split("/")
    if len(parts) < 3:
        logger.warning("Unexpected key format: %s — skipping", source_key)
        return {"status": "skipped", "key": source_key, "reason": "unexpected key format"}

    image_id = parts[1]
    extension = parts[-1].rsplit(".", 1)[-1].lower()
    if extension == "jpeg":
        extension = "jpg"

    pil_format = FORMAT_MAP.get(extension)
    if not pil_format:
        logger.warning("Unsupported format: %s — skipping", extension)
        return {"status": "skipped", "key": source_key, "reason": f"unsupported format: {extension}"}

    # Open image
    image = Image.open(BytesIO(image_bytes))
    image.load()

    # Create variants
    variants = []
    for label, size in PRESET_SIZES.items():
        variant_info = _create_variant(image, image_id, label, size, extension, pil_format)
        variants.append(variant_info)

    processing_time = (time.monotonic() - start_time) * 1000

    logger.info(
        "Completed: image_id=%s variants=%d time=%.1fms",
        image_id, len(variants), processing_time,
    )

    return {
        "status": "success",
        "image_id": image_id,
        "variants": variants,
        "processing_time_ms": round(processing_time, 2),
    }


def _create_variant(
    source_image: Image.Image,
    image_id: str,
    label: str,
    size: tuple[int, int],
    extension: str,
    pil_format: str,
) -> dict:
    """Resize image and upload to output bucket."""
    img = source_image.copy()
    img.thumbnail(size)

    # Build save params
    save_kwargs: dict = {"optimize": True}
    if pil_format == "JPEG":
        img = img.convert("RGB")
        save_kwargs["quality"] = JPEG_QUALITY
        save_kwargs["progressive"] = True
    elif pil_format == "WEBP":
        save_kwargs["quality"] = WEBP_QUALITY

    buffer = BytesIO()
    img.save(buffer, pil_format, **save_kwargs)
    buffer.seek(0)
    body = buffer.getvalue()

    output_key = f"processed/{image_id}/{label}.{extension}"
    content_type = CONTENT_TYPE_MAP.get(pil_format, "application/octet-stream")

    s3_client.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=output_key,
        Body=body,
        ContentType=content_type,
    )

    # Generate URL
    if CLOUDFRONT_DOMAIN:
        domain = CLOUDFRONT_DOMAIN.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        url = f"{domain}/{output_key}"
    else:
        url = f"https://{OUTPUT_BUCKET}.s3.amazonaws.com/{output_key}"

    width, height = img.size
    logger.info(
        "Variant: label=%s size=%dx%d format=%s bytes=%d",
        label, width, height, pil_format, len(body),
    )

    return {
        "label": label,
        "width": width,
        "height": height,
        "format": extension,
        "url": url,
        "size_bytes": len(body),
    }
