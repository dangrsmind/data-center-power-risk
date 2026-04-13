from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/power_risk"
