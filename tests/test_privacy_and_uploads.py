import tempfile
import re
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app as app_module


class PrivacyAndUploadsTest(unittest.TestCase):
    def setUp(self):
        self.csrf_patch = patch.object(app_module.Config, "CSRF_ENABLED", False)
        self.csrf_patch.start()
        self.database_dir = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(
            app_module.Config,
            "SQLITE_DB_PATH",
            str(Path(self.database_dir.name) / "test.db"),
        )
        self.database_patch.start()
        app_module.init_db()
        self.client = app_module.app.test_client()
        self.upload_dir = tempfile.TemporaryDirectory()
        self.upload_patch = patch.object(app_module, "CV_UPLOAD_DIR", Path(self.upload_dir.name))
        self.upload_patch.start()

    def tearDown(self):
        self.upload_patch.stop()
        self.upload_dir.cleanup()
        self.database_patch.stop()
        self.database_dir.cleanup()
        self.csrf_patch.stop()

    def test_homepage_renders_jinja_and_utf8(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("charset=utf-8", response.content_type.lower())
        self.assertIn("contratación", page)
        self.assertIn("¿Cómo funciona?", page)
        self.assertNotIn("{% extends", page)
        self.assertNotIn("{% block", page)
        self.assertNotIn("{% endblock", page)
        self.assertNotIn("{{ url_for", page)

    def test_health_check_does_not_require_database_access(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_post_requests_require_csrf_token(self):
        with patch.object(app_module.Config, "CSRF_ENABLED", True):
            login_page = self.client.get("/login")
            token_match = re.search(
                rb'name="csrf_token" value="([^"]+)"',
                login_page.data,
            )
            self.assertIsNotNone(token_match)
            token = token_match.group(1).decode("ascii")

            rejected = self.client.post(
                "/login",
                data={"correo": "nobody@example.test", "password": "wrong"},
            )
            accepted = self.client.post(
                "/login",
                data={
                    "correo": "nobody@example.test",
                    "password": "wrong",
                    "csrf_token": token,
                },
            )

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(accepted.status_code, 200)

    def test_password_hash_uses_workers_compatible_pbkdf2(self):
        password = "secure-password-123"
        password_hash = app_module.hash_password(password)

        self.assertTrue(password_hash.startswith("pbkdf2:sha256:600000$"))
        self.assertTrue(app_module.check_password_hash(password_hash, password))
        self.assertFalse(app_module.check_password_hash(password_hash, "incorrect"))

    def test_cloudflare_without_database_renders_presentation_only(self):
        with (
            patch.object(app_module.Config, "CLOUDFLARE_WORKERS", True),
            patch.dict(app_module.app.config, {"SECRET_KEY": None}),
            patch.dict(
                "sys.modules",
                {
                    "cloudflare_runtime": SimpleNamespace(
                        get_worker_asset=lambda worker_env, path: SimpleNamespace(
                            status=200,
                            headers={"Content-Type": "text/css"},
                            body=b"body { color: black; }",
                        )
                    )
                },
            ),
        ):
            response = self.client.get(
                "/",
                environ_overrides={"workers.env": SimpleNamespace()},
            )
            static_response = self.client.get(
                "/static/css/style.css",
                environ_overrides={"workers.env": SimpleNamespace()},
            )
            restricted_response = self.client.get(
                "/login",
                environ_overrides={"workers.env": SimpleNamespace()},
            )

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Modo de presentación", page)
        self.assertNotIn("Buscar oportunidades", page)
        self.assertEqual(static_response.status_code, 200)
        self.assertEqual(static_response.get_data(), b"body { color: black; }")
        self.assertEqual(restricted_response.status_code, 503)
        self.assertIn("D1", restricted_response.get_data(as_text=True))

    def test_cloudflare_routes_are_enabled_when_required_bindings_exist(self):
        worker_env = SimpleNamespace(
            SECRET_KEY="test-secret-key",
            DB=object(),
            CV_BUCKET=object(),
        )
        with (
            patch.object(app_module.Config, "CLOUDFLARE_WORKERS", True),
            self.client.application.test_request_context(
                "/login",
                environ_overrides={"workers.env": worker_env},
            ),
        ):
            self.assertFalse(app_module.is_cloudflare_limited_mode())

    def test_d1_migration_creates_expected_tables(self):
        import sqlite3

        migrations = Path(__file__).resolve().parents[1] / "migrations"
        connection = sqlite3.connect(":memory:")
        for migration in sorted(migrations.glob("*.sql")):
            connection.executescript(migration.read_text(encoding="utf-8"))
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(seguimiento)")
        }
        connection.close()

        self.assertTrue(
            {
                "usuarios",
                "postulantes",
                "empresas",
                "ofertas",
                "ofertas_favoritas",
                "postulaciones",
                "seguimiento",
                "curriculums",
                "cv_archivos",
                "entrevistas",
                "notificaciones",
            }.issubset(tables)
        )
        self.assertTrue(
            {"estado_anterior", "usuario_id", "rol_actor"}.issubset(columns)
        )

    def test_d1_adapter_binds_nulls_and_returns_rows_and_insert_ids(self):
        import importlib
        import sys
        import types
        from datetime import date

        jsnull = object()
        ffi = types.ModuleType("pyodide.ffi")
        ffi.run_sync = lambda result: result
        ffi.jsnull = jsnull
        ffi.to_js = lambda value: value
        pyodide = types.ModuleType("pyodide")
        pyodide.ffi = ffi
        js = types.ModuleType("js")
        js.fetch = object()
        js.crypto = object()
        js.Uint8Array = SimpleNamespace(new=lambda values: bytes(values))

        class Statement:
            def __init__(self, query):
                self.query = query
                self.parameters = ()

            def bind(self, *parameters):
                self.parameters = parameters
                return self

            def all(self):
                return SimpleNamespace(
                    results=[{"id": 7}],
                    meta={"last_row_id": 0, "changes": 0},
                )

            def run(self):
                return SimpleNamespace(
                    results=[],
                    meta={"last_row_id": 42, "changes": 1},
                )

            def first(self):
                return SimpleNamespace(contenido=b"%PDF-test")

        class Database:
            def __init__(self):
                self.statements = []
                self.batches = []

            def prepare(self, query):
                statement = Statement(query)
                self.statements.append(statement)
                return statement

            def batch(self, statements):
                self.batches.append(statements)
                return []

        previous_module = sys.modules.pop("cloudflare_runtime", None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "pyodide": pyodide,
                    "pyodide.ffi": ffi,
                    "js": js,
                },
            ):
                runtime = importlib.import_module("cloudflare_runtime")
                database = Database()
                worker_env = SimpleNamespace(DB=database)
                connection = runtime.connect_d1(worker_env)
                cursor = connection.cursor()
                row = cursor.execute(
                    "SELECT id FROM usuarios WHERE creado_en = ?",
                    (date(2026, 10, 2),),
                ).fetchone()
                cursor.execute(
                    "INSERT INTO usuarios (nombre) VALUES (?)",
                    (None,),
                )
                runtime.save_cv_d1(worker_env, "cv/test.pdf", b"%PDF-test")
                cv_bytes = runtime.load_cv_d1(worker_env, "cv/test.pdf")
                connection.execute_batch(
                    [
                        ("INSERT INTO usuarios (nombre) VALUES (?)", ("Ana",)),
                        ("INSERT INTO postulantes (usuario_id) VALUES (?)", (True,)),
                    ]
                )
                cursor.close()
                connection.close()
        finally:
            sys.modules.pop("cloudflare_runtime", None)
            if previous_module is not None:
                sys.modules["cloudflare_runtime"] = previous_module

        self.assertEqual(row, {"id": 7})
        self.assertEqual(database.statements[0].parameters, ("2026-10-02",))
        self.assertEqual(database.statements[1].parameters, (jsnull,))
        self.assertEqual(cursor.lastrowid, 42)
        self.assertEqual(cursor.rowcount, 1)
        self.assertEqual(database.statements[2].parameters, ("cv/test.pdf", b"%PDF-test"))
        self.assertEqual(cv_bytes, b"%PDF-test")
        self.assertEqual(len(database.batches), 1)
        self.assertEqual(len(database.batches[0]), 2)
        self.assertEqual(database.batches[0][1].parameters, (1,))

    def test_cloudflare_initial_admin_setup_is_one_time(self):
        import sqlite3

        database_path = Path(app_module.Config.SQLITE_DB_PATH)

        class SQLiteBatchConnection:
            def __init__(self):
                self.connection = sqlite3.connect(database_path)
                self.connection.row_factory = sqlite3.Row

            def cursor(self):
                return self.connection.cursor()

            def execute_batch(self, statements):
                try:
                    for query, parameters in statements:
                        self.connection.execute(query, parameters)
                    self.connection.commit()
                except Exception:
                    self.connection.rollback()
                    raise

            def close(self):
                self.connection.close()

        def open_test_database():
            return SQLiteBatchConnection()

        worker_env = SimpleNamespace(
            SECRET_KEY="test-secret-key",
            DB=object(),
            CV_BUCKET=object(),
            INITIAL_ADMIN_TOKEN="one-time-token",
        )
        with (
            patch.object(app_module.Config, "CLOUDFLARE_WORKERS", True),
            patch.object(app_module, "get_db", side_effect=open_test_database),
            patch.object(
                app_module,
                "hash_password",
                return_value=app_module.generate_password_hash(
                    "a-long-secure-password",
                    method="pbkdf2:sha256:600000",
                ),
            ),
        ):
            response = self.client.post(
                "/setup-admin",
                data={
                    "token": "one-time-token",
                    "nombre": "Admin",
                    "apellido": "Prueba",
                    "correo": "cloudflare-admin@example.test",
                    "password": "a-long-secure-password",
                },
                environ_overrides={"workers.env": worker_env},
            )
            unavailable = self.client.get(
                "/setup-admin",
                environ_overrides={"workers.env": worker_env},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        self.assertEqual(unavailable.status_code, 404)

    def test_static_assets_are_served_with_content_types(self):
        css = self.client.get("/static/css/style.css")
        javascript = self.client.get("/static/js/main.js")

        self.assertEqual(css.status_code, 200)
        self.assertIn("text/css", css.content_type)
        self.assertEqual(javascript.status_code, 200)
        self.assertIn("javascript", javascript.content_type)
        css.close()
        javascript.close()

    def test_sqlite_creates_missing_database_directory(self):
        database_path = Path(self.database_dir.name) / "missing" / "nested" / "test.db"
        with patch.object(app_module.Config, "SQLITE_DB_PATH", str(database_path)):
            connection = app_module.get_db()
            connection.close()

        self.assertTrue(database_path.is_file())

    def test_mysql_initialization_does_not_seed_demo_accounts(self):
        connection = MagicMock()
        with (
            patch.object(app_module.Config, "USE_SQLITE", False),
            patch.object(app_module, "get_db", return_value=connection),
        ):
            app_module.init_db()

        connection.commit.assert_called_once()

    def test_fresh_sqlite_database_has_no_seeded_accounts_or_offers(self):
        connection = app_module.get_db()
        cursor = connection.cursor()
        user_count = cursor.execute(
            "SELECT COUNT(*) AS total FROM usuarios"
        ).fetchone()["total"]
        offer_count = cursor.execute(
            "SELECT COUNT(*) AS total FROM ofertas"
        ).fetchone()["total"]
        cursor.close()
        connection.close()

        self.assertEqual(user_count, 0)
        self.assertEqual(offer_count, 0)

    def test_admin_can_be_provisioned_with_flask_cli(self):
        with (
            patch("builtins.input", side_effect=["Admin", "Prueba", "admin@example.test"]),
            patch(
                "getpass.getpass",
                side_effect=["long-secure-password", "long-secure-password"],
            ),
        ):
            result = app_module.app.test_cli_runner().invoke(
                args=["create-admin"]
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Cuenta de administración creada", result.output)
        self.client.post(
            "/login",
            data={
                "correo": "admin@example.test",
                "password": "long-secure-password",
            },
        )
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)

    def test_candidates_can_save_and_remove_only_their_own_favorite_offers(self):
        _, _, company_id = self.create_user("EMPRESA")
        _, owner_user_id, owner_id = self.create_user("POSTULANTE")
        _, other_user_id, _ = self.create_user("POSTULANTE")

        conn = app_module.get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ofertas (empresa_id, titulo, descripcion, estado)
            VALUES (?, ?, ?, 'ACTIVA')
            """,
            (company_id, "Oferta favorita de prueba", "Descripción de prueba"),
        )
        offer_id = cur.lastrowid
        conn.commit()
        conn.close()

        with self.client.session_transaction() as session:
            session["usuario_id"] = owner_user_id
            session["rol"] = "POSTULANTE"
        saved = self.client.post(
            f"/postulante/favoritos/{offer_id}",
            data={"action": "guardar"},
        )
        self.assertEqual(saved.status_code, 302)
        listing = self.client.get("/postulante/favoritos")
        self.assertIn(b"Oferta favorita de prueba", listing.data)

        with self.client.session_transaction() as session:
            session["usuario_id"] = other_user_id
            session["rol"] = "POSTULANTE"
        self.client.post(
            f"/postulante/favoritos/{offer_id}",
            data={"action": "quitar"},
        )
        other_listing = self.client.get("/postulante/favoritos")
        self.assertNotIn(b"Oferta favorita de prueba", other_listing.data)

        with self.client.session_transaction() as session:
            session["usuario_id"] = owner_user_id
            session["rol"] = "POSTULANTE"
        owner_listing = self.client.get("/postulante/favoritos")
        self.assertIn(b"Oferta favorita de prueba", owner_listing.data)
        removed = self.client.post(
            f"/postulante/favoritos/{offer_id}",
            data={"action": "quitar"},
            follow_redirects=True,
        )
        self.assertIn(b"Oferta quitada de tus guardadas.", removed.data)
        self.assertNotIn(b"Oferta favorita de prueba", removed.data)

        conn = app_module.get_db()
        favorite_count = conn.cursor().execute(
            "SELECT COUNT(*) AS total FROM ofertas_favoritas WHERE postulante_id = ?",
            (owner_id,),
        ).fetchone()["total"]
        conn.close()
        self.assertEqual(favorite_count, 0)

    def create_user(self, role):
        email = f"{role.lower()}_{uuid.uuid4().hex}@example.test"
        conn = app_module.get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (?, ?, ?, ?, ?, 1)",
            ("Cuenta", "Prueba", email, app_module.generate_password_hash("123456"), role),
        )
        user_id = cur.lastrowid
        if role == "EMPRESA":
            cur.execute(
                "INSERT INTO empresas (usuario_id, nombre_empresa) VALUES (?, ?)",
                (user_id, "Empresa " + uuid.uuid4().hex[:6]),
            )
            profile_id = cur.lastrowid
        elif role == "ADMIN":
            cur.execute(
                "INSERT INTO administradores (usuario_id) VALUES (?)",
                (user_id,),
            )
            profile_id = cur.lastrowid
        else:
            cur.execute(
                "INSERT INTO postulantes (usuario_id, ciudad, region) VALUES (?, ?, ?)",
                (user_id, "Santiago", "Metropolitana"),
            )
            profile_id = cur.lastrowid
        conn.commit()
        conn.close()
        return email, user_id, profile_id

    def test_cv_upload_is_private_and_downloadable_by_owner(self):
        email, _, _ = self.create_user("POSTULANTE")
        self.client.post("/login", data={"correo": email, "password": "123456"})

        response = self.client.post(
            "/postulante/perfil",
            data={
                "telefono": "",
                "ciudad": "Santiago",
                "region": "Metropolitana",
                "descripcion": "Perfil de prueba",
                "objetivo_profesional": "",
                "habilidades": "Python",
                "experiencia": "",
                "educacion": "",
                "curriculum": (BytesIO(b"%PDF-1.7\ncontenido de prueba"), "cv.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)

        download = self.client.get("/postulante/cv")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"%PDF-1.7\ncontenido de prueba")
        download.close()

        self.client.get("/logout")
        self.assertEqual(self.client.get("/postulante/cv").status_code, 302)

    def test_cloudflare_rejects_cv_larger_than_d1_row_budget(self):
        email, _, _ = self.create_user("POSTULANTE")
        self.client.post("/login", data={"correo": email, "password": "123456"})

        database_path = Path(app_module.Config.SQLITE_DB_PATH)

        def open_test_database():
            connection = app_module.sqlite3.connect(database_path)
            connection.row_factory = app_module.sqlite3.Row
            return connection

        worker_env = SimpleNamespace(SECRET_KEY="test-secret-key", DB=object())
        with (
            patch.object(app_module.Config, "CLOUDFLARE_WORKERS", True),
            patch.object(app_module, "get_db", side_effect=open_test_database),
            patch.object(app_module, "save_cv_file") as save_cv,
        ):
            response = self.client.post(
                "/postulante/perfil",
                data={
                    "telefono": "",
                    "ciudad": "Santiago",
                    "region": "Metropolitana",
                    "descripcion": "",
                    "objetivo_profesional": "",
                    "habilidades": "",
                    "experiencia": "",
                    "educacion": "",
                    "curriculum": (
                        BytesIO(b"%PDF-" + b"x" * app_module.MAX_CV_FILE_SIZE),
                        "large.pdf",
                    ),
                },
                content_type="multipart/form-data",
                environ_overrides={"workers.env": worker_env},
            )

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertTrue(
                any(
                    "Cloudflare" in message and "1 MB" in message
                    for _, message in session["_flashes"]
                )
            )
        save_cv.assert_not_called()

    def test_application_requires_cv(self):
        email, _, _ = self.create_user("POSTULANTE")
        _, _, company_id = self.create_user("EMPRESA")
        conn = app_module.get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ofertas (empresa_id, titulo, descripcion, estado) VALUES (?, ?, ?, 'ACTIVA')",
            (company_id, "Oferta temporal de prueba", "Oferta creada solo para este test."),
        )
        offer_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        self.client.post("/login", data={"correo": email, "password": "123456"})
        conn = app_module.get_db()
        applicant = conn.cursor().execute(
            "SELECT p.id FROM postulantes p JOIN usuarios u ON u.id = p.usuario_id WHERE u.correo = ?",
            (email,),
        ).fetchone()
        response = self.client.post(f"/postular/{offer_id}", follow_redirects=True)
        application = conn.cursor().execute(
            "SELECT id FROM postulaciones WHERE oferta_id = ? AND postulante_id = ?",
            (offer_id, applicant["id"]),
        ).fetchone()
        conn.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Debes cargar tu currículum PDF", response.data.decode("utf-8"))
        self.assertIsNone(application)

    def test_company_cannot_view_or_update_another_company_application(self):
        owning_company_email, _, owning_company_id = self.create_user("EMPRESA")
        other_company_email, _, _ = self.create_user("EMPRESA")
        applicant_email, _, applicant_id = self.create_user("POSTULANTE")
        conn = app_module.get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ofertas (empresa_id, titulo, descripcion, estado) VALUES (?, ?, ?, 'ACTIVA')",
            (owning_company_id, "Oferta privada", "Descripción"),
        )
        offer_id = cur.lastrowid
        cur.execute(
            "INSERT INTO postulaciones (oferta_id, postulante_id, estado) VALUES (?, ?, 'POSTULADO')",
            (offer_id, applicant_id),
        )
        application_id = cur.lastrowid
        conn.commit()
        conn.close()

        self.client.post("/login", data={"correo": other_company_email, "password": "123456"})
        self.assertEqual(self.client.get(f"/empresa/candidatos/{application_id}").status_code, 404)
        self.client.post(
            f"/empresa/postulaciones/{application_id}/estado",
            data={"estado": "SELECCIONADO"},
        )

        conn = app_module.get_db()
        status = conn.cursor().execute(
            "SELECT estado FROM postulaciones WHERE id = ?",
            (application_id,),
        ).fetchone()["estado"]
        conn.close()
        self.assertEqual(status, "POSTULADO")

        self.client.get("/logout")
        self.client.post("/login", data={"correo": owning_company_email, "password": "123456"})
        self.assertEqual(self.client.get(f"/empresa/candidatos/{application_id}").status_code, 200)
        self.assertEqual(self.client.get("/empresa/candidatos").status_code, 200)
        self.client.post(
            f"/empresa/ofertas/{offer_id}/estado",
            data={"estado": "PAUSADA"},
        )
        conn = app_module.get_db()
        offer_status = conn.cursor().execute(
            "SELECT estado FROM ofertas WHERE id = ?",
            (offer_id,),
        ).fetchone()["estado"]
        conn.close()
        self.assertEqual(offer_status, "PAUSADA")

    def test_admin_dashboard_is_restricted_to_admin_role(self):
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        email, _, _ = self.create_user("ADMIN")
        self.client.post(
            "/login",
            data={"correo": email, "password": "123456"},
        )
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Panel de administraci", response.data)


if __name__ == "__main__":
    unittest.main()
