import unittest
from uuid import uuid4
from unittest.mock import patch

from app import app
from wsgi import app as wsgi_app
from models.user import create_user, get_user
from werkzeug.security import generate_password_hash


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_home_page_renders(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_health_endpoint(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.get_json())

    def test_healthz_is_public_and_does_not_query_storage(self):
        with patch('database.connect_database', side_effect=AssertionError('Health check must not open storage')), \
                patch('routes.get_user', side_effect=AssertionError('Health check must not query users')):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'OK')
        self.assertNotIn('Set-Cookie', response.headers)

    def test_numeric_nutrition_route_renders_for_signed_in_user(self):
        username = f'nutrition-user-{uuid4().hex[:8]}'
        create_user(
            username=username,
            pasword_hash=generate_password_hash('secret123'),
            created_at='2024-01-01',
            email=f'{uuid4().hex[:8]}@example.com',
        )
        user = get_user(username=username)

        with self.client.session_transaction() as session:
            session['user_id'] = user['user_id']

        response = self.client.get('/nutrition')
        self.assertEqual(response.status_code, 200)
        self.assertIn('National Nutrition Data', response.get_data(as_text=True))

    def test_wsgi_entrypoint_uses_same_app(self):
        self.assertIs(wsgi_app, app)


if __name__ == '__main__':
    unittest.main()
