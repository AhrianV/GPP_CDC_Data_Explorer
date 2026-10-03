"""Exercise authentication throttles without creating users or waiting in real time."""
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from app import app
from form_helpers import csrf_token


class AuthRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.web = app.test_client()
        octets = uuid4().bytes[:3]
        self.ip = '10.' + '.'.join(str(part) for part in octets)
        self.lookup = patch('routes.get_user', return_value=None)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)
        self.token = csrf_token(self.web)

    def post(self, path='/signin', **kwargs):
        kwargs['data'] = {'csrf_token': self.token, **kwargs.get('data', {})}
        return self.web.post(path, environ_overrides={'REMOTE_ADDR': self.ip}, **kwargs)

    def exhaust_signin(self):
        for _ in range(5):
            self.assertEqual(self.post().status_code, 302)

    def test_signin_limit_rejects_before_authentication(self):
        self.exhaust_signin()
        with patch('routes.check_password_hash') as password_check:
            response = self.post(data={'identifier': 'student', 'password': 'secret123'})
        self.assertEqual(response.status_code, 429)
        self.assertIn(b'Too many sign-in attempts', response.data)
        self.assertGreater(int(response.headers['Retry-After']), 0)
        self.assertLessEqual(int(response.headers['Retry-After']), 61)
        self.assertIn('no-store', response.headers['Cache-Control'])
        password_check.assert_not_called()

    def test_signup_limit_rejects_before_account_creation(self):
        for _ in range(5):
            self.assertEqual(self.post('/signup').status_code, 302)
        with patch('routes.create_user') as create:
            response = self.post('/signup', data={'username': 'new-student', 'password': 'secret123',
                                                 'email': '', 'educational_acknowledgment': 'accepted'})
        self.assertEqual(response.status_code, 429)
        self.assertIn(b'Too many sign-up attempts', response.data)
        self.assertGreater(int(response.headers['Retry-After']), 60)
        create.assert_not_called()

    def test_other_ips_and_other_routes_remain_available(self):
        self.exhaust_signin()
        other = self.web.post('/signin', data={'csrf_token': self.token}, environ_overrides={'REMOTE_ADDR': '192.0.2.' + str(uuid4().int % 254 + 1)})
        self.assertEqual(other.status_code, 302)
        self.assertEqual(self.post('/signup').status_code, 302)
        for path in ('/signin', '/signup', '/forgot-password', '/api/health', '/about'):
            with self.subTest(path=path):
                self.assertEqual(self.web.get(path, environ_overrides={'REMOTE_ADDR': self.ip}).status_code, 200)
        self.assertEqual(self.web.get('/logout', environ_overrides={'REMOTE_ADDR': self.ip}).status_code, 200)

    def test_forwarded_headers_do_not_bypass_limit(self):
        self.exhaust_signin()
        response = self.post(headers={'X-Forwarded-For': '198.51.100.27', 'X-Real-IP': '198.51.100.28'})
        self.assertEqual(response.status_code, 429)

    def test_new_session_does_not_bypass_limit(self):
        self.exhaust_signin()
        other = app.test_client()
        response = other.post('/signin', data={'csrf_token': csrf_token(other)}, environ_overrides={'REMOTE_ADDR': self.ip})
        self.assertEqual(response.status_code, 429)

    def test_get_requests_do_not_consume_attempts(self):
        for _ in range(8):
            self.web.get('/signin', environ_overrides={'REMOTE_ADDR': self.ip})
        self.exhaust_signin()

    def test_minute_limit_expires(self):
        self.exhaust_signin()
        self.assertEqual(self.post().status_code, 429)
        with patch('time.time', return_value=time.time() + 65):
            self.assertEqual(self.post().status_code, 302)

    def test_hourly_limit_survives_minute_cooldowns(self):
        now = time.time()
        for minute in range(6):
            with patch('time.time', return_value=now + minute * 65):
                self.exhaust_signin()
        with patch('time.time', return_value=now + 6 * 65):
            response = self.post()
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response.headers['Retry-After']), 60)

    def test_valid_signin_below_limit_still_works(self):
        with patch('routes.get_user', return_value={'user_id': 1, 'password_hash': 'test-hash'}), \
                patch('routes.check_password_hash', return_value=True), \
                patch('routes.update_last_login'):
            response = self.post(data={'identifier': 'student', 'password': 'secret123'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/dashboard'))
        with self.web.session_transaction() as state:
            self.assertEqual(state['user_id'], 1)


if __name__ == '__main__':
    unittest.main()
