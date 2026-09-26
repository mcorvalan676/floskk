import os
from pathlib import Path

IS_CLOUDFLARE_WORKER = os.getenv("CLOUDFLARE_WORKERS", "").lower() in {
    "1", "true", "yes",
}

if not IS_CLOUDFLARE_WORKER:
    from dotenv import load_dotenv

    load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
USE_SQLITE = os.getenv("USE_SQLITE", "1").lower() in {"1", "true", "yes", "y"}
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY and not IS_CLOUDFLARE_WORKER and not USE_SQLITE:
    raise RuntimeError(
        "SECRET_KEY must be configured when SQLite is disabled."
    )

if not SECRET_KEY and USE_SQLITE and not IS_CLOUDFLARE_WORKER:
    SECRET_KEY = "conectatalento-dev-key"


class Config:
    SECRET_KEY = SECRET_KEY
    USE_SQLITE = USE_SQLITE
    CLOUDFLARE_WORKERS = IS_CLOUDFLARE_WORKER
    DEBUG = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes", "y"}
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "conectatalento")
    SQLITE_DB_PATH = os.path.join(BASE_DIR, "database", "conectatalento.db")
    PHP_SERVICE_URL = os.getenv(
        "PHP_SERVICE_URL", "http://127.0.0.1:8000/servicio.php"
    )
    APP_NAME = "ConectaTalento"
