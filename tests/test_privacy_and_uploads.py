import tempfile
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

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
        self.client.post("/login", data={"correo": email, "password": "123456"})
        conn = app_module.get_db()
        offer = conn.cursor().execute(
            "SELECT id FROM ofertas WHERE estado = 'ACTIVA' ORDER BY id LIMIT 1"
        ).fetchone()
        applicant = conn.cursor().execute(
            "SELECT p.id FROM postulantes p JOIN usuarios u ON u.id = p.usuario_id WHERE u.correo = ?",
            (email,),
        ).fetchone()
        response = self.client.post(f"/postular/{offer['id']}", follow_redirects=True)
        application = conn.cursor().execute(
            "SELECT id FROM postulaciones WHERE oferta_id = ? AND postulante_id = ?",
            (offer["id"], applicant["id"]),
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
        self.client.post(
            "/login",
            data={"correo": "admin@demo.cl", "password": "demo123"},
        )
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Panel de administraci", response.data)


if __name__ == "__main__":
    unittest.main()
