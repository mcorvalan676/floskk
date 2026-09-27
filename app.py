import uuid
from datetime import date, time
from io import BytesIO
from pathlib import Path

from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
if not Config.CLOUDFLARE_WORKERS:
    import sqlite3
    from urllib.error import URLError
    from urllib.request import urlopen

from models.curriculum import Curriculum
from models.entrevista import Entrevista
from models.notificacion import Notificacion
from models.postulacion import Postulacion
from models.proceso_seleccion import ProcesoSeleccion
from services.compatibilidad import calcular_compatibilidad

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

BASE_DIR = Path(__file__).resolve().parent
CV_UPLOAD_DIR = BASE_DIR / "uploads" / "cv"


class MySQLCursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, *args, **kwargs):
        self._cursor.execute(*args, **kwargs)
        return self

    def executemany(self, *args, **kwargs):
        self._cursor.executemany(*args, **kwargs)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


class MySQLConnectionAdapter:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        if Config.CLOUDFLARE_WORKERS:
            import pymysql

            return MySQLCursorAdapter(
                self._connection.cursor(pymysql.cursors.DictCursor)
            )

        from mysql.connector.cursor import MySQLCursorDict

        return MySQLCursorAdapter(self._connection.cursor(cursor_class=MySQLCursorDict))

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def get_db():
    if Config.CLOUDFLARE_WORKERS:
        from cloudflare_runtime import connect_hyperdrive

        return MySQLConnectionAdapter(connect_hyperdrive(request.environ["workers.env"]))

    if Config.USE_SQLITE:
        Path(Config.SQLITE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(Config.SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    import mysql.connector

    connection = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DATABASE,
        ssl_ca=Config.MYSQL_SSL_CA,
        ssl_verify_cert=True,
        ssl_verify_identity=True,
    )
    return MySQLConnectionAdapter(connection)


def save_cv_file(key, contents):
    if Config.CLOUDFLARE_WORKERS:
        from cloudflare_runtime import save_cv_object

        save_cv_object(request.environ["workers.env"], key, contents)
    elif Config.CV_STORAGE == "r2":
        from r2_storage import save_cv_object

        save_cv_object(key, contents)
    else:
        CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (CV_UPLOAD_DIR / Path(key).name).write_bytes(contents)


def load_cv_file(key):
    if Config.CLOUDFLARE_WORKERS:
        from cloudflare_runtime import load_cv_object

        return load_cv_object(request.environ["workers.env"], key)
    if Config.CV_STORAGE == "r2":
        from r2_storage import load_cv_object

        return load_cv_object(key)
    cv_path = CV_UPLOAD_DIR / Path(key).name
    if not cv_path.is_file():
        abort(404)
    return cv_path.read_bytes()


def guardar_notificacion(cursor, usuario_id, mensaje):
    notificacion = Notificacion(usuario_id, mensaje)
    placeholder = "?" if Config.USE_SQLITE else "%s"
    cursor.execute(
        f"INSERT INTO notificaciones (usuario_id, mensaje, leida) VALUES ({placeholder}, {placeholder}, 0)",
        (notificacion.usuario_id, notificacion.mensaje),
    )


def sincronizar_habilidades(cursor, postulante_id, texto_habilidades):
    placeholder = "?" if Config.USE_SQLITE else "%s"
    insert_skill = (
        "INSERT OR IGNORE INTO habilidades (nombre) VALUES (?)"
        if Config.USE_SQLITE
        else "INSERT IGNORE INTO habilidades (nombre) VALUES (%s)"
    )
    cursor.execute(
        f"DELETE FROM postulante_habilidades WHERE postulante_id = {placeholder}",
        (postulante_id,),
    )
    names = list(dict.fromkeys(
        skill.strip() for skill in texto_habilidades.split(",") if skill.strip()
    ))
    for name in names:
        cursor.execute(insert_skill, (name,))
        row = cursor.execute(
            f"SELECT id FROM habilidades WHERE nombre = {placeholder}",
            (name,),
        ).fetchone()
        cursor.execute(
            f"INSERT INTO postulante_habilidades (postulante_id, habilidad_id) VALUES ({placeholder}, {placeholder})",
            (postulante_id, row["id"]),
        )


def migrate_sqlite_schema():
    conn = get_db()
    cur = conn.cursor()

    if not Config.USE_SQLITE:
        conn.close()
        return

    existing_columns = {
        row[1]
        for row in cur.execute("PRAGMA table_info(postulantes)").fetchall()
    }

    for column_name, column_sql in {
        "telefono": "TEXT",
        "ciudad": "TEXT",
        "region": "TEXT",
        "descripcion": "TEXT",
        "objetivo_profesional": "TEXT",
        "habilidades": "TEXT DEFAULT ''",
        "experiencia": "TEXT",
        "educacion": "TEXT",
    }.items():
        if column_name not in existing_columns:
            cur.execute(f"ALTER TABLE postulantes ADD COLUMN {column_name} {column_sql}")

    if Config.USE_SQLITE:
        offer_columns = {
            row[1] for row in cur.execute("PRAGMA table_info(ofertas)").fetchall()
        }
        for column_name in ("experiencia_requerida", "educacion_requerida"):
            if column_name not in offer_columns:
                cur.execute(f"ALTER TABLE ofertas ADD COLUMN {column_name} TEXT")

    tables = {
        "entrevistas": """
            CREATE TABLE IF NOT EXISTS entrevistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                postulacion_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                modalidad TEXT NOT NULL DEFAULT 'ONLINE',
                lugar TEXT,
                observaciones TEXT,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id)
            )
        """,
        "notificaciones": """
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                mensaje TEXT NOT NULL,
                leida INTEGER DEFAULT 0,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """,
    }

    for table_name, ddl in tables.items():
        cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if cur.fetchone() is None:
            cur.execute(ddl)

    conn.commit()
    cur.close()
    conn.close()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    if Config.USE_SQLITE:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                apellido TEXT NOT NULL,
                correo TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                activo INTEGER DEFAULT 1,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS postulantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL UNIQUE,
                telefono TEXT,
                ciudad TEXT,
                region TEXT,
                descripcion TEXT,
                objetivo_profesional TEXT,
                habilidades TEXT DEFAULT '',
                experiencia TEXT,
                educacion TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL UNIQUE,
                nombre_empresa TEXT NOT NULL,
                descripcion TEXT,
                sector TEXT,
                ubicacion TEXT,
                sitio_web TEXT,
                telefono TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ofertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                experiencia_requerida TEXT,
                educacion_requerida TEXT,
                requisitos TEXT,
                habilidades TEXT,
                ubicacion TEXT,
                tipo_contrato TEXT,
                jornada TEXT,
                rango_salarial TEXT,
                fecha_publicacion TEXT DEFAULT CURRENT_DATE,
                fecha_cierre TEXT,
                estado TEXT DEFAULT 'ACTIVA',
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS postulaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                oferta_id INTEGER NOT NULL,
                postulante_id INTEGER NOT NULL,
                fecha_postulacion TEXT DEFAULT CURRENT_TIMESTAMP,
                estado TEXT DEFAULT 'POSTULADO',
                observacion TEXT,
                UNIQUE(oferta_id, postulante_id),
                FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE CASCADE,
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entrevistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                postulacion_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                modalidad TEXT NOT NULL DEFAULT 'ONLINE',
                lugar TEXT,
                observaciones TEXT,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                mensaje TEXT NOT NULL,
                leida INTEGER DEFAULT 0,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS curriculums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                postulante_id INTEGER NOT NULL UNIQUE,
                archivo TEXT NOT NULL,
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                postulante_id INTEGER NOT NULL UNIQUE,
                url TEXT NOT NULL,
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seguimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                postulacion_id INTEGER NOT NULL,
                estado TEXT NOT NULL,
                observacion TEXT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS administradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL UNIQUE,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS habilidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS postulante_habilidades (
                postulante_id INTEGER NOT NULL,
                habilidad_id INTEGER NOT NULL,
                PRIMARY KEY (postulante_id, habilidad_id),
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE,
                FOREIGN KEY (habilidad_id) REFERENCES habilidades(id) ON DELETE CASCADE
            )
            """
        )
        cur.executemany(
            "INSERT OR IGNORE INTO habilidades (nombre) VALUES (?)",
            [(name,) for name in ("Python", "Flask", "MySQL", "JavaScript", "HTML", "CSS")],
        )
    else:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                apellido VARCHAR(100) NOT NULL,
                correo VARCHAR(150) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                rol ENUM('POSTULANTE','EMPRESA','ADMIN') NOT NULL,
                activo BOOLEAN DEFAULT TRUE,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS postulantes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL UNIQUE,
                telefono VARCHAR(30),
                ciudad VARCHAR(100),
                region VARCHAR(100),
                descripcion TEXT,
                objetivo_profesional TEXT,
                habilidades TEXT,
                experiencia TEXT,
                educacion TEXT,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL UNIQUE,
                nombre_empresa VARCHAR(150) NOT NULL,
                descripcion TEXT,
                sector VARCHAR(100),
                ubicacion VARCHAR(150),
                sitio_web VARCHAR(255),
                telefono VARCHAR(30),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ofertas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                empresa_id INT NOT NULL,
                titulo VARCHAR(150) NOT NULL,
                descripcion TEXT NOT NULL,
                experiencia_requerida TEXT,
                educacion_requerida TEXT,
                requisitos TEXT,
                habilidades TEXT,
                ubicacion VARCHAR(150),
                tipo_contrato VARCHAR(80),
                jornada VARCHAR(80),
                rango_salarial VARCHAR(100),
                fecha_publicacion DATE,
                fecha_cierre DATE,
                estado ENUM('ACTIVA','PAUSADA','CERRADA') DEFAULT 'ACTIVA',
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS postulaciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                oferta_id INT NOT NULL,
                postulante_id INT NOT NULL,
                fecha_postulacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                estado ENUM('POSTULADO','REVISION','PRESELECCIONADO','ENTREVISTA','SELECCIONADO','RECHAZADO','FINALIZADO') DEFAULT 'POSTULADO',
                observacion TEXT,
                UNIQUE KEY postulacion_unica (oferta_id, postulante_id),
                FOREIGN KEY (oferta_id) REFERENCES ofertas(id),
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entrevistas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                postulacion_id INT NOT NULL,
                fecha DATE NOT NULL,
                hora TIME NOT NULL,
                modalidad ENUM('PRESENCIAL','ONLINE','TELEFONICA') NOT NULL DEFAULT 'ONLINE',
                lugar VARCHAR(255),
                observaciones TEXT,
                estado ENUM('PENDIENTE','REALIZADA','CANCELADA') DEFAULT 'PENDIENTE',
                FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL,
                mensaje VARCHAR(500) NOT NULL,
                leida BOOLEAN DEFAULT FALSE,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS curriculums (
                id INT AUTO_INCREMENT PRIMARY KEY,
                postulante_id INT NOT NULL UNIQUE,
                archivo VARCHAR(255) NOT NULL,
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                postulante_id INT NOT NULL UNIQUE,
                url VARCHAR(500) NOT NULL,
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seguimiento (
                id INT AUTO_INCREMENT PRIMARY KEY,
                postulacion_id INT NOT NULL,
                estado VARCHAR(50) NOT NULL,
                observacion TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (postulacion_id) REFERENCES postulaciones(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS administradores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL UNIQUE,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS habilidades (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS postulante_habilidades (
                postulante_id INT NOT NULL,
                habilidad_id INT NOT NULL,
                PRIMARY KEY (postulante_id, habilidad_id),
                FOREIGN KEY (postulante_id) REFERENCES postulantes(id) ON DELETE CASCADE,
                FOREIGN KEY (habilidad_id) REFERENCES habilidades(id) ON DELETE CASCADE
            )
            """
        )
        cur.executemany(
            "INSERT IGNORE INTO habilidades (nombre) VALUES (%s)",
            [(name,) for name in ("Python", "Flask", "MySQL", "JavaScript", "HTML", "CSS")],
        )

    conn.commit()
    cur.close()
    conn.close()

    if Config.USE_SQLITE:
        migrate_sqlite_schema()


@app.cli.command("create-admin")
def create_admin_command():
    from getpass import getpass

    nombre = input("Nombre: ").strip()
    apellido = input("Apellido: ").strip()
    correo = input("Correo: ").strip()
    password = getpass("Contraseña (mínimo 12 caracteres): ")
    confirmation = getpass("Confirma la contraseña: ")

    if not nombre or not apellido or not correo or len(password) < 12:
        raise SystemExit("Completa todos los campos y usa una contraseña de 12 caracteres como mínimo.")
    if password != confirmation:
        raise SystemExit("Las contraseñas no coinciden.")

    conn = get_db()
    cur = conn.cursor()
    placeholder = "?" if Config.USE_SQLITE else "%s"
    try:
        existing = cur.execute(
            f"SELECT id FROM usuarios WHERE correo = {placeholder}", (correo,)
        ).fetchone()
        if existing:
            raise SystemExit("Ya existe una cuenta con ese correo.")
        cur.execute(
            f"INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, 'ADMIN', 1)",
            (nombre, apellido, correo, generate_password_hash(password)),
        )
        cur.execute(
            f"INSERT INTO administradores (usuario_id) VALUES ({placeholder})",
            (cur.lastrowid,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print(f"Cuenta de administración creada para {correo}.")


def get_user_by_email(correo):
    conn = get_db()
    cur = conn.cursor()
    if Config.USE_SQLITE:
        row = cur.execute("SELECT * FROM usuarios WHERE correo = ? AND activo = 1", (correo,)).fetchone()
    else:
        row = cur.execute("SELECT * FROM usuarios WHERE correo = %s AND activo = 1", (correo,)).fetchone()
    conn.close()
    return dict(row) if row is not None else None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def health_check():
    return {"status": "ok"}


@app.route("/static/<path:filename>", endpoint="static")
def static_assets(filename):
    if Config.CLOUDFLARE_WORKERS:
        from cloudflare_runtime import get_worker_asset

        asset = get_worker_asset(request.environ["workers.env"], f"static/{filename}")
        return Response(
            asset.body,
            status=asset.status,
            headers=asset.headers,
        )
    return send_from_directory(BASE_DIR / "static", filename)


@app.route("/api/php/sectores")
def php_sector_proxy():
    if Config.CLOUDFLARE_WORKERS:
        from cloudflare_runtime import fetch_php_service

        payload, status = fetch_php_service(request.environ["workers.env"])
        return jsonify(payload), status

    try:
        with urlopen(Config.PHP_SERVICE_URL, timeout=3) as response:
            payload = response.read().decode("utf-8")
            return Response(payload, status=response.status, content_type="application/json; charset=utf-8")
    except (URLError, TimeoutError, OSError):
        return jsonify(
            success=False,
            message="El servicio PHP/MySQL no está disponible.",
        ), 503


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        apellido = request.form["apellido"].strip()
        correo = request.form["correo"].strip()
        password = request.form["password"]
        rol = request.form["rol"]

        if not nombre or not apellido or not correo or len(password) < 6:
            flash("Completa todos los campos y usa una contraseña con al menos 6 caracteres.", "error")
            return render_template("register.html")

        if rol not in ("POSTULANTE", "EMPRESA"):
            flash("Rol no válido.", "error")
            return render_template("register.html")

        existing = get_user_by_email(correo)
        if existing:
            flash("El correo ya se encuentra registrado.", "error")
            return render_template("register.html")

        conn = get_db()
        cur = conn.cursor()
        try:
            if Config.USE_SQLITE:
                cur.execute(
                    "INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    (nombre, apellido, correo, generate_password_hash(password), rol),
                )
            else:
                cur.execute(
                    "INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (%s, %s, %s, %s, %s, TRUE)",
                    (nombre, apellido, correo, generate_password_hash(password), rol),
                )

            user_id = cur.lastrowid
            if rol == "POSTULANTE":
                if Config.USE_SQLITE:
                    cur.execute(
                        "INSERT INTO postulantes (usuario_id, ciudad, region, habilidades) VALUES (?, ?, ?, ?)",
                        (user_id, "Sin información", "Sin información", ""),
                    )
                else:
                    cur.execute(
                        "INSERT INTO postulantes (usuario_id, ciudad, region, habilidades) VALUES (%s, %s, %s, %s)",
                        (user_id, "Sin información", "Sin información", ""),
                    )
            else:
                if Config.USE_SQLITE:
                    cur.execute(
                        "INSERT INTO empresas (usuario_id, nombre_empresa) VALUES (?, ?)",
                        (user_id, f"{nombre} {apellido}"),
                    )
                else:
                    cur.execute(
                        "INSERT INTO empresas (usuario_id, nombre_empresa) VALUES (%s, %s)",
                        (user_id, f"{nombre} {apellido}"),
                    )
            conn.commit()
            flash("Cuenta creada correctamente.", "success")
            return redirect(url_for("login"))
        except Exception:
            conn.rollback()
            flash("No se pudo crear la cuenta. Intenta nuevamente.", "error")
        finally:
            cur.close()
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form["correo"].strip()
        password = request.form["password"]

        user = get_user_by_email(correo)
        if user and check_password_hash(user["password_hash"], password):
            session["usuario_id"] = user["id"]
            session["nombre"] = user["nombre"]
            session["rol"] = user["rol"]

            if user["rol"] == "EMPRESA":
                return redirect(url_for("empresa_dashboard"))
            if user["rol"] == "POSTULANTE":
                return redirect(url_for("postulante_dashboard"))
            if user["rol"] == "ADMIN":
                return redirect(url_for("admin_dashboard"))
            session.clear()

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/postulante/dashboard")
def postulante_dashboard():
    if session.get("rol") != "POSTULANTE":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")
    postulante = cur.execute(
        "SELECT * FROM postulantes WHERE usuario_id = ?",
        (user_id,),
    ).fetchone() if Config.USE_SQLITE else cur.execute(
        "SELECT * FROM postulantes WHERE usuario_id = %s",
        (user_id,),
    ).fetchone()

    postulaciones = []
    historiales = {}
    if postulante is not None:
        if Config.USE_SQLITE:
            postulaciones = cur.execute(
                """
                SELECT p.id, p.estado, o.titulo, e.nombre_empresa, p.fecha_postulacion
                FROM postulaciones p
                JOIN ofertas o ON o.id = p.oferta_id
                JOIN empresas e ON e.id = o.empresa_id
                WHERE p.postulante_id = ?
                ORDER BY p.id DESC
                """,
                (postulante["id"],),
            ).fetchall()
        else:
            postulaciones = cur.execute(
                """
                SELECT p.id, p.estado, o.titulo, e.nombre_empresa, p.fecha_postulacion
                FROM postulaciones p
                JOIN ofertas o ON o.id = p.oferta_id
                JOIN empresas e ON e.id = o.empresa_id
                WHERE p.postulante_id = %s
                ORDER BY p.id DESC
                """,
                (postulante["id"],),
            ).fetchall()
        placeholder = "?" if Config.USE_SQLITE else "%s"
        events = cur.execute(
            f"""
            SELECT s.postulacion_id, s.estado, s.observacion, s.fecha
            FROM seguimiento s
            JOIN postulaciones p ON p.id = s.postulacion_id
            WHERE p.postulante_id = {placeholder}
            ORDER BY s.fecha, s.id
            """,
            (postulante["id"],),
        ).fetchall()
        for event in events:
            historiales.setdefault(event["postulacion_id"], []).append(event)

    conn.close()
    return render_template(
        "postulante/dashboard.html",
        postulaciones=postulaciones,
        historiales=historiales,
    )


@app.route("/empresa/dashboard")
def empresa_dashboard():
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")
    empresa = cur.execute(
        "SELECT * FROM empresas WHERE usuario_id = ?",
        (user_id,),
    ).fetchone() if Config.USE_SQLITE else cur.execute(
        "SELECT * FROM empresas WHERE usuario_id = %s",
        (user_id,),
    ).fetchone()

    ofertas = []
    postulaciones = []
    entrevistas_pendientes = 0
    if empresa is not None:
        empresa_id = empresa["id"]
        if Config.USE_SQLITE:
            ofertas = cur.execute(
                "SELECT * FROM ofertas WHERE empresa_id = ? ORDER BY id DESC",
                (empresa_id,),
            ).fetchall()
            postulaciones = cur.execute(
                """
                SELECT p.id, u.nombre, u.apellido, o.titulo, p.estado, p.fecha_postulacion
                FROM postulaciones p
                JOIN postulantes po ON po.id = p.postulante_id
                JOIN usuarios u ON u.id = po.usuario_id
                JOIN ofertas o ON o.id = p.oferta_id
                WHERE o.empresa_id = ?
                ORDER BY p.id DESC
                """,
                (empresa_id,),
            ).fetchall()
        else:
            ofertas = cur.execute(
                "SELECT * FROM ofertas WHERE empresa_id = %s ORDER BY id DESC",
                (empresa_id,),
            ).fetchall()
            postulaciones = cur.execute(
                """
                SELECT p.id, u.nombre, u.apellido, o.titulo, p.estado, p.fecha_postulacion
                FROM postulaciones p
                JOIN postulantes po ON po.id = p.postulante_id
                JOIN usuarios u ON u.id = po.usuario_id
                JOIN ofertas o ON o.id = p.oferta_id
                WHERE o.empresa_id = %s
                ORDER BY p.id DESC
                """,
                (empresa_id,),
            ).fetchall()
        interviews_placeholder = "?" if Config.USE_SQLITE else "%s"
        entrevistas_pendientes = cur.execute(
            f"""
            SELECT COUNT(*) AS total FROM entrevistas i
            JOIN postulaciones p ON p.id = i.postulacion_id
            JOIN ofertas o ON o.id = p.oferta_id
            WHERE o.empresa_id = {interviews_placeholder} AND i.estado = 'PENDIENTE'
            """,
            (empresa_id,),
        ).fetchone()["total"]

    conn.close()
    return render_template(
        "empresa/dashboard.html",
        ofertas=ofertas,
        postulaciones=postulaciones,
        ofertas_activas=sum(1 for oferta in ofertas if oferta["estado"] == "ACTIVA"),
        en_revision=sum(1 for item in postulaciones if item["estado"] == "REVISION"),
        preseleccionados=sum(1 for item in postulaciones if item["estado"] == "PRESELECCIONADO"),
        entrevistas_pendientes=entrevistas_pendientes,
    )


@app.route("/postulante/perfil", methods=["GET", "POST"])
def postulante_perfil():
    if session.get("rol") != "POSTULANTE":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")

    if Config.USE_SQLITE:
        perfil = cur.execute(
            "SELECT u.nombre, u.apellido, u.correo, p.telefono, p.ciudad, p.region, p.descripcion, p.objetivo_profesional, p.habilidades, p.experiencia, p.educacion, c.archivo AS curriculum_archivo, v.url AS video_url FROM usuarios u LEFT JOIN postulantes p ON p.usuario_id = u.id LEFT JOIN curriculums c ON c.postulante_id = p.id LEFT JOIN videos v ON v.postulante_id = p.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
    else:
        perfil = cur.execute(
            "SELECT u.nombre, u.apellido, u.correo, p.telefono, p.ciudad, p.region, p.descripcion, p.objetivo_profesional, p.habilidades, p.experiencia, p.educacion, c.archivo AS curriculum_archivo, v.url AS video_url FROM usuarios u LEFT JOIN postulantes p ON p.usuario_id = u.id LEFT JOIN curriculums c ON c.postulante_id = p.id LEFT JOIN videos v ON v.postulante_id = p.id WHERE u.id = %s",
            (user_id,),
        ).fetchone()

    if request.method == "POST":
        telefono = request.form.get("telefono", "").strip()
        ciudad = request.form.get("ciudad", "").strip()
        region = request.form.get("region", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        objetivo = request.form.get("objetivo_profesional", "").strip()
        habilidades = request.form.get("habilidades", "").strip()
        experiencia = request.form.get("experiencia", "").strip()
        educacion = request.form.get("educacion", "").strip()
        video_url = request.form.get("video_url", "").strip()
        cv = request.files.get("curriculum")

        if video_url and not video_url.lower().startswith(("https://", "http://")):
            conn.close()
            flash("El enlace del video debe comenzar con http:// o https://.", "error")
            return redirect(url_for("postulante_perfil"))

        saved_cv_name = None
        if cv and cv.filename:
            original_name = secure_filename(cv.filename)
            if not Curriculum(None, original_name).es_pdf():
                conn.close()
                flash("El currículum debe estar en formato PDF.", "error")
                return redirect(url_for("postulante_perfil"))
            if cv.stream.read(5) != b"%PDF-":
                conn.close()
                flash("El archivo no parece ser un PDF válido.", "error")
                return redirect(url_for("postulante_perfil"))
            cv.stream.seek(0)
            saved_cv_name = f"{uuid.uuid4().hex}.pdf"
            cv_contents = cv.read()
            if Config.CLOUDFLARE_WORKERS or Config.CV_STORAGE == "r2":
                saved_cv_name = f"cv/{saved_cv_name}"
            save_cv_file(saved_cv_name, cv_contents)

        if Config.USE_SQLITE:
            cur.execute(
                "INSERT INTO postulantes (usuario_id, telefono, ciudad, region, descripcion, objetivo_profesional, habilidades, experiencia, educacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(usuario_id) DO UPDATE SET telefono=excluded.telefono, ciudad=excluded.ciudad, region=excluded.region, descripcion=excluded.descripcion, objetivo_profesional=excluded.objetivo_profesional, habilidades=excluded.habilidades, experiencia=excluded.experiencia, educacion=excluded.educacion",
                (user_id, telefono, ciudad, region, descripcion, objetivo, habilidades, experiencia, educacion),
            )
        else:
            cur.execute(
                "INSERT INTO postulantes (usuario_id, telefono, ciudad, region, descripcion, objetivo_profesional, habilidades, experiencia, educacion) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE telefono=VALUES(telefono), ciudad=VALUES(ciudad), region=VALUES(region), descripcion=VALUES(descripcion), objetivo_profesional=VALUES(objetivo_profesional), habilidades=VALUES(habilidades), experiencia=VALUES(experiencia), educacion=VALUES(educacion)",
                (user_id, telefono, ciudad, region, descripcion, objetivo, habilidades, experiencia, educacion),
            )

        profile_id = cur.execute(
            "SELECT id FROM postulantes WHERE usuario_id = " + ("?" if Config.USE_SQLITE else "%s"),
            (user_id,),
        ).fetchone()["id"]
        placeholder = "?" if Config.USE_SQLITE else "%s"
        sincronizar_habilidades(cur, profile_id, habilidades)
        if saved_cv_name:
            if Config.USE_SQLITE:
                cur.execute(
                    "INSERT INTO curriculums (postulante_id, archivo) VALUES (?, ?) ON CONFLICT(postulante_id) DO UPDATE SET archivo=excluded.archivo",
                    (profile_id, saved_cv_name),
                )
            else:
                cur.execute(
                    "INSERT INTO curriculums (postulante_id, archivo) VALUES (%s, %s) ON DUPLICATE KEY UPDATE archivo=VALUES(archivo)",
                    (profile_id, saved_cv_name),
                )
        if request.form.get("eliminar_video") == "1":
            cur.execute(
                f"DELETE FROM videos WHERE postulante_id = {placeholder}",
                (profile_id,),
            )
        elif video_url:
            if Config.USE_SQLITE:
                cur.execute(
                    "INSERT INTO videos (postulante_id, url) VALUES (?, ?) ON CONFLICT(postulante_id) DO UPDATE SET url=excluded.url",
                    (profile_id, video_url),
                )
            else:
                cur.execute(
                    "INSERT INTO videos (postulante_id, url) VALUES (%s, %s) ON DUPLICATE KEY UPDATE url=VALUES(url)",
                    (profile_id, video_url),
                )
        conn.commit()
        flash("Perfil actualizado correctamente.", "success")
        conn.close()
        return redirect(url_for("postulante_perfil"))

    conn.close()
    return render_template("postulante/perfil.html", perfil=perfil)


@app.route("/empresa/perfil", methods=["GET", "POST"])
def empresa_perfil():
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")

    if Config.USE_SQLITE:
        perfil = cur.execute(
            "SELECT u.nombre, u.apellido, u.correo, e.nombre_empresa, e.descripcion, e.sector, e.ubicacion, e.sitio_web, e.telefono FROM usuarios u LEFT JOIN empresas e ON e.usuario_id = u.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
    else:
        perfil = cur.execute(
            "SELECT u.nombre, u.apellido, u.correo, e.nombre_empresa, e.descripcion, e.sector, e.ubicacion, e.sitio_web, e.telefono FROM usuarios u LEFT JOIN empresas e ON e.usuario_id = u.id WHERE u.id = %s",
            (user_id,),
        ).fetchone()

    if request.method == "POST":
        nombre_empresa = request.form.get("nombre_empresa", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        sector = request.form.get("sector", "").strip()
        ubicacion = request.form.get("ubicacion", "").strip()
        sitio_web = request.form.get("sitio_web", "").strip()
        telefono = request.form.get("telefono", "").strip()

        if Config.USE_SQLITE:
            cur.execute(
                "INSERT INTO empresas (usuario_id, nombre_empresa, descripcion, sector, ubicacion, sitio_web, telefono) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(usuario_id) DO UPDATE SET nombre_empresa=excluded.nombre_empresa, descripcion=excluded.descripcion, sector=excluded.sector, ubicacion=excluded.ubicacion, sitio_web=excluded.sitio_web, telefono=excluded.telefono",
                (user_id, nombre_empresa, descripcion, sector, ubicacion, sitio_web, telefono),
            )
        else:
            cur.execute(
                "INSERT INTO empresas (usuario_id, nombre_empresa, descripcion, sector, ubicacion, sitio_web, telefono) VALUES (%s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE nombre_empresa=VALUES(nombre_empresa), descripcion=VALUES(descripcion), sector=VALUES(sector), ubicacion=VALUES(ubicacion), sitio_web=VALUES(sitio_web), telefono=VALUES(telefono)",
                (user_id, nombre_empresa, descripcion, sector, ubicacion, sitio_web, telefono),
            )

        conn.commit()
        flash("Perfil de empresa actualizado.", "success")
        conn.close()
        return redirect(url_for("empresa_perfil"))

    conn.close()
    return render_template("empresa/perfil.html", perfil=perfil)


@app.route("/ofertas")
def ofertas():
    filtros = {
        "cargo": request.args.get("cargo", "").strip(),
        "ciudad": request.args.get("ciudad", "").strip(),
        "contrato": request.args.get("contrato", "").strip(),
        "jornada": request.args.get("jornada", "").strip(),
        "habilidad": request.args.get("habilidad", "").strip(),
    }
    placeholder = "?" if Config.USE_SQLITE else "%s"
    conditions = [
        "o.estado = 'ACTIVA'",
        "(o.fecha_cierre IS NULL OR o.fecha_cierre >= CURRENT_DATE)",
    ]
    params = []
    for field, value in (
        ("o.titulo", filtros["cargo"]),
        ("o.ubicacion", filtros["ciudad"]),
        ("o.tipo_contrato", filtros["contrato"]),
        ("o.jornada", filtros["jornada"]),
        ("o.habilidades", filtros["habilidad"]),
    ):
        if value:
            conditions.append(f"{field} LIKE {placeholder}")
            params.append(f"%{value}%")
    conn = get_db()
    cur = conn.cursor()
    rows = cur.execute(
        f"""
        SELECT o.*, e.nombre_empresa FROM ofertas o
        JOIN empresas e ON e.id = o.empresa_id
        WHERE {' AND '.join(conditions)}
        ORDER BY o.id DESC
        """,
        tuple(params),
    ).fetchall()
    conn.close()

    return render_template("ofertas.html", ofertas=rows, filtros=filtros)


@app.route("/ofertas/<int:oferta_id>")
def oferta_detalle(oferta_id):
    conn = get_db()
    cur = conn.cursor()
    if Config.USE_SQLITE:
        oferta = cur.execute(
            "SELECT o.*, e.nombre_empresa FROM ofertas o JOIN empresas e ON e.id = o.empresa_id WHERE o.id = ? AND o.estado = 'ACTIVA' AND (o.fecha_cierre IS NULL OR o.fecha_cierre >= CURRENT_DATE)",
            (oferta_id,),
        ).fetchone()
    else:
        oferta = cur.execute(
            "SELECT o.*, e.nombre_empresa FROM ofertas o JOIN empresas e ON e.id = o.empresa_id WHERE o.id = %s AND o.estado = 'ACTIVA' AND (o.fecha_cierre IS NULL OR o.fecha_cierre >= CURRENT_DATE)",
            (oferta_id,),
        ).fetchone()
    conn.close()

    if oferta is None:
        return render_template("errors/404.html"), 404

    if session.get("rol") == "POSTULANTE":
        user_id = session.get("usuario_id")
        conn = get_db()
        cur = conn.cursor()
        if Config.USE_SQLITE:
            postulante = cur.execute("SELECT * FROM postulantes WHERE usuario_id = ?", (user_id,)).fetchone()
        else:
            postulante = cur.execute("SELECT * FROM postulantes WHERE usuario_id = %s", (user_id,)).fetchone()
        conn.close()
        if postulante is not None:
            habilidades_postulante = []
            if isinstance(postulante, sqlite3.Row):
                habilidades_postulante = (postulante["habilidades"] or "").split(",")
            else:
                habilidades_postulante = (postulante["habilidades"] or "").split(",")
            oferta_habilidades = (oferta["habilidades"] or "").split(",")
            compatibilidad = calcular_compatibilidad(habilidades_postulante, oferta_habilidades)
        else:
            compatibilidad = 0
    else:
        compatibilidad = None

    return render_template("oferta_detalle.html", oferta=oferta, compatibilidad=compatibilidad)


@app.route("/postular/<int:oferta_id>", methods=["POST"])
def postular(oferta_id):
    if session.get("rol") != "POSTULANTE":
        flash("Debes iniciar sesión como postulante.", "error")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")

    if Config.USE_SQLITE:
        postulante = cur.execute("SELECT * FROM postulantes WHERE usuario_id = ?", (user_id,)).fetchone()
        oferta = cur.execute("SELECT * FROM ofertas WHERE id = ? AND estado = 'ACTIVA' AND (fecha_cierre IS NULL OR fecha_cierre >= CURRENT_DATE)", (oferta_id,)).fetchone()
        curriculum = cur.execute(
            "SELECT id FROM curriculums WHERE postulante_id = ?",
            (postulante["id"],),
        ).fetchone() if postulante else None
        existe = cur.execute(
            "SELECT id FROM postulaciones WHERE oferta_id = ? AND postulante_id = ?",
            (oferta_id, postulante["id"]),
        ).fetchone() if postulante else None
    else:
        postulante = cur.execute("SELECT * FROM postulantes WHERE usuario_id = %s", (user_id,)).fetchone()
        oferta = cur.execute("SELECT * FROM ofertas WHERE id = %s AND estado = 'ACTIVA' AND (fecha_cierre IS NULL OR fecha_cierre >= CURRENT_DATE)", (oferta_id,)).fetchone()
        curriculum = cur.execute(
            "SELECT id FROM curriculums WHERE postulante_id = %s",
            (postulante["id"],),
        ).fetchone() if postulante else None
        existe = cur.execute(
            "SELECT id FROM postulaciones WHERE oferta_id = %s AND postulante_id = %s",
            (oferta_id, postulante["id"]),
        ).fetchone() if postulante else None

    if postulante is None:
        conn.close()
        flash("Completa tu perfil antes de postular.", "error")
        return redirect(url_for("postulante_perfil"))
    if not oferta:
        flash("La oferta no existe.", "error")
        conn.close()
        return redirect(url_for("ofertas"))
    if not curriculum:
        conn.close()
        flash("Debes cargar tu currículum PDF antes de postular.", "error")
        return redirect(url_for("postulante_perfil"))

    if existe:
        flash("Ya te postulaste a esta oferta.", "info")
        conn.close()
        return redirect(url_for("ofertas"))

    if Config.USE_SQLITE:
        cur.execute(
            "INSERT INTO postulaciones (oferta_id, postulante_id, estado) VALUES (?, ?, 'POSTULADO')",
            (oferta_id, postulante["id"]),
        )
    else:
        cur.execute(
            "INSERT INTO postulaciones (oferta_id, postulante_id, estado) VALUES (%s, %s, 'POSTULADO')",
            (oferta_id, postulante["id"]),
        )
    application_id = cur.lastrowid
    placeholder = "?" if Config.USE_SQLITE else "%s"
    cur.execute(
        f"INSERT INTO seguimiento (postulacion_id, estado, observacion) VALUES ({placeholder}, 'POSTULADO', 'Postulación recibida')",
        (application_id,),
    )
    empresa_usuario = cur.execute(
        f"SELECT e.usuario_id FROM empresas e JOIN ofertas o ON o.empresa_id = e.id WHERE o.id = {placeholder}",
        (oferta_id,),
    ).fetchone()
    if empresa_usuario:
        guardar_notificacion(
            cur,
            empresa_usuario["usuario_id"],
            f"Nueva postulación recibida para {oferta['titulo']}.",
        )
    conn.commit()
    conn.close()
    flash("Postulación registrada correctamente.", "success")
    return redirect(url_for("postulante_dashboard"))


@app.route("/empresa/ofertas/nueva", methods=["GET", "POST"])
def oferta_nueva():
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))

    if request.method == "POST":
        titulo = request.form["titulo"].strip()
        descripcion = request.form["descripcion"].strip()
        experiencia_requerida = request.form.get("experiencia_requerida", "").strip()
        educacion_requerida = request.form.get("educacion_requerida", "").strip()
        requisitos = request.form.get("requisitos", "").strip()
        fecha_cierre = request.form.get("fecha_cierre", "").strip() or None
        habilidades = request.form.get("habilidades", "").strip()
        ubicacion = request.form.get("ubicacion", "").strip()
        tipo_contrato = request.form.get("tipo_contrato", "").strip()
        jornada = request.form.get("jornada", "").strip()
        rango_salarial = request.form.get("rango_salarial", "").strip()

        if not titulo or not descripcion:
            flash("El título y la descripción son obligatorios.", "error")
            return render_template("empresa/oferta_nueva.html")
        if fecha_cierre:
            try:
                fecha_cierre_date = date.fromisoformat(fecha_cierre)
            except ValueError:
                flash("La fecha de cierre no es válida.", "error")
                return render_template("empresa/oferta_nueva.html")
            if fecha_cierre_date < date.today():
                flash("La fecha de cierre no puede estar en el pasado.", "error")
                return render_template("empresa/oferta_nueva.html")

        conn = get_db()
        cur = conn.cursor()
        user_id = session.get("usuario_id")
        empresa = cur.execute(
            "SELECT * FROM empresas WHERE usuario_id = ?",
            (user_id,),
        ).fetchone() if Config.USE_SQLITE else cur.execute(
            "SELECT * FROM empresas WHERE usuario_id = %s",
            (user_id,),
        ).fetchone()

        empresa_id = empresa["id"]
        if Config.USE_SQLITE:
            cur.execute(
                "INSERT INTO ofertas (empresa_id, titulo, descripcion, experiencia_requerida, educacion_requerida, requisitos, habilidades, ubicacion, tipo_contrato, jornada, rango_salarial, fecha_cierre, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVA')",
                (empresa_id, titulo, descripcion, experiencia_requerida, educacion_requerida, requisitos, habilidades, ubicacion, tipo_contrato, jornada, rango_salarial, fecha_cierre),
            )
        else:
            cur.execute(
                "INSERT INTO ofertas (empresa_id, titulo, descripcion, experiencia_requerida, educacion_requerida, requisitos, habilidades, ubicacion, tipo_contrato, jornada, rango_salarial, fecha_cierre, estado) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVA')",
                (empresa_id, titulo, descripcion, experiencia_requerida, educacion_requerida, requisitos, habilidades, ubicacion, tipo_contrato, jornada, rango_salarial, fecha_cierre),
            )
        conn.commit()
        conn.close()
        flash("Oferta creada correctamente.", "success")
        return redirect(url_for("empresa_dashboard"))

    return render_template("empresa/oferta_nueva.html")


@app.route("/empresa/ofertas/<int:oferta_id>/estado", methods=["POST"])
def actualizar_estado_oferta(oferta_id):
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))
    estado = request.form.get("estado", "").strip().upper()
    if estado not in {"ACTIVA", "PAUSADA", "CERRADA"}:
        flash("Estado de oferta no válido.", "error")
        return redirect(url_for("empresa_dashboard"))
    placeholder = "?" if Config.USE_SQLITE else "%s"
    conn = get_db()
    cur = conn.cursor()
    empresa = cur.execute(
        f"SELECT id FROM empresas WHERE usuario_id = {placeholder}",
        (session["usuario_id"],),
    ).fetchone()
    if empresa is None:
        conn.close()
        abort(403)
    owned_offer = cur.execute(
        f"SELECT id FROM ofertas WHERE id = {placeholder} AND empresa_id = {placeholder}",
        (oferta_id, empresa["id"]),
    ).fetchone()
    if owned_offer is None:
        conn.close()
        abort(404)
    cur.execute(
        f"UPDATE ofertas SET estado = {placeholder} WHERE id = {placeholder}",
        (estado, oferta_id),
    )
    conn.commit()
    conn.close()
    flash("Estado de la oferta actualizado.", "success")
    return redirect(url_for("empresa_dashboard"))


@app.route("/empresa/candidatos")
def empresa_candidatos():
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")
    empresa = cur.execute(
        "SELECT * FROM empresas WHERE usuario_id = ?",
        (user_id,),
    ).fetchone() if Config.USE_SQLITE else cur.execute(
        "SELECT * FROM empresas WHERE usuario_id = %s",
        (user_id,),
    ).fetchone()

    if empresa is None:
        conn.close()
        abort(403)

    placeholder = "?" if Config.USE_SQLITE else "%s"
    rows = cur.execute(
        f"""
        SELECT p.id, u.nombre, u.apellido, o.titulo, p.estado, p.fecha_postulacion,
               po.ciudad, po.habilidades AS habilidades_postulante,
               po.experiencia, po.educacion, o.habilidades AS habilidades_oferta
        FROM postulaciones p
        JOIN postulantes po ON po.id = p.postulante_id
        JOIN usuarios u ON u.id = po.usuario_id
        JOIN ofertas o ON o.id = p.oferta_id
        WHERE o.empresa_id = {placeholder}
        ORDER BY p.id DESC
        """,
        (empresa["id"],),
    ).fetchall()
    filtros = {
        "estado": request.args.get("estado", "").strip().upper(),
        "ciudad": request.args.get("ciudad", "").strip().lower(),
        "habilidad": request.args.get("habilidad", "").strip().lower(),
        "experiencia": request.args.get("experiencia", "").strip().lower(),
        "educacion": request.args.get("educacion", "").strip().lower(),
    }
    postulaciones = []
    for row in rows:
        item = dict(row)
        item["compatibilidad"] = calcular_compatibilidad(
            (item["habilidades_postulante"] or "").split(","),
            (item["habilidades_oferta"] or "").split(","),
        )
        if filtros["estado"] and item["estado"] != filtros["estado"]:
            continue
        if filtros["ciudad"] and filtros["ciudad"] not in (item["ciudad"] or "").lower():
            continue
        if filtros["habilidad"] and filtros["habilidad"] not in (item["habilidades_postulante"] or "").lower():
            continue
        if filtros["experiencia"] and filtros["experiencia"] not in (item["experiencia"] or "").lower():
            continue
        if filtros["educacion"] and filtros["educacion"] not in (item["educacion"] or "").lower():
            continue
        postulaciones.append(item)
    conn.close()
    return render_template(
        "empresa/candidatos.html",
        postulaciones=postulaciones,
        filtros=filtros,
        estados=("POSTULADO", "REVISION", "PRESELECCIONADO", "ENTREVISTA", "SELECCIONADO", "RECHAZADO", "FINALIZADO"),
    )


def get_owned_application(cursor, postulacion_id, usuario_empresa_id):
    placeholder = "?" if Config.USE_SQLITE else "%s"
    return cursor.execute(
        f"""
        SELECT p.id, p.oferta_id, p.postulante_id, p.estado, p.fecha_postulacion, p.observacion,
               o.titulo, u.nombre, u.apellido, u.correo,
               po.telefono, po.ciudad, po.region, po.descripcion,
               po.objetivo_profesional, po.habilidades, po.experiencia, po.educacion,
               c.archivo AS curriculum_archivo, v.url AS video_url
        FROM postulaciones p
        JOIN ofertas o ON o.id = p.oferta_id
        JOIN empresas e ON e.id = o.empresa_id
        JOIN postulantes po ON po.id = p.postulante_id
        JOIN usuarios u ON u.id = po.usuario_id
        LEFT JOIN curriculums c ON c.postulante_id = po.id
        LEFT JOIN videos v ON v.postulante_id = po.id
        WHERE p.id = {placeholder} AND e.usuario_id = {placeholder}
        """,
        (postulacion_id, usuario_empresa_id),
    ).fetchone()


@app.route("/empresa/candidatos/<int:postulacion_id>")
def empresa_candidato_detalle(postulacion_id):
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))
    conn = get_db()
    candidato = get_owned_application(conn.cursor(), postulacion_id, session["usuario_id"])
    conn.close()
    if candidato is None:
        abort(404)
    return render_template("empresa/candidato_detalle.html", candidato=candidato)


@app.route("/empresa/postulaciones/<int:postulacion_id>/cv")
def empresa_candidato_cv(postulacion_id):
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))
    conn = get_db()
    candidato = get_owned_application(conn.cursor(), postulacion_id, session["usuario_id"])
    conn.close()
    if candidato is None or not candidato["curriculum_archivo"]:
        abort(404)
    contents = load_cv_file(candidato["curriculum_archivo"])
    return send_file(
        BytesIO(contents),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="curriculum.pdf",
    )


@app.route("/postulante/cv")
def postulante_cv():
    if session.get("rol") != "POSTULANTE":
        return redirect(url_for("login"))
    placeholder = "?" if Config.USE_SQLITE else "%s"
    conn = get_db()
    row = conn.cursor().execute(
        f"SELECT c.archivo FROM curriculums c JOIN postulantes p ON p.id = c.postulante_id WHERE p.usuario_id = {placeholder}",
        (session["usuario_id"],),
    ).fetchone()
    conn.close()
    if row is None:
        abort(404)
    contents = load_cv_file(row["archivo"])
    return send_file(
        BytesIO(contents),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="curriculum.pdf",
    )


@app.route("/postulante/notificaciones")
def postulante_notificaciones():
    if session.get("rol") != "POSTULANTE":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    user_id = session.get("usuario_id")

    if Config.USE_SQLITE:
        rows = cur.execute(
            "SELECT * FROM notificaciones WHERE usuario_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM notificaciones WHERE usuario_id = %s ORDER BY id DESC",
            (user_id,),
        ).fetchall()

    conn.close()
    return render_template("postulante/notificaciones.html", notificaciones=rows)


@app.route("/empresa/postulaciones/<int:postulacion_id>/agendar_entrevista", methods=["POST"])
def agendar_entrevista(postulacion_id):
    if session.get("rol") != "EMPRESA":
        flash("Debes iniciar sesión como empresa.", "error")
        return redirect(url_for("login"))

    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    modalidad = request.form.get("modalidad", "ONLINE").strip().upper()
    lugar = request.form.get("lugar", "").strip()
    if not Entrevista(postulacion_id=postulacion_id, modalidad=modalidad).modalidad_valida():
        flash("La modalidad de entrevista no es válida.", "error")
        return redirect(url_for("empresa_candidatos"))

    if not fecha or not hora:
        flash("Debes completar la fecha y la hora de la entrevista.", "error")
        return redirect(url_for("empresa_candidatos"))
    try:
        interview_date = date.fromisoformat(fecha)
        time.fromisoformat(hora)
    except ValueError:
        flash("La fecha o la hora de la entrevista no son válidas.", "error")
        return redirect(url_for("empresa_candidatos"))
    if interview_date < date.today():
        flash("La fecha de entrevista no puede estar en el pasado.", "error")
        return redirect(url_for("empresa_candidatos"))

    conn = get_db()
    cur = conn.cursor()

    postulacion = get_owned_application(cur, postulacion_id, session["usuario_id"])

    if postulacion is None:
        conn.close()
        flash("La postulación no existe.", "error")
        return redirect(url_for("empresa_candidatos"))

    if Config.USE_SQLITE:
        cur.execute(
            "INSERT INTO entrevistas (postulacion_id, fecha, hora, modalidad, lugar, estado) VALUES (?, ?, ?, ?, ?, 'PENDIENTE')",
            (postulacion_id, fecha, hora, modalidad, lugar or "Por confirmar"),
        )
        cur.execute(
            "UPDATE postulaciones SET estado = 'ENTREVISTA' WHERE id = ?",
            (postulacion_id,),
        )
        cur.execute(
            "INSERT INTO seguimiento (postulacion_id, estado, observacion) VALUES (?, 'ENTREVISTA', ?)",
            (postulacion_id, f"Entrevista agendada para {fecha} a las {hora} ({modalidad})."),
        )
        postulante = cur.execute("SELECT * FROM postulantes WHERE id = ?", (postulacion["postulante_id"],)).fetchone()
        if postulante is not None:
            usuario = cur.execute("SELECT * FROM usuarios WHERE id = ?", (postulante["usuario_id"],)).fetchone()
            if usuario is not None:
                guardar_notificacion(
                    cur,
                    usuario["id"],
                    f"Tu entrevista fue agendada para el {fecha} a las {hora} ({modalidad}).",
                )
    else:
        cur.execute(
            "INSERT INTO entrevistas (postulacion_id, fecha, hora, modalidad, lugar, estado) VALUES (%s, %s, %s, %s, %s, 'PENDIENTE')",
            (postulacion_id, fecha, hora, modalidad, lugar or "Por confirmar"),
        )
        cur.execute(
            "UPDATE postulaciones SET estado = 'ENTREVISTA' WHERE id = %s",
            (postulacion_id,),
        )
        cur.execute(
            "INSERT INTO seguimiento (postulacion_id, estado, observacion) VALUES (%s, 'ENTREVISTA', %s)",
            (postulacion_id, f"Entrevista agendada para {fecha} a las {hora} ({modalidad})."),
        )
        postulante = cur.execute("SELECT * FROM postulantes WHERE id = %s", (postulacion["postulante_id"],)).fetchone()
        if postulante is not None:
            usuario = cur.execute("SELECT * FROM usuarios WHERE id = %s", (postulante["usuario_id"],)).fetchone()
            if usuario is not None:
                guardar_notificacion(
                    cur,
                    usuario["id"],
                    f"Tu entrevista fue agendada para el {fecha} a las {hora} ({modalidad}).",
                )

    conn.commit()
    conn.close()
    flash("Entrevista agendada correctamente.", "success")
    return redirect(url_for("empresa_candidatos"))


@app.route("/empresa/postulaciones/<int:postulacion_id>/estado", methods=["POST"])
def actualizar_estado_postulacion(postulacion_id):
    if session.get("rol") != "EMPRESA":
        flash("Debes iniciar sesión como empresa.", "error")
        return redirect(url_for("login"))

    estado = request.form.get("estado", "").strip().upper()
    observacion = request.form.get("observacion", "").strip()

    conn = get_db()
    cur = conn.cursor()
    postulacion = get_owned_application(cur, postulacion_id, session["usuario_id"])

    if postulacion is None:
        conn.close()
        flash("La postulación no existe.", "error")
        return redirect(url_for("empresa_candidatos"))

    proceso = ProcesoSeleccion(
        Postulacion(
            id=postulacion["id"],
            oferta_id=postulacion["oferta_id"],
            postulante_id=postulacion["postulante_id"],
            estado=postulacion["estado"],
        )
    )
    try:
        proceso.avanzar_a(estado)
    except ValueError:
        conn.close()
        flash("Estado no válido.", "error")
        return redirect(url_for("empresa_candidatos"))

    if Config.USE_SQLITE:
        cur.execute(
            "UPDATE postulaciones SET estado = ?, observacion = ? WHERE id = ?",
            (estado, observacion, postulacion_id),
        )
        cur.execute(
            "INSERT INTO seguimiento (postulacion_id, estado, observacion) VALUES (?, ?, ?)",
            (postulacion_id, estado, observacion or None),
        )
        postulante = cur.execute("SELECT * FROM postulantes WHERE id = ?", (postulacion["postulante_id"],)).fetchone()
        if postulante is not None:
            usuario = cur.execute("SELECT * FROM usuarios WHERE id = ?", (postulante["usuario_id"],)).fetchone()
            if usuario is not None:
                mensaje = f"El estado de tu postulación cambió a {estado}."
                if observacion:
                    mensaje += f" Observación: {observacion}"
                guardar_notificacion(cur, usuario["id"], mensaje)
    else:
        cur.execute(
            "UPDATE postulaciones SET estado = %s, observacion = %s WHERE id = %s",
            (estado, observacion, postulacion_id),
        )
        cur.execute(
            "INSERT INTO seguimiento (postulacion_id, estado, observacion) VALUES (%s, %s, %s)",
            (postulacion_id, estado, observacion or None),
        )
        postulante = cur.execute("SELECT * FROM postulantes WHERE id = %s", (postulacion["postulante_id"],)).fetchone()
        if postulante is not None:
            usuario = cur.execute("SELECT * FROM usuarios WHERE id = %s", (postulante["usuario_id"],)).fetchone()
            if usuario is not None:
                mensaje = f"El estado de tu postulación cambió a {estado}."
                if observacion:
                    mensaje += f" Observación: {observacion}"
                guardar_notificacion(cur, usuario["id"], mensaje)

    conn.commit()
    conn.close()
    flash("Estado actualizado correctamente.", "success")
    return redirect(url_for("empresa_candidatos"))


@app.route("/empresa/entrevistas")
def empresa_entrevistas():
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))
    placeholder = "?" if Config.USE_SQLITE else "%s"
    conn = get_db()
    rows = conn.cursor().execute(
        f"""
        SELECT i.id, i.fecha, i.hora, i.modalidad, i.lugar, i.observaciones, i.estado,
               p.id AS postulacion_id, u.nombre, u.apellido, o.titulo
        FROM entrevistas i
        JOIN postulaciones p ON p.id = i.postulacion_id
        JOIN ofertas o ON o.id = p.oferta_id
        JOIN empresas e ON e.id = o.empresa_id
        JOIN postulantes po ON po.id = p.postulante_id
        JOIN usuarios u ON u.id = po.usuario_id
        WHERE e.usuario_id = {placeholder}
        ORDER BY i.fecha DESC, i.hora DESC
        """,
        (session["usuario_id"],),
    ).fetchall()
    conn.close()
    return render_template("empresa/entrevistas.html", entrevistas=rows)


@app.route("/empresa/entrevistas/<int:entrevista_id>/estado", methods=["POST"])
def actualizar_estado_entrevista(entrevista_id):
    if session.get("rol") != "EMPRESA":
        return redirect(url_for("login"))
    estado = request.form.get("estado", "").strip().upper()
    if estado not in {"PENDIENTE", "REALIZADA", "CANCELADA"}:
        flash("Estado de entrevista no válido.", "error")
        return redirect(url_for("empresa_entrevistas"))

    placeholder = "?" if Config.USE_SQLITE else "%s"
    conn = get_db()
    cur = conn.cursor()
    owned = cur.execute(
        f"""
        SELECT i.id FROM entrevistas i
        JOIN postulaciones p ON p.id = i.postulacion_id
        JOIN ofertas o ON o.id = p.oferta_id
        JOIN empresas e ON e.id = o.empresa_id
        WHERE i.id = {placeholder} AND e.usuario_id = {placeholder}
        """,
        (entrevista_id, session["usuario_id"]),
    ).fetchone()
    if owned is None:
        conn.close()
        abort(404)
    cur.execute(
        f"UPDATE entrevistas SET estado = {placeholder} WHERE id = {placeholder}",
        (estado, entrevista_id),
    )
    conn.commit()
    conn.close()
    flash("Estado de entrevista actualizado.", "success")
    return redirect(url_for("empresa_entrevistas"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if session.get("rol") != "ADMIN":
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    users = cur.execute(
        "SELECT id, nombre, apellido, correo, rol, activo, creado_en FROM usuarios ORDER BY creado_en DESC"
    ).fetchall()
    stats = {
        "usuarios": cur.execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()["total"],
        "empresas": cur.execute("SELECT COUNT(*) AS total FROM empresas").fetchone()["total"],
        "postulantes": cur.execute("SELECT COUNT(*) AS total FROM postulantes").fetchone()["total"],
        "ofertas_activas": cur.execute("SELECT COUNT(*) AS total FROM ofertas WHERE estado = 'ACTIVA'").fetchone()["total"],
        "postulaciones": cur.execute("SELECT COUNT(*) AS total FROM postulaciones").fetchone()["total"],
        "procesos_finalizados": cur.execute("SELECT COUNT(*) AS total FROM postulaciones WHERE estado IN ('SELECCIONADO', 'RECHAZADO', 'FINALIZADO')").fetchone()["total"],
    }
    conn.close()
    return render_template("admin/dashboard.html", usuarios=users, stats=stats)


@app.route("/admin/usuarios/<int:usuario_id>/estado", methods=["POST"])
def actualizar_estado_usuario(usuario_id):
    if session.get("rol") != "ADMIN":
        return redirect(url_for("login"))
    if usuario_id == session.get("usuario_id"):
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("admin_dashboard"))
    activo = request.form.get("activo")
    if activo not in {"0", "1"}:
        flash("Estado de cuenta no válido.", "error")
        return redirect(url_for("admin_dashboard"))
    placeholder = "?" if Config.USE_SQLITE else "%s"
    conn = get_db()
    cur = conn.cursor()
    result = cur.execute(
        f"UPDATE usuarios SET activo = {placeholder} WHERE id = {placeholder} AND rol IN ('EMPRESA', 'POSTULANTE')",
        (int(activo), usuario_id),
    )
    if getattr(result, "rowcount", 0) == 0:
        conn.close()
        flash("La cuenta no existe o no puede ser administrada.", "error")
        return redirect(url_for("admin_dashboard"))
    conn.commit()
    conn.close()
    flash("Estado de cuenta actualizado.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404


@app.errorhandler(413)
def file_too_large(error):
    flash("El archivo supera el máximo permitido de 10 MB.", "error")
    return redirect(url_for("postulante_perfil"))


@app.errorhandler(500)
def internal_error(error):
    return render_template("errors/500.html"), 500


if not Config.CLOUDFLARE_WORKERS and Config.USE_SQLITE:
    init_db()


if __name__ == "__main__":
    app.run(debug=Config.DEBUG)
