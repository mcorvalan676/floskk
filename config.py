import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "conectatalento-dev-key")
    USE_SQLITE = os.getenv("USE_SQLITE", "1").lower() in {"1", "true", "yes", "y"}
    DEBUG = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes", "y"}
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "conectatalento")
    SQLITE_DB_PATH = os.path.join(BASE_DIR, "database", "conectatalento.db")
    APP_NAME = "ConectaTalento"
