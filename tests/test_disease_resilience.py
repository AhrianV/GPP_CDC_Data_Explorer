"""CDC outages, malformed data, and empty charts must not break the page."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from flask import Flask
import pandas as pd
import requests

from app import app
from cache import cache
from disease_data import DiseaseDataUnavailable, _fetch_rows, get_disease_data
from disease_functions import get_disease_cases_over_time, get_cumulative_disease_cases
from form_helpers import csrf_token


ROWS = [
    {"year": "2024", "week": "1", "label": "Tuberculosis", "m1": "4", "m3": "4"},
    {"year": "2024", "week": "2", "label": "Tuberculosis", "m1": "6", "m3": "10"},
    # CDC omits suppressed/null fields rather than always returning keys.
    {"year": "2024", "week": "2", "label": "Anthrax"},
]


def response(rows):
    return Mock(json=Mock(return_value=rows), raise_for_status=Mock())


class DiseaseLoaderTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'instance' / 'tests'
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (uuid4().hex + '.json')
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        self.app = Flask(__name__)
        self.app.config["DISEASE_CACHE_PATH"] = str(self.path)
        cache.init_app(self.app)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.get = patch('disease_data.requests.get').start()
        self.addCleanup(patch.stopall)
        self.get.return_value = response(ROWS)

    def test_both_charts_share_one_fetch_and_persist_valid_data(self):
        monthly = get_disease_cases_over_time()
        cumulative, year = get_cumulative_disease_cases()
        self.assertEqual(monthly.m1.sum(), 10)
        self.assertEqual(cumulative.m3.tolist(), [10])
        self.assertEqual(year, 2024)
        self.assertFalse(monthly.attrs['stale'])
        self.get.assert_called_once()
        self.assertEqual(self.get.call_args.kwargs['timeout'], (3, 8))
        self.assertNotIn('auth', self.get.call_args.kwargs)
        self.assertTrue(self.path.exists())
        cache.clear()
        get_disease_data()
        self.get.assert_called_once()  # Survives loss of the in-memory cache.

    def test_expired_disk_snapshot_survives_timeout_with_cooldown(self):
        old = {"rows": ROWS, "fetched_at": time.time() - 90000}
        self.path.write_text(json.dumps(old))
        self.get.side_effect = requests.Timeout('upstream timeout')
        with self.assertLogs(self.app.logger, level='WARNING'):
            frame = get_disease_data()
        self.assertTrue(frame.attrs['stale'])
        self.assertEqual(frame.attrs['fetched_at'], old['fetched_at'])
        get_disease_data()
        self.get.assert_called_once()
        self.assertEqual(json.loads(self.path.read_text()), old)

    def test_bad_responses_do_not_replace_saved_data(self):
        for payload in ({'error': 'Unauthorized'}, [], [{'year': '2024'}],
                        [{'year': 'bad', 'week': '99', 'label': 'Tuberculosis', 'm1': 'x'}]):
            with self.subTest(payload=payload):
                cache.clear()
                self.get.return_value = response(payload)
                with self.assertLogs(self.app.logger, level='WARNING'):
                    with self.assertRaises(DiseaseDataUnavailable):
                        get_disease_data()
                self.assertFalse(self.path.exists())

    def test_http_failure_is_checked_before_json(self):
        self.get.return_value.raise_for_status.side_effect = requests.HTTPError('503')
        with self.assertLogs(self.app.logger, level='WARNING'):
            with self.assertRaises(DiseaseDataUnavailable):
                get_disease_data()
        self.get.return_value.json.assert_not_called()

    def test_invalid_refresh_preserves_last_successful_snapshot(self):
        old = {"rows": ROWS, "fetched_at": time.time() - 90000}
        self.path.write_text(json.dumps(old))
        self.get.return_value = response({'error': 'upstream failure'})
        with self.assertLogs(self.app.logger, level='WARNING'):
            result = get_disease_data()
        self.assertTrue(result.attrs['stale'])
        self.assertEqual(result.m1.dropna().sum(), 10)
        self.assertEqual(json.loads(self.path.read_text()), old)

    def test_concurrent_refresh_serves_saved_data_without_another_request(self):
        from disease_data import _refresh_lock
        self.path.write_text(json.dumps({"rows": ROWS, "fetched_at": time.time() - 90000}))
        with _refresh_lock:
            result = get_disease_data()
        self.assertTrue(result.attrs['stale'])
        self.get.assert_not_called()

    def test_pagination_downloads_every_page(self):
        self.get.side_effect = [response(ROWS[:2]), response(ROWS[2:])]
        with patch('disease_data.PAGE_SIZE', 2):
            self.assertEqual(_fetch_rows(), ROWS)
        self.assertEqual([call.kwargs['params']['$offset'] for call in self.get.call_args_list], [0, 2])

    def test_empty_chart_data_is_reported_explicitly(self):
        frame = pd.DataFrame([dict(year=2024, week=1, label='Unknown disease', m1=3, m3=3)])
        with patch('disease_functions.get_disease_data', return_value=frame):
            for loader in (get_disease_cases_over_time, get_cumulative_disease_cases):
                with self.assertRaises(DiseaseDataUnavailable):
                    loader()


class DiseasePageTests(unittest.TestCase):
    def setUp(self):
        self.web = app.test_client()
        with self.web.session_transaction() as state:
            state['user_id'] = 1
        for target, value in [('routes.get_user', {'username': 'Student', 'avatar': 'blue'}),
                              ('routes.favorites_context', {})]:
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.monthly = pd.DataFrame([dict(month='2024-01', disease_group='Tuberculosis', m1=10)])
        self.cumulative = pd.DataFrame([dict(disease_group='Tuberculosis', m3=10)])

    def test_one_chart_failure_keeps_other_chart_visible(self):
        token = csrf_token(self.web)
        with patch('routes.get_disease_cases_over_time', side_effect=requests.Timeout()), \
                patch('routes.get_cumulative_disease_cases', return_value=(self.cumulative, 2024)), \
                self.assertLogs(app.logger, level='ERROR'):
            result = self.web.post('/diseases', data={'csrf_token': token})
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'Chart temporarily unavailable', result.data)
        self.assertIn(b'Cumulative Disease Cases', result.data)
        self.assertNotIn(b'value="over_time"', result.data)
        self.assertIn(b'value="cumulative_cases"', result.data)

    def test_total_outage_renders_retry_and_blocks_analysis(self):
        token = csrf_token(self.web)
        with patch('routes.get_disease_cases_over_time', side_effect=DiseaseDataUnavailable()), \
                patch('routes.get_cumulative_disease_cases', side_effect=DiseaseDataUnavailable()), \
                patch('routes.analyze_public_chart') as analyze, self.assertLogs(app.logger, level='ERROR'):
            result = self.web.post('/diseases', data={'csrf_token': token, 'data': 'over_time'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data.count(b'Retry loading data'), 2)
        self.assertNotIn(b'AI Analyze', result.data)
        analyze.assert_not_called()

    def test_stale_data_is_labeled(self):
        token = csrf_token(self.web)
        self.monthly.attrs.update(stale=True, fetched_at=1704067200)
        with patch('routes.get_disease_cases_over_time', return_value=self.monthly), \
                patch('routes.get_cumulative_disease_cases', return_value=(self.cumulative, 2024)):
            result = self.web.post('/diseases', data={'csrf_token': token})
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'Showing saved data fetched 2024-01-01 00:00 UTC', result.data)


if __name__ == '__main__':
    unittest.main()
