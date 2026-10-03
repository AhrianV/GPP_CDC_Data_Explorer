"""The page shell must load without CDC or the vaccination warming thread."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from app import app
from form_helpers import csrf_token


class PublicDataTests(unittest.TestCase):
    def setUp(self):
        self.web = app.test_client()
        with self.web.session_transaction() as session:
            session['user_id'] = 1
        for name, value in [('routes.get_user', {'username': 'Student', 'avatar': 'blue'}),
                            ('routes.favorites_context', {})]:
            patcher = patch(name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_pages_render_without_any_cdc_requests(self):
        with patch('requests.get', side_effect=AssertionError('No network in page request')), \
                patch('requests.post', side_effect=AssertionError('No network in page request')), \
                patch('routes.cache_ready.is_set', return_value=False):
            for page in ('diseases', 'vaccinations'):
                result = self.web.get('/' + page)
                self.assertEqual(result.status_code, 200)
                self.assertIn(b'Load without recent data', result.data)
                self.assertIn(b'cdc-demo-data.js', result.data)
                self.assertIn(b'vendor/plotly.min.js', result.data)
                self.assertNotIn(b'checkStatus', result.data)

    def test_workspace_failure_does_not_block_demo(self):
        with patch('routes.favorites_context', side_effect=sqlite3.OperationalError('read-only database')), \
                self.assertLogs(app.logger, level='ERROR'):
            for page in ('diseases', 'vaccinations'):
                result = self.web.get('/' + page)
                self.assertEqual(result.status_code, 200)
                self.assertIn(b'Saved charts are temporarily unavailable', result.data)
                self.assertIn(b'Load without recent data', result.data)

    def test_api_failure_returns_recoverable_json(self):
        with patch('routes.get_chart_payload', side_effect=ValueError('upstream unavailable')), \
                self.assertLogs(app.logger, level='ERROR'):
            result = self.web.get('/api/public-charts/diseases')
        self.assertEqual(result.status_code, 503)
        self.assertIn('saved demo data', result.json['error'])

    def test_api_requires_login_and_rejects_unknown_pages(self):
        self.assertEqual(self.web.get('/api/public-charts/invalid').status_code, 404)
        with self.web.session_transaction() as session:
            session.clear()
        self.assertEqual(self.web.get('/api/public-charts/diseases').status_code, 302)

    def test_api_returns_chart_payload(self):
        payload = {'charts': {'example': {'data': [], 'layout': {}}}}
        with patch('routes.get_chart_payload', return_value=payload):
            result = self.web.get('/api/public-charts/vaccinations')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json, payload)

    def test_vaccination_analysis_failure_returns_demo_shell(self):
        token = csrf_token(self.web)
        with patch('routes.get_vaccination_by_date', side_effect=ValueError('empty CDC data')), \
                self.assertLogs(app.logger, level='ERROR'):
            result = self.web.post('/vaccinations', data={'csrf_token': token, 'data': 'over_time'})
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'Load without recent data', result.data)

    def test_checked_in_snapshot_has_all_charts_and_provenance(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'static/js/cdc-demo-data.js').read_text(encoding='utf-8')
        payload = json.loads(source.split('window.CDC_DEMO_DATA = ', 1)[1].removesuffix(';\n'))
        for page, count in [('diseases', 2), ('vaccinations', 3)]:
            self.assertEqual(len(payload[page]['charts']), count)
            self.assertTrue(payload[page]['source'].startswith('https://data.cdc.gov/'))
            self.assertTrue(payload[page]['captured_at'])
            for chart in payload[page]['charts'].values():
                self.assertTrue(chart['data'])
        topology = json.loads((root / 'static/vendor/usa_110m.json').read_text())
        self.assertEqual(topology['type'], 'Topology')


if __name__ == '__main__':
    unittest.main()
