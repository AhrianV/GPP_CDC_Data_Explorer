"""Verify sign-up requires explicit acknowledgment, including direct POSTs."""
import unittest
from unittest.mock import patch

from app import app
from form_helpers import csrf_token


class SignupDisclaimerTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.details = {'username': 'signup-test', 'password': 'secret123', 'email': '', 'csrf_token': csrf_token(self.client)}

    def test_checkbox_is_required_and_not_preselected(self):
        html = self.client.get('/signup').get_data(as_text=True)
        checkbox = next(tag for tag in html.split('>') if '<input' in tag and 'educational_acknowledgment' in tag)
        self.assertIn('required', checkbox)
        self.assertNotIn('checked', checkbox)
        self.assertIn('CodeWizardsHQ, its students, and instructors', html)

    @patch('routes.create_user')
    def test_missing_or_invalid_acknowledgment_prevents_account_creation(self, create):
        for value in (None, '', 'false', 'on'):
            with self.subTest(value=value):
                data = dict(self.details)
                if value is not None:
                    data['educational_acknowledgment'] = value
                response = self.client.post('/signup', data=data, follow_redirects=True)
                self.assertIn(b'Please acknowledge the educational project disclaimer', response.data)
        create.assert_not_called()

    @patch('routes.get_user', return_value=None)
    @patch('routes.create_user', return_value=None)
    def test_acknowledged_signup_can_create_account(self, create, lookup):
        response = self.client.post('/signup', data={**self.details, 'educational_acknowledgment': 'accepted'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/signin'))
        create.assert_called_once()


if __name__ == '__main__':
    unittest.main()
