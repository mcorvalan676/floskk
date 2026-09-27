import os
from pathlib import Path

IS_CLOUDFLARE_WORKER = os.getenv("CLOUDFLARE_WORKERS", "").lower() in {
    "1", "true", "yes",
}

if not IS_CLOUDFLARE_WORKER:
    from dotenv import load_dotenv

    load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
IS_RENDER = bool(os.getenv("RENDER"))
USE_SQLITE = os.getenv(
    "USE_SQLITE", "0" if IS_RENDER else "1"
).lower() in {"1", "true", "yes", "y"}
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY and not IS_CLOUDFLARE_WORKER and (not USE_SQLITE or IS_RENDER):
    raise RuntimeError(
        "SECRET_KEY must be configured outside local SQLite development."
    )

if not SECRET_KEY and USE_SQLITE and not IS_CLOUDFLARE_WORKER:
    SECRET_KEY = "conectatalento-dev-key"

if IS_RENDER:
    required_database_settings = {
        "MYSQL_HOST": os.getenv("MYSQL_HOST"),
        "MYSQL_USER": os.getenv("MYSQL_USER"),
        "MYSQL_PASSWORD": os.getenv("MYSQL_PASSWORD"),
    }
    missing_database_settings = [
        name for name, value in required_database_settings.items() if not value
    ]
    if missing_database_settings:
        raise RuntimeError(
            "Required Render environment variables are missing: "
            + ", ".join(missing_database_settings)
        )
    if os.getenv("CV_STORAGE", "").lower() != "r2":
        raise RuntimeError("CV_STORAGE=r2 is required for Render deployments.")
    required_r2_settings = {
        "R2_ACCOUNT_ID": os.getenv("R2_ACCOUNT_ID"),
        "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID"),
        "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY"),
        "R2_BUCKET": os.getenv("R2_BUCKET"),
    }
    missing_r2_settings = [
        name for name, value in required_r2_settings.items() if not value
    ]
    if missing_r2_settings:
        raise RuntimeError(
            "Required Render environment variables are missing: "
            + ", ".join(missing_r2_settings)
        )


class Config:
    SECRET_KEY = SECRET_KEY
    USE_SQLITE = USE_SQLITE
    CLOUDFLARE_WORKERS = IS_CLOUDFLARE_WORKER
    DEBUG = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes", "y"}
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "conectatalento")
    MYSQL_SSL_CA = os.getenv("MYSQL_SSL_CA") or None
    CV_STORAGE = os.getenv("CV_STORAGE", "local").lower()
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    R2_BUCKET = os.getenv("R2_BUCKET")
    SQLITE_DB_PATH = os.path.join(BASE_DIR, "database", "conectatalento.db")
    PHP_SERVICE_URL = os.getenv(
        "PHP_SERVICE_URL", "http://127.0.0.1:8000/servicio.php"
    )
    APP_NAME = "ConectaTalento"
