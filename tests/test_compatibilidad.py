import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from services.compatibilidad import analizar_compatibilidad, calcular_compatibilidad


class CompatibilityAnalysisTest(unittest.TestCase):
    def test_analysis_explains_matches_missing_skills_and_profile_gaps(self):
        analysis = analizar_compatibilidad(
            "Python, Flask, python",
            [" python ", "FLASK", "Docker"],
            {
                "habilidades": "Python, Flask",
                "experiencia": "",
                "educacion": "Informática",
                "descripcion": "Desarrolladora",
                "objetivo_profesional": "",
            },
        )

        self.assertEqual(analysis["porcentaje"], 67)
        self.assertEqual(analysis["nivel"], "Media")
        self.assertEqual(analysis["coincidencias"], ["python", "FLASK"])
        self.assertEqual(analysis["requisitos_faltantes"], ["Docker"])
        self.assertEqual(
            analysis["campos_sin_informacion"],
            ["Experiencia", "Objetivo profesional"],
        )
        self.assertIn("predice una", analysis["criterio"])

    def test_analysis_reports_insufficient_data_when_offer_has_no_skills(self):
        analysis = analizar_compatibilidad(
            ["Python"],
            [],
            {"habilidades": "", "experiencia": None},
        )

        self.assertIsNone(analysis["porcentaje"])
        self.assertEqual(analysis["nivel"], "Sin datos suficientes")
        self.assertEqual(analysis["requisitos_faltantes"], [])
        self.assertIn("no especifica habilidades", analysis["explicacion"])
        self.assertEqual(
            analysis["campos_sin_informacion"],
            ["Habilidades", "Experiencia", "Educación",
             "Presentación profesional", "Objetivo profesional"],
        )

    def test_match_levels_follow_documented_skill_ratio_thresholds(self):
        self.assertEqual(
            analizar_compatibilidad(["a", "b", "c"], ["a", "b", "c", "d"])["nivel"],
            "Alta",
        )
        self.assertEqual(
            analizar_compatibilidad(["a", "b"], ["a", "b", "c", "d", "e"])["nivel"],
            "Media",
        )
        self.assertEqual(
            analizar_compatibilidad(["a"], ["a", "b", "c"])["nivel"],
            "Baja",
        )

    def test_legacy_score_keeps_existing_numeric_contract(self):
        self.assertEqual(
            calcular_compatibilidad([" Python ", "Flask"], ["python", "SQL"]),
            50,
        )
        self.assertEqual(calcular_compatibilidad(["Python"], []), 0)


class CompatibilityViewsTest(unittest.TestCase):
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
        self.ids = self._create_application()

    def tearDown(self):
        self.database_patch.stop()
        self.database_dir.cleanup()
        self.csrf_patch.stop()

    def _create_application(self):
        conn = app_module.get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO usuarios
                (nombre, apellido, correo, password_hash, rol, activo)
            VALUES (?, ?, ?, ?, 'EMPRESA', 1)
            """,
            ("Empresa", "Prueba", "empresa-match@example.test",
             app_module.hash_password("password")),
        )
        company_user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO empresas (usuario_id, nombre_empresa) VALUES (?, ?)",
            (company_user_id, "Empresa de prueba"),
        )
        company_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO usuarios
                (nombre, apellido, correo, password_hash, rol, activo)
            VALUES (?, ?, ?, ?, 'POSTULANTE', 1)
            """,
            ("Candidato", "Prueba", "candidato-match@example.test",
             app_module.hash_password("password")),
        )
        candidate_user_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO postulantes
                (usuario_id, ciudad, descripcion, objetivo_profesional,
                 habilidades, experiencia, educacion)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_user_id,
                "Santiago",
                "Perfil profesional",
                "Desarrollo de software",
                "Python, Flask",
                "Proyecto personal",
                "",
            ),
        )
        candidate_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO ofertas
                (empresa_id, titulo, descripcion, habilidades,
                 experiencia_requerida, educacion_requerida, estado)
            VALUES (?, ?, ?, ?, ?, ?, 'ACTIVA')
            """,
            (
                company_id,
                "Desarrollador",
                "Oferta de prueba",
                "Python, Flask, SQL",
                "Experiencia deseable",
                "Formación técnica deseable",
            ),
        )
        offer_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO postulaciones (oferta_id, postulante_id, estado)
            VALUES (?, ?, 'POSTULADO')
            """,
            (offer_id, candidate_id),
        )
        application_id = cur.lastrowid
        conn.commit()
        conn.close()
        return {
            "company_user_id": company_user_id,
            "candidate_user_id": candidate_user_id,
            "offer_id": offer_id,
            "application_id": application_id,
        }

    def test_candidate_sees_explainable_match_without_ai(self):
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["candidate_user_id"]
            session["rol"] = "POSTULANTE"

        response = self.client.get(f"/ofertas/{self.ids['offer_id']}")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Coincidencia con habilidades", page)
        self.assertIn("Prepara tu CV para esta oferta", page)
        self.assertIn("no la presentes como una habilidad propia", page)
        self.assertIn("Python", page)
        self.assertIn("Flask", page)
        self.assertIn("SQL", page)
        self.assertIn("Educación", page)
        self.assertIn("predice una", page)

    def test_offer_list_shows_skill_matches_for_candidates(self):
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["candidate_user_id"]
            session["rol"] = "POSTULANTE"

        response = self.client.get("/ofertas")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Coincidencia de habilidades: Media", page)
        self.assertIn("Coinciden: Python, Flask.", page)
        self.assertIn("La oferta también menciona: SQL.", page)
        self.assertIn("ni predice contrataciones", page)

    def test_offer_list_does_not_show_personalized_match_to_visitor(self):
        response = self.client.get("/ofertas")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Coincidencia de habilidades", page)

    def test_candidate_without_declared_skills_gets_profile_prompt_not_zero_scores(self):
        conn = app_module.get_db()
        conn.cursor().execute(
            "UPDATE postulantes SET habilidades = '' WHERE usuario_id = ?",
            (self.ids["candidate_user_id"],),
        )
        conn.commit()
        conn.close()
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["candidate_user_id"]
            session["rol"] = "POSTULANTE"

        response = self.client.get("/ofertas")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Completa las habilidades de tu perfil", page)
        self.assertNotIn("Coincidencia de habilidades", page)

    def test_candidate_dashboard_shows_actionable_profile_checklist(self):
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["candidate_user_id"]
            session["rol"] = "POSTULANTE"

        response = self.client.get("/postulante/dashboard")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Checklist de perfil", page)
        self.assertIn("Teléfono — pendiente", page)
        self.assertIn("Habilidades — completado", page)
        self.assertIn("Currículum en PDF — pendiente", page)

    def test_company_sees_explanation_only_for_owned_application(self):
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["company_user_id"]
            session["rol"] = "EMPRESA"

        response = self.client.get(
            f"/empresa/candidatos/{self.ids['application_id']}"
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Resumen de coincidencia con la oferta", page)
        self.assertIn("Habilidades que coinciden", page)
        self.assertIn("Información no declarada en el perfil", page)
        self.assertIn("Experiencia deseable", page)
        candidate_list = self.client.get("/empresa/candidatos")
        self.assertEqual(candidate_list.status_code, 200)
        self.assertIn(b"Ver explicaci", candidate_list.data)

        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["candidate_user_id"]
            session["rol"] = "EMPRESA"
        forbidden = self.client.get(
            f"/empresa/candidatos/{self.ids['application_id']}"
        )
        self.assertEqual(forbidden.status_code, 404)

    def test_company_dashboard_groups_applications_and_filters_by_offer(self):
        conn = app_module.get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ofertas
                (empresa_id, titulo, descripcion, habilidades, estado)
            SELECT id, 'Analista de datos', 'Segunda oferta', 'SQL', 'ACTIVA'
            FROM empresas WHERE usuario_id = ?
            """,
            (self.ids["company_user_id"],),
        )
        second_offer_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO postulaciones (oferta_id, postulante_id, estado)
            SELECT ?, id, 'REVISION'
            FROM postulantes WHERE usuario_id = ?
            """,
            (second_offer_id, self.ids["candidate_user_id"]),
        )
        conn.commit()
        conn.close()

        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["company_user_id"]
            session["rol"] = "EMPRESA"

        dashboard = self.client.get("/empresa/dashboard")
        dashboard_page = dashboard.get_data(as_text=True)
        filtered = self.client.get(
            f"/empresa/candidatos?oferta_id={self.ids['offer_id']}"
        )
        other_filtered = self.client.get(
            f"/empresa/candidatos?oferta_id={second_offer_id}"
        )

        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("1 en total", dashboard_page)
        self.assertIn("Revisar postulaciones", dashboard_page)
        self.assertEqual(filtered.status_code, 200)
        self.assertIn(b"<td>Desarrollador</td>", filtered.data)
        self.assertNotIn(b"<td>Analista de datos</td>", filtered.data)
        self.assertEqual(other_filtered.status_code, 200)
        self.assertIn(b"<td>Analista de datos</td>", other_filtered.data)
        self.assertNotIn(b"<td>Desarrollador</td>", other_filtered.data)


if __name__ == "__main__":
    unittest.main()
