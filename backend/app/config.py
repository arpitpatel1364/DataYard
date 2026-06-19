"""
Cactus Intelligence Suite (CIS) - Configuration
Central settings object. All values can be overridden via environment
variables or a .env file placed next to this package.
"""
from pydantic_settings import BaseSettings
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    APP_NAME: str = "Cactus Intelligence Suite"
    APP_BRAND: str = "Cactus Creatives"
    APP_VERSION: str = "1.0.0"
    BRAND_COLOR: str = "#72ab52"

    # Security
    SECRET_KEY: str = "CHANGE_ME_CIS_SUPER_SECRET_KEY_72ab52"
    REFRESH_SECRET_KEY: str = "CHANGE_ME_CIS_REFRESH_SECRET_KEY_72ab52"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database (SQLite, file based, zero external services)
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'storage' / 'cis.db'}"

    # Storage
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    DATASET_DIR: Path = BASE_DIR / "storage" / "datasets"
    REPORT_DIR: Path = BASE_DIR / "storage" / "reports"
    MODEL_DIR: Path = BASE_DIR / "storage" / "models"

    # Monitoring
    DEFAULT_SCAN_EVERY_MINUTES: int = 30

    # Roboflow (optional, only used if user supplies their own API key per-request)
    ROBOFLOW_API_BASE: str = "https://api.roboflow.com"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"
        arbitrary_types_allowed = True


settings = Settings()

# Ensure storage directories exist
for d in [settings.STORAGE_DIR, settings.UPLOAD_DIR, settings.DATASET_DIR,
          settings.REPORT_DIR, settings.MODEL_DIR]:
    d.mkdir(parents=True, exist_ok=True)
