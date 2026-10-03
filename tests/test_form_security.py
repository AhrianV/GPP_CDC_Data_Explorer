"""Real CSRF validation across page forms, AJAX, uploads, and authentication."""
import io
import time
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
from werkzeug.datastructures import MultiDict
from app import app
from form_helpers import csrf_token, token_from_response


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = {'method': attrs.get('method', 'GET').upper(), 'tokens': []}
            self.forms.append(self.current)
        elif tag == 'input' and self.current is not None and attrs.get('name') == 'csrf_token':
            self.current['tokens'].append(attrs.get('value'))

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


class FormSecurityTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'instance' / 'tests'
        folder.mkdir(parents=True, exist_ok=True)
        database = folder / (uuid4().hex + '.db')
        self.addCleanup(lambda: database.unlink(missing_ok=True))
        config = patch.dict(app.config, TESTING=True, WORKSPACE_DATABASE_URL='sqlite:///' + database.as_posix())
        config.start()
        self.addCleanup(config.stop)
        self.web = app.test_client()
        self.ip = '10.' + '.'.join(str(n) for n in uuid4().bytes[:3])
        self.patch('routes.get_user', return_value={'user_id': 1, 'username': 'Student', 'avatar': 'blue', 'password_hash': 'test'})
        self.avatar = self.patch('routes.update_avatar', return_value=True)
        self.create = self.patch('routes.create_user', return_value=None)
        self.hash = self.patch('routes.generate_password_hash', return_value='hashed')
        self.api = Mock()
        self.api.with_options.return_value = self.api
        self.api.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content='Analysis <script>bad()</script>'))])
        self.patch('routes.client', self.api)
        self.patch('dataset_workspace.get_client', return_value=self.api)
        self.patch('routes.cache_ready.is_set', return_value=True)
        frame = pd.DataFrame([dict(date='2024-01-01', avg_vaccination_rate=50, state='CA',
                                   product_name='Milk', energy_kcal=60, protein_g=3, carbohydrates_g=5, fat_g=2)])
        for function in ('get_vaccination_by_date', 'get_vaccination_by_state_time', 'get_disease_cases_over_time', 'get_nutrition_data'):
            self.patch('routes.' + function, side_effect=lambda: frame.copy())
        self.patch('routes.get_cumulative_disease_cases', return_value=(frame, 2024))
        for function in ('create_vac_by_state_fig', 'create_vac_by_map_fig', 'display_disease_cases_over_time', 'display_cumulative_disease_cases_graph'):
            self.patch('routes.' + function, return_value='<div>Chart</div>')
        self.patch('routes.update_graph_layout')
        for function in ('line', 'bar', 'choropleth'):
            self.patch('routes.px.' + function, side_effect=lambda *args, **kwargs: SimpleNamespace(
                update_layout=Mock(), to_html=Mock(return_value='<div>Chart</div>'),
                layout=SimpleNamespace(title=SimpleNamespace(text=kwargs.get('title')))))
        self.prompt = self.patch('routes.create_prompt', return_value='Server-selected chart data')
        self.patch('routes.convert_df', side_effect=lambda df: df.to_json(orient='records', date_format='iso'))
        with self.web.session_transaction() as state:
            state['user_id'] = 1
        self.token = csrf_token(self.web)

    def patch(self, name, *args, **kwargs):
        patcher = patch(name, *args, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def post(self, path, data=None, **kwargs):
        return self.web.post(path, data={'csrf_token': self.token, **(data or {})},
                             environ_overrides={'REMOTE_ADDR': self.ip}, **kwargs)

    def test_all_page_forms_render_one_signed_token(self):
        for path in ('/', '/about', '/signin', '/signup', '/forgot-password', '/logout',
                     '/dashboard', '/vaccinations', '/diseases', '/nutrition'):
            with self.subTest(path=path):
                response = self.web.get(path)
                self.assertEqual(response.status_code, 200)
                forms = Forms()
                forms.feed(response.get_data(as_text=True))
                for form in forms.forms:
                    if form['method'] == 'POST':
                        self.assertEqual(form['tokens'], [token_from_response(response)])
                self.assertIn('no-store', response.headers['Cache-Control'])
        self.api.chat.completions.create.assert_not_called()

    def test_all_state_changing_routes_reject_missing_tokens(self):
        for path in ('/signin', '/signup', '/logout', '/profile/avatar', '/vaccinations', '/diseases',
                     '/nutrition', '/dashboard/upload', '/dashboard/datasets/1/analyze', '/charts/disease-trends/favorite'):
            with self.subTest(path=path):
                response = self.web.post(path, data={'avatar': 'green'}, environ_overrides={'REMOTE_ADDR': self.ip})
                self.assertEqual(response.status_code, 400)
        self.avatar.assert_not_called()
        self.create.assert_not_called()
        self.api.chat.completions.create.assert_not_called()

    def test_cross_session_and_expired_tokens_are_rejected(self):
        other = app.test_client()
        self.assertEqual(other.post('/logout', data={'csrf_token': self.token}).status_code, 400)
        with patch('time.time', return_value=time.time() + 3605):
            self.assertEqual(self.post('/profile/avatar', {'avatar': 'green'}).status_code, 400)
        self.avatar.assert_not_called()

    def test_ajax_errors_are_json_and_header_tokens_work(self):
        response = self.web.post('/charts/disease-trends/favorite', data={'action': 'save'}, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('expired', response.json['error'])
        response = self.web.post('/charts/disease-trends/favorite', data={'action': 'save'},
                                 headers={'Accept': 'application/json', 'X-CSRFToken': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['saved'])

    def test_logout_get_is_read_only_and_post_ends_session(self):
        self.assertEqual(self.web.get('/logout').status_code, 200)
        with self.web.session_transaction() as state:
            self.assertEqual(state['user_id'], 1)
        self.assertEqual(self.post('/logout').status_code, 302)
        with self.web.session_transaction() as state:
            self.assertNotIn('user_id', state)

    def test_avatar_redirects_only_to_known_pages(self):
        for target in ('https://evil.example', '//evil.example', '/\\evil.example', '/%2f%2fevil.example', '/signin\r\nX-Test: yes'):
            with self.subTest(target=target):
                response = self.post('/profile/avatar', {'avatar': 'green', 'next': target})
                self.assertEqual(response.location, '/dashboard')
        self.assertEqual(self.post('/profile/avatar', {'avatar': 'blue', 'next': '/nutrition'}).location, '/nutrition')

    def test_malformed_fields_do_not_create_accounts_or_hash_passwords(self):
        variants = [{}, {'username': 'ab', 'password': 'longenough'},
                    {'username': 'valid', 'password': 'tiny'},
                    {'username': 'valid', 'password': 'a' * 257},
                    {'username': 'valid', 'password': 'longenough', 'email': 'invalid'}]
        for data in variants:
            response = self.post('/signup', {'educational_acknowledgment': 'accepted', **data})
            self.assertEqual(response.status_code, 302)
        self.create.assert_not_called()
        self.hash.assert_not_called()

    def test_duplicate_fields_and_large_bodies_are_rejected(self):
        response = self.web.post('/profile/avatar', data=MultiDict([
            ('csrf_token', self.token), ('avatar', 'blue'), ('avatar', 'green')]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post('/profile/avatar', {'avatar': 'a' * 70000}).status_code, 413)
        self.avatar.assert_not_called()

    def test_login_rotates_token_and_old_forms_cannot_submit(self):
        with patch('routes.check_password_hash', return_value=True), patch('routes.update_last_login'):
            self.assertEqual(self.post('/signin', {'identifier': 'student', 'password': 'valid-password'}).status_code, 302)
        self.assertEqual(self.post('/profile/avatar', {'avatar': 'green'}).status_code, 400)
        self.token = csrf_token(self.web)
        self.assertEqual(self.post('/profile/avatar', {'avatar': 'green'}).status_code, 302)

    def test_all_chart_analyses_work_via_post_and_escape_output(self):
        for path, graphs in [('/vaccinations', ('over_time', 'state_time_bar', 'state_time_map')),
                             ('/diseases', ('over_time', 'cumulative_cases')),
                             ('/nutrition', ('nutrition_over_time', 'nutrition_state_bar', 'nutrition_state_map'))]:
            for graph in graphs:
                with self.subTest(path=path, graph=graph):
                    response = self.post(path, {'data': graph, 'graph-title': 'attacker title'})
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b'Analysis &lt;script&gt;bad()&lt;/script&gt;', response.data)
                    self.assertNotEqual(self.prompt.call_args.args[0], 'attacker title')
        with self.web.session_transaction() as state:
            for key in ('prompt_data', 'ai_response', 'graph_id'):
                self.assertNotIn(key, state)
        self.assertEqual(self.api.chat.completions.create.call_count, 8)

    def test_unknown_chart_selectors_and_legacy_get_do_not_call_ai(self):
        for path in ('/vaccinations', '/diseases', '/nutrition'):
            self.assertEqual(self.post(path, {'data': 'unknown'}).status_code, 200)
        self.assertEqual(self.web.get('/ai-analysis').location, '/dashboard')
        self.api.chat.completions.create.assert_not_called()

    def test_valid_multipart_upload_still_works(self):
        # Uploads retain their larger limit; ordinary forms are capped at 64 KiB.
        data = b'name,value\n' + (b'a' * 40 + b',1\n') * 3000
        response = self.post('/dashboard/upload', {'dataset': (io.BytesIO(data), 'data.csv')})
        self.assertEqual(response.status_code, 302)
        self.assertIn('dataset=', response.location)
        self.assertIn(b'Analysis &lt;script&gt;', self.web.get(response.location).data)


if __name__ == '__main__':
    unittest.main()
