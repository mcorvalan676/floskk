import tempfile
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app as app_module


class PrivacyAndUploadsTest(unittest.TestCase):
    def setUp(self):
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

    def test_cloudflare_without_hyperdrive_renders_presentation_only(self):
        with (
            patch.object(app_module.Config, "CLOUDFLARE_WORKERS", True),
            patch.dict(app_module.app.config, {"SECRET_KEY": None}),
        ):
            response = self.client.get(
                "/",
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
        self.assertEqual(restricted_response.status_code, 503)
        self.assertIn("base de datos", restricted_response.get_data(as_text=True))

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
