"""Application configuration with dual-mode support (local / AWS)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
METADATA_DIR = DATA_DIR / "metadata"


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────
    app_name: str = "Serverless Image Resizer API"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── Image constraints ────────────────────────────────────
    max_file_size_mb: int = 5
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")

    # ── CORS ─────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:5173"]

    # ── Storage backend: "local" or "s3" ─────────────────────
    storage_backend: str = "local"

    # ── AWS ──────────────────────────────────────────────────
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    s3_input_bucket: str = "serverless-image-resizer-buckets-input"
    s3_output_bucket: str = "serverless-image-resizer-buckets-output"
    s3_presign_expiry: int = 300  # seconds

    cloudfront_domain: str = ""  # e.g. d1234abcdef.cloudfront.net

    # ── Model config ─────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_prefix="IMAGE_RESIZER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def is_aws_mode(self) -> bool:
        return self.storage_backend.lower() == "s3"

    def get_asset_base_url(self) -> str:
        """Return CloudFront domain for S3 mode, empty string for local."""
        if self.is_aws_mode() and self.cloudfront_domain:
            domain = self.cloudfront_domain.rstrip("/")
            if not domain.startswith("http"):
                domain = f"https://{domain}"
            return domain
        return ""


settings = Settings()


def ensure_directories() -> None:
    """Create local data directories (only relevant in local mode)."""
    if not settings.is_aws_mode():
        for directory in (DATA_DIR, UPLOADS_DIR, PROCESSED_DIR, METADATA_DIR):
            directory.mkdir(parents=True, exist_ok=True)
