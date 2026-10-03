import unittest
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import app as app_module


class InterviewNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.csrf_patch = patch.object(app_module.Config, "CSRF_ENABLED", False)
        self.csrf_patch.start()
        self.app = app_module.app
        self.client = self.app.test_client()

    def tearDown(self):
        self.csrf_patch.stop()

    def test_postulante_can_access_notifications_page_after_login(self):
        email = f'notificaciones_postulante_{uuid.uuid4().hex[:8]}@example.com'
        self.client.post('/register', data={
            'nombre': 'Luis',
            'apellido': 'Prueba',
            'correo': email,
            'password': '123456',
            'rol': 'POSTULANTE'
        }, follow_redirects=True)

        self.client.post('/login', data={
            'correo': email,
            'password': '123456'
        }, follow_redirects=True)

        response = self.client.get('/postulante/notificaciones')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Notificaciones', response.data)

    def test_notification_can_only_be_marked_read_by_its_owner(self):
        conn = app_module.get_db()
        cur = conn.cursor()
        emails = [
            f'notificacion_owner_{uuid.uuid4().hex[:8]}@example.com',
            f'notificacion_other_{uuid.uuid4().hex[:8]}@example.com',
        ]
        user_ids = []
        notification_ids = []
        for email in emails:
            cur.execute(
                """
                INSERT INTO usuarios
                    (nombre, apellido, correo, password_hash, rol, activo)
                VALUES (?, ?, ?, ?, 'POSTULANTE', 1)
                """,
                ('Prueba', 'Notificación', email, app_module.generate_password_hash('123456')),
            )
            user_id = cur.lastrowid
            user_ids.append(user_id)
            cur.execute(
                "INSERT INTO notificaciones (usuario_id, mensaje, leida) VALUES (?, ?, 0)",
                (user_id, 'Aviso privado de prueba'),
            )
            notification_ids.append(cur.lastrowid)
        conn.commit()
        conn.close()

        with self.client.session_transaction() as session:
            session['usuario_id'] = user_ids[1]
            session['rol'] = 'POSTULANTE'
        forbidden = self.client.post(
            f'/postulante/notificaciones/{notification_ids[0]}/leer'
        )
        self.assertEqual(forbidden.status_code, 302)

        conn = app_module.get_db()
        unchanged = conn.cursor().execute(
            "SELECT leida FROM notificaciones WHERE id = ?",
            (notification_ids[0],),
        ).fetchone()
        conn.close()
        self.assertEqual(unchanged['leida'], 0)

        with self.client.session_transaction() as session:
            session['usuario_id'] = user_ids[0]
            session['rol'] = 'POSTULANTE'
        accepted = self.client.post(
            f'/postulante/notificaciones/{notification_ids[0]}/leer',
            follow_redirects=True,
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertIn(b'Notificaci\xc3\xb3n marcada como le\xc3\xadda.', accepted.data)
        self.assertNotIn(b'Marcar como le\xc3\xadda', accepted.data)

    def test_company_can_schedule_interview_and_create_notification(self):
        conn = app_module.get_db()
        cur = conn.cursor()
        empresa_email = f'empresa_agenda_{uuid.uuid4().hex[:8]}@example.com'
        postulante_email = f'postulante_agenda_{uuid.uuid4().hex[:8]}@example.com'

        cur.execute("INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    ('Empresa', 'Agenda', empresa_email, app_module.generate_password_hash('123456'), 'EMPRESA'))
        empresa_user_id = cur.lastrowid
        cur.execute("INSERT INTO empresas (usuario_id, nombre_empresa, descripcion, sector, ubicacion) VALUES (?, ?, ?, ?, ?)",
                    (empresa_user_id, 'Agenda Labs', 'Empresa de pruebas', 'Tecnología', 'Santiago'))
        empresa_id = cur.lastrowid

        cur.execute("INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    ('Postulante', 'Agenda', postulante_email, app_module.generate_password_hash('123456'), 'POSTULANTE'))
        postulante_user_id = cur.lastrowid
        cur.execute("INSERT INTO postulantes (usuario_id, ciudad, region, descripcion, objetivo_profesional, habilidades) VALUES (?, ?, ?, ?, ?, ?)",
                    (postulante_user_id, 'Valparaíso', 'V Región', 'Perfil de prueba', 'Objetivo de prueba', 'Python, Flask'))
        postulante_id = cur.lastrowid

        cur.execute("INSERT INTO ofertas (empresa_id, titulo, descripcion, habilidades, ubicacion, tipo_contrato, jornada, rango_salarial, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVA')",
                    (empresa_id, 'Analista de Datos', 'Oferta para prueba', 'Python, SQL', 'Santiago', 'Indefinido', 'Full time', '$1.200.000'))
        oferta_id = cur.lastrowid

        cur.execute("INSERT INTO postulaciones (oferta_id, postulante_id, estado) VALUES (?, ?, 'POSTULADO')",
                    (oferta_id, postulante_id))
        postulacion_id = cur.lastrowid

        conn.commit()
        conn.close()

        self.client.post('/login', data={
            'correo': empresa_email,
            'password': '123456'
        }, follow_redirects=True)

        interview_date = date.today() + timedelta(days=1)
        response = self.client.post(f'/empresa/postulaciones/{postulacion_id}/agendar_entrevista', data={
            'fecha': interview_date.isoformat(),
            'hora': '10:30',
            'modalidad': 'ONLINE',
            'lugar': 'Meet'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        conn = app_module.get_db()
        cur = conn.cursor()
        entrevista = cur.execute("SELECT * FROM entrevistas WHERE postulacion_id = ?", (postulacion_id,)).fetchone()
        notificacion = cur.execute("SELECT * FROM notificaciones WHERE usuario_id = ? ORDER BY id DESC LIMIT 1", (postulante_user_id,)).fetchone()
        history = cur.execute(
            "SELECT * FROM seguimiento WHERE postulacion_id = ? ORDER BY id DESC LIMIT 1",
            (postulacion_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(entrevista)
        self.assertIsNotNone(notificacion)
        self.assertEqual(history["estado_anterior"], "POSTULADO")
        self.assertEqual(history["estado"], "ENTREVISTA")
        self.assertEqual(history["usuario_id"], empresa_user_id)
        self.assertEqual(history["rol_actor"], "EMPRESA")
        self.assertIn(b'Entrevista', response.data)

        self.client.get('/logout')
        self.client.post('/login', data={
            'correo': postulante_email,
            'password': '123456'
        }, follow_redirects=True)
        dashboard = self.client.get('/postulante/dashboard')
        self.assertIn(b'Pr\xc3\xb3xima entrevista', dashboard.data)
        self.assertIn(b'Analista de Datos', dashboard.data)
        self.assertIn(b'Agenda Labs', dashboard.data)

    def test_company_can_update_postulation_state_and_notify_postulant(self):
        conn = app_module.get_db()
        cur = conn.cursor()
        empresa_email = f'empresa_estado_{uuid.uuid4().hex[:8]}@example.com'
        postulante_email = f'postulante_estado_{uuid.uuid4().hex[:8]}@example.com'

        cur.execute("INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    ('Empresa', 'Estado', empresa_email, app_module.generate_password_hash('123456'), 'EMPRESA'))
        empresa_user_id = cur.lastrowid
        cur.execute("INSERT INTO empresas (usuario_id, nombre_empresa, descripcion, sector, ubicacion) VALUES (?, ?, ?, ?, ?)",
                    (empresa_user_id, 'Estado Labs', 'Empresa de estados', 'Tecnología', 'Santiago'))
        empresa_id = cur.lastrowid

        cur.execute("INSERT INTO usuarios (nombre, apellido, correo, password_hash, rol, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    ('Postulante', 'Estado', postulante_email, app_module.generate_password_hash('123456'), 'POSTULANTE'))
        postulante_user_id = cur.lastrowid
        cur.execute("INSERT INTO postulantes (usuario_id, ciudad, region, descripcion, objetivo_profesional, habilidades) VALUES (?, ?, ?, ?, ?, ?)",
                    (postulante_user_id, 'Concepción', 'VIII Región', 'Perfil de prueba', 'Objetivo de prueba', 'Python, Flask'))
        postulante_id = cur.lastrowid

        cur.execute("INSERT INTO ofertas (empresa_id, titulo, descripcion, habilidades, ubicacion, tipo_contrato, jornada, rango_salarial, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVA')",
                    (empresa_id, 'Ingeniero', 'Oferta de estado', 'Python', 'Santiago', 'Indefinido', 'Full time', '$1.400.000'))
        oferta_id = cur.lastrowid

        cur.execute("INSERT INTO postulaciones (oferta_id, postulante_id, estado) VALUES (?, ?, 'POSTULADO')",
                    (oferta_id, postulante_id))
        postulacion_id = cur.lastrowid

        conn.commit()
        conn.close()

        self.client.post('/login', data={
            'correo': empresa_email,
            'password': '123456'
        }, follow_redirects=True)

        response = self.client.post(f'/empresa/postulaciones/{postulacion_id}/estado', data={
            'estado': 'REVISION',
            'observacion': 'Revisar carta y experiencia'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Estado actualizado', response.data)

        conn = app_module.get_db()
        cur = conn.cursor()
        post = cur.execute("SELECT estado, observacion FROM postulaciones WHERE id = ?", (postulacion_id,)).fetchone()
        notif = cur.execute("SELECT * FROM notificaciones WHERE usuario_id = ? ORDER BY id DESC LIMIT 1", (postulante_user_id,)).fetchone()
        history = cur.execute(
            "SELECT * FROM seguimiento WHERE postulacion_id = ? ORDER BY id DESC LIMIT 1",
            (postulacion_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(post)
        self.assertEqual(post["estado"], 'REVISION')
        self.assertIn('Revisar carta', post["observacion"])
        self.assertIsNotNone(notif)
        self.assertEqual(history["estado_anterior"], "POSTULADO")
        self.assertEqual(history["estado"], "REVISION")
        self.assertEqual(history["usuario_id"], empresa_user_id)
        self.assertEqual(history["rol_actor"], "EMPRESA")


if __name__ == '__main__':
    unittest.main()
