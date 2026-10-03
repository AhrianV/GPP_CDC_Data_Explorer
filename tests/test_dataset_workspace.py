"""Dataset import and account isolation tests; no external API or real user writes."""
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from werkzeug.datastructures import FileStorage

from app import app
from form_helpers import csrf_token, token_from_response
from dataset_workspace import MAX_BYTES, parse_upload, profile_dataset


class DatasetParsingTests(unittest.TestCase):
    def parse(self, text, filename='sample.csv'):
        return parse_upload(FileStorage(stream=io.BytesIO(text.encode()), filename=filename))[1]

    def test_counts_missing_values_and_histograms_use_all_rows(self):
        df = self.parse('region,cases\nNorth,10\nSouth,30\nNorth,\nSouth,20\n')
        result = profile_dataset(df)
        self.assertEqual(result['rows'], 4)
        self.assertEqual(result['missing_total'], 1)
        self.assertEqual(result['numeric']['cases']['mean'], 20)
        self.assertEqual(sum(result['numeric']['cases']['histogram']['counts']), 3)
        self.assertEqual(result['categories']['region']['counts'], [2, 2])

    def test_tsv_json_and_single_value(self):
        for filename, text in [('sample.tsv', 'name\tvalue\na\t5\nb\t5'),
                               ('sample.json', '[{"name":"a","value":5},{"name":"b","value":5}]')]:
            with self.subTest(filename=filename):
                result = profile_dataset(self.parse(text, filename))
                self.assertEqual(result['numeric']['value']['histogram']['counts'], [2])

    def test_invalid_files_are_rejected(self):
        cases = [('a,a\n1,2', 'x.csv'), ('a,b\n1,2,3', 'x.csv'), ('a\n', 'x.csv'),
                 ('[]', 'x.json'), ('{}', 'x.json'), ('[{"a": {"b":1}}]', 'x.json'),
                 ('a,b\n1,2', 'x.exe'), ('a\n1', 'x.xlsx'), ('a\n1', 'x'),
                 ('a, \n1,2', 'x.csv'), ('a\n"unterminated', 'x.csv')]
        for text, filename in cases:
            with self.subTest(filename=filename, text=text), self.assertRaises(ValueError):
                self.parse(text, filename)

    def test_limits_and_nonfinite_numbers(self):
        for text in ('a\n' + 'x\n' * 50001, ','.join('c' + str(i) for i in range(41)) + '\n' + ','.join('1' for _ in range(41)), 'a\n' + 'x' * MAX_BYTES):
            with self.assertRaises(ValueError):
                self.parse(text)
        for value in ('inf', '1e101', '-Infinity'):
            with self.assertRaises(ValueError):
                profile_dataset(self.parse('a\n' + value))

    def test_preview_is_limited_and_na_category_is_preserved(self):
        result = profile_dataset(self.parse('region\n' + 'NA\n' * 20))
        self.assertEqual(len(result['preview']), 10)
        self.assertEqual(result['categories']['region']['labels'], ['NA'])
        self.assertEqual(result['missing_total'], 0)


class WorkspaceRoutesTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / 'instance' / 'tests'
        test_root.mkdir(parents=True, exist_ok=True)
        database = test_root / (uuid4().hex + '.db')
        self.addCleanup(lambda: database.unlink(missing_ok=True))
        self.config = patch.dict(app.config, TESTING=True,
                                 WORKSPACE_DATABASE_URL='sqlite:///' + database.as_posix())
        self.config.start()
        self.addCleanup(self.config.stop)
        self.user_patch = patch('routes.get_user', return_value={'user_id': 1, 'username': 'Test', 'avatar': 'blue'})
        self.user_patch.start()
        self.addCleanup(self.user_patch.stop)
        self.api = Mock()
        self.api.with_options.return_value = self.api
        self.api.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='Findings\nThree rows. <script>alert(1)</script>'))])
        self.client_patch = patch('dataset_workspace.get_client', return_value=self.api)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.web = app.test_client()
        self.signin(1)

    def signin(self, user_id):
        with self.web.session_transaction() as session:
            session.clear()
            session['user_id'] = user_id
        response = self.web.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.token = token_from_response(response)

    def upload(self, text=b'region,cases,rate\nNorth,10,2\nSouth,20,3\nNorth,30,4', filename='cases.csv'):
        return self.web.post('/dashboard/upload', data={
            'csrf_token': self.token, 'dataset': (io.BytesIO(text), filename)}, follow_redirects=True)

    def test_empty_dashboard_has_compact_links_and_no_sample_content(self):
        html = self.web.get('/dashboard').get_data(as_text=True)
        self.assertIn('Your next insight starts here', html)
        self.assertNotIn('Data Exploration Tools', html)
        self.assertNotIn('Sample activity', html)
        self.assertLess(html.index('Workspace overview'), html.index('Additional dashboards'))
        self.assertLess(html.index('Additional dashboards'), html.index('Workspace metrics'))

    def test_upload_renders_charts_analysis_and_persists_on_reload(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Numeric distribution', html)
        self.assertIn('cases.csv', html)
        self.assertIn('Three rows. &lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('Median 20', html)
        self.assertIn('Findings', self.web.get('/dashboard').get_data(as_text=True))
        messages = self.api.chat.completions.create.call_args.kwargs['messages']
        payload = json.loads(messages[1]['content'])
        self.assertEqual(payload['rows'], 3)
        self.assertNotIn('preview', payload)
        self.api.chat.completions.create.assert_called_once()

    def test_provider_failure_preserves_data_and_retry_works(self):
        self.api.chat.completions.create.side_effect = RuntimeError('private-provider-details')
        response = self.upload()
        self.assertIn(b'Retry analysis', response.data)
        self.assertIn(b'Median 20', response.data)
        self.assertNotIn(b'private-provider-details', response.data)
        self.api.chat.completions.create.side_effect = None
        response = self.web.post('/dashboard/datasets/1/analyze', data={'csrf_token': self.token}, follow_redirects=True)
        self.assertIn(b'Three rows.', response.data)
        self.assertNotIn(b'Retry analysis', response.data)

    def test_missing_key_and_empty_completion_show_retry(self):
        for mode in ('key', 'empty'):
            with self.subTest(mode=mode):
                if mode == 'key':
                    with patch('dataset_workspace.get_client', side_effect=RuntimeError('Missing key')):
                        response = self.upload()
                else:
                    self.api.chat.completions.create.return_value.choices[0].message.content = ' '
                    response = self.upload()
                self.assertIn(b'Retry analysis', response.data)

    def test_other_account_cannot_read_or_analyze_dataset(self):
        self.upload()
        self.signin(2)
        response = self.web.get('/dashboard')
        self.assertNotIn(b'cases.csv', response.data)
        self.assertEqual(self.web.get('/dashboard?dataset=1').status_code, 404)
        self.assertEqual(self.web.post('/dashboard/datasets/1/analyze', data={'csrf_token': self.token}).status_code, 404)
        self.api.chat.completions.create.assert_called_once()

    def test_csrf_and_authentication_are_required(self):
        for token in ('', 'wrong', '\u2603'):
            response = self.web.post('/dashboard/upload', data={'csrf_token': token, 'dataset': (io.BytesIO(b'a\n1'), 'x.csv')})
            self.assertEqual(response.status_code, 400)
        with self.web.session_transaction() as session:
            session.clear()
        token = csrf_token(self.web)
        for path in ('/dashboard/upload', '/dashboard/datasets/1/analyze'):
            response = self.web.post(path, data={'csrf_token': token})
            self.assertEqual(response.status_code, 302)
            self.assertIn('/signin', response.location)
        self.api.chat.completions.create.assert_not_called()

    def test_invalid_and_oversize_uploads_do_not_call_groq(self):
        for text, filename in [(b'a,a\n1,2', 'x.csv'), (b'[]', 'x.json'), (b'a\n' + b'x' * (MAX_BYTES + 150000), 'big.csv')]:
            with self.subTest(filename=filename):
                self.assertEqual(self.upload(text, filename).status_code, 413 if filename == 'big.csv' else 200)
        self.api.chat.completions.create.assert_not_called()

    def test_switching_columns_and_datasets(self):
        self.upload()
        self.upload(b'other\n42', 'other.csv')
        response = self.web.get('/dashboard?dataset=1&numeric=rate')
        self.assertIn(b'Median 3', response.data)
        response = self.web.get('/dashboard?dataset=2')
        self.assertIn(b'Median 42', response.data)

    def test_text_only_and_html_values_are_safe(self):
        response = self.upload(b'label\n<script>alert(1)</script>', 'text.csv')
        self.assertIn(b'No numeric columns', response.data)
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;', response.data)
        self.assertNotIn(b'<script>alert(1)</script>', response.data)


if __name__ == '__main__':
    unittest.main()
