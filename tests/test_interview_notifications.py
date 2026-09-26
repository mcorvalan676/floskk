import unittest
import uuid

import app as app_module


class InterviewNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.client = self.app.test_client()

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

        response = self.client.post(f'/empresa/postulaciones/{postulacion_id}/agendar_entrevista', data={
            'fecha': '2026-10-10',
            'hora': '10:30',
            'modalidad': 'ONLINE',
            'lugar': 'Meet'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        conn = app_module.get_db()
        cur = conn.cursor()
        entrevista = cur.execute("SELECT * FROM entrevistas WHERE postulacion_id = ?", (postulacion_id,)).fetchone()
        notificacion = cur.execute("SELECT * FROM notificaciones WHERE usuario_id = ? ORDER BY id DESC LIMIT 1", (postulante_user_id,)).fetchone()
        conn.close()

        self.assertIsNotNone(entrevista)
        self.assertIsNotNone(notificacion)
        self.assertIn(b'Entrevista', response.data)

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
        conn.close()

        self.assertIsNotNone(post)
        self.assertEqual(post["estado"], 'REVISION')
        self.assertIn('Revisar carta', post["observacion"])
        self.assertIsNotNone(notif)


if __name__ == '__main__':
    unittest.main()
