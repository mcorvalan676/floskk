import unittest
from unittest.mock import patch

import app as app_module


class ProfileRoutesTest(unittest.TestCase):
    def setUp(self):
        self.csrf_patch = patch.object(app_module.Config, "CSRF_ENABLED", False)
        self.csrf_patch.start()
        self.app = app_module.app
        self.client = self.app.test_client()

    def tearDown(self):
        self.csrf_patch.stop()

    def test_postulante_profile_requires_login(self):
        response = self.client.get('/postulante/perfil')
        self.assertEqual(response.status_code, 302)

    def test_company_profile_requires_login(self):
        response = self.client.get('/empresa/perfil')
        self.assertEqual(response.status_code, 302)

    def test_postulante_can_access_profile_after_login(self):
        email = 'perfil_postulante_test@example.com'
        self.client.post('/register', data={
            'nombre': 'Ana',
            'apellido': 'Prueba',
            'correo': email,
            'password': '123456',
            'rol': 'POSTULANTE'
        }, follow_redirects=True)

        login = self.client.post('/login', data={
            'correo': email,
            'password': '123456'
        }, follow_redirects=True)
        self.assertEqual(login.status_code, 200)
        response = self.client.get('/postulante/perfil')
        self.assertIn(b'Perfil profesional', response.data)
        dashboard = self.client.get('/postulante/dashboard')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Ofertas disponibles', dashboard.data)
        self.assertIn(b'Entrevistas pr\xc3\xb3ximas', dashboard.data)
        self.assertIn(b'Perfil completo', dashboard.data)

    def test_company_can_access_profile_after_login(self):
        email = 'perfil_empresa_test@example.com'
        self.client.post('/register', data={
            'nombre': 'Empresa',
            'apellido': 'Prueba',
            'correo': email,
            'password': '123456',
            'rol': 'EMPRESA'
        }, follow_redirects=True)

        self.client.post('/login', data={
            'correo': email,
            'password': '123456'
        }, follow_redirects=True)
        response = self.client.get('/empresa/perfil')
        self.assertIn(b'Perfil de empresa', response.data)


if __name__ == '__main__':
    unittest.main()
