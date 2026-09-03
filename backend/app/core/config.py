import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/power_risk"

DEFAULT_BACKEND_CORS_ORIGINS = (
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5001",
    "http://127.0.0.1:5001",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
)


def get_backend_cors_origins() -> list[str]:
    raw_origins = os.getenv("BACKEND_CORS_ORIGINS") or os.getenv("CORS_ORIGINS")
    if not raw_origins:
        return list(DEFAULT_BACKEND_CORS_ORIGINS)

    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
