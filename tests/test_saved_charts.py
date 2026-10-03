"""Saved-chart persistence, deep links, and account isolation."""
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from flask import render_template, session
from app import app
from form_helpers import csrf_token, token_from_response
from saved_charts import CHARTS


class SavedChartsTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'instance' / 'tests'
        folder.mkdir(parents=True, exist_ok=True)
        database = folder / (uuid4().hex + '.db')
        self.addCleanup(lambda: database.unlink(missing_ok=True))
        config = patch.dict(app.config, TESTING=True, WORKSPACE_DATABASE_URL='sqlite:///' + database.as_posix())
        config.start()
        self.addCleanup(config.stop)
        user = patch('routes.get_user', return_value={'username': 'Student', 'avatar': 'blue'})
        user.start()
        self.addCleanup(user.stop)
        self.web = app.test_client()
        self.signin(1)

    def signin(self, user_id):
        with self.web.session_transaction() as state:
            state.clear()
            state['user_id'] = user_id
        self.token = token_from_response(self.web.get('/dashboard'))

    def change(self, chart='vaccination-trends', action='save', **kwargs):
        return self.web.post('/charts/' + chart + '/favorite',
                             data={'csrf_token': self.token, 'action': action, **kwargs},
                             headers={'Accept': 'application/json'})

    def test_save_is_persistent_and_idempotent(self):
        for _ in range(2):
            response = self.change()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['saved'])
        html = self.web.get('/dashboard').get_data(as_text=True)
        self.assertEqual(html.count('href="/vaccinations#vaccination-trends"'), 1)
        self.signin(1)
        self.assertIn(b'/vaccinations#vaccination-trends', self.web.get('/dashboard').data)

    def test_remove_updates_dashboard_and_empty_state(self):
        self.change()
        response = self.web.post('/charts/vaccination-trends/favorite', data={
            'csrf_token': self.token, 'action': 'remove', 'return_to': 'dashboard'})
        self.assertTrue(response.location.endswith('/dashboard#saved-charts'))
        html = self.web.get('/dashboard').get_data(as_text=True)
        self.assertNotIn('href="/vaccinations#vaccination-trends"', html)
        self.assertIn('Your shortcuts will appear here', html)

    def test_accounts_are_isolated(self):
        self.change()
        self.signin(2)
        self.assertNotIn(b'/vaccinations#vaccination-trends', self.web.get('/dashboard').data)
        self.change(action='remove')
        self.signin(1)
        self.assertIn(b'/vaccinations#vaccination-trends', self.web.get('/dashboard').data)

    def test_invalid_requests_cannot_change_favorites(self):
        self.assertEqual(self.change(chart='unknown').status_code, 404)
        self.assertEqual(self.change(action='unknown').status_code, 400)
        self.token = 'invalid'
        self.assertEqual(self.change().status_code, 400)
        with self.web.session_transaction() as state:
            state.clear()
        self.token = csrf_token(self.web)
        self.assertIn('/signin', self.change().location)

    def test_every_saved_link_targets_an_existing_chart(self):
        templates = {'vaccination_page': ('/vaccinations', 'vaccinations.html'),
                     'disease_page': ('/diseases', 'diseases.html'),
                     'nutrition_page': ('/nutrition', 'nutrition.html')}
        for chart, (endpoint, title, _, _) in CHARTS.items():
            with self.subTest(chart=chart):
                self.change(chart=chart)
                path, template = templates[endpoint]
                with app.test_request_context(path):
                    session['user_id'] = 1
                    html = render_template(template)
                self.assertIn('id="' + chart + '"', html)
                self.assertIn('aria-label="Remove saved chart: ' + title + '"', html)
                self.assertIn(path + '#' + chart, self.web.get('/dashboard').get_data(as_text=True))

    def test_no_javascript_fallback_redirects_to_chart(self):
        response = self.web.post('/charts/disease-totals/favorite', data={
            'csrf_token': self.token, 'action': 'save', 'return_to': 'https://example.com'})
        self.assertTrue(response.location.endswith('/diseases#disease-totals'))

    def test_about_lists_the_student_team_without_placeholder_roles(self):
        html = self.web.get('/about').get_data(as_text=True)
        for name in ('Adrian', 'Ahrian Vemuri', 'Akshat Parekh', 'James Seudieu'):
            self.assertIn('<h3>' + name + '</h3>', html)
        self.assertEqual(html.count('Student at Group Project Program'), 4)
        self.assertIn('CodeWizardsHQ Group Project Program', html)
        self.assertNotIn('Lorem ipsum', html)
        for name, role in [('Adrian', 'Frontend Developer'), ('James Seudieu', 'Frontend Developer'),
                           ('Ahrian Vemuri', 'Full Stack Developer'), ('Akshat Parekh', 'Full Stack Developer')]:
            self.assertIn('<h3>' + name + '</h3><p>' + role + '</p>', html)


if __name__ == '__main__':
    unittest.main()
