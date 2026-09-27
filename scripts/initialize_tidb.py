import getpass
import ssl
from pathlib import Path

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_NAME = "conectatalento"


def main():
    host = input("TiDB host: ").strip()
    username = input("TiDB username: ").strip()
    password = getpass.getpass(
        "Contraseña TiDB (no se mostrará; escribe y presiona Enter): "
    )
    if not host or not username or not password:
        raise ValueError("TiDB host, username, and password are required.")

    connection = pymysql.connect(
        host=host,
        port=4000,
        user=username,
        password=password,
        charset="utf8mb4",
        ssl=ssl.create_default_context(),
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DATABASE_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.select_db(DATABASE_NAME)
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            if cursor.fetchall():
                raise RuntimeError(
                    f"Database '{DATABASE_NAME}' already contains tables; "
                    "refusing to initialize over existing data."
                )

        schema_path = PROJECT_ROOT / "database" / "schema.sql"
        statements = schema_path.read_text(encoding="utf-8").split(";")
        with connection.cursor() as cursor:
            for statement in statements:
                statement = statement.strip()
                if not statement:
                    continue
                if statement.upper().startswith(("CREATE DATABASE ", "USE ")):
                    continue
                cursor.execute(statement)
        print(f"Initialized database schema in '{DATABASE_NAME}'.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
