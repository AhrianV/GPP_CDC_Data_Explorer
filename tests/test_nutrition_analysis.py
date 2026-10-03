"""Exercise the nutrition route in isolation, without database or external API access."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pandas as pd
import plotly.express as px
from flask import Flask, flash, render_template, request
from form_security import init_form_security
from form_helpers import csrf_token


class NutritionAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        self.app.secret_key = 'test-only'
        init_form_security(self.app)
        self.api = Mock()
        self.api.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='Chart analysis <script>unsafe</script>'))]
        )
        data = pd.DataFrame([
            dict(date='2024-01-01', product_name='Milk', energy_kcal=40, protein_g=3, carbohydrates_g=5, fat_g=1),
            dict(date='2024-01-01', product_name='Eggs', energy_kcal=160, protein_g=13, carbohydrates_g=1, fat_g=11),
        ])
        self.env = dict(app=self.app, request=request, flash=flash, render_template=render_template,
                        pd=pd, px=px, client=self.api, get_nutrition_data=lambda: data.copy(),
                        convert_df=lambda df: df.to_json(orient='records'), create_prompt=Mock(return_value='prompt'))
        # Load the real route without app startup, database writes, or network imports.
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'routes.py').read_text(encoding='utf-8'))
        route = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'nutrition_page')
        route.decorator_list = []
        exec(compile(ast.Module(body=[route], type_ignores=[]), 'routes.py', 'exec'), self.env)
        self.app.add_url_rule('/nutrition', 'nutrition_page', self.env['nutrition_page'], methods=['GET', 'POST'])
        self.app.add_url_rule('/charts/<chart_id>/favorite', 'chart_favorite', lambda chart_id: '', methods=['POST'])
        for endpoint in ('home', 'dashboard', 'about', 'signin', 'signup', 'vaccination_page', 'disease_page'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')
        self.web = self.app.test_client()
        self.token = csrf_token(self.web, '/nutrition')

    def test_each_chart_renders_its_own_analysis(self):
        import json
        for index, graph in enumerate(('nutrition_over_time', 'nutrition_state_bar', 'nutrition_state_map')):
            with self.subTest(graph=graph):
                response = self.web.post('/nutrition', data={'csrf_token': self.token, 'data': graph, 'graph-title': 'untrusted title'})
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                panels = html.split('<!-- Panel ')[1:]
                for panel_index, panel in enumerate(panels):
                    self.assertEqual('AI Generated' in panel, panel_index == index)
                self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
                self.assertIn('<header', html)
                self.assertIn('<footer', html)
                title, records = self.env['create_prompt'].call_args.args
                self.assertNotEqual(title, 'untrusted title')
                if index == 0:
                    self.assertEqual(json.loads(records)[0]['energy_kcal'], 100)
                messages = self.api.chat.completions.create.call_args.kwargs['messages']
                self.assertIn('demonstration', messages[0]['content'])

    def test_missing_client_keeps_page_and_retry_buttons(self):
        self.env['client'] = None
        response = self.web.post('/nutrition', data={'csrf_token': self.token, 'data': 'nutrition_state_map'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'currently unavailable', response.data)
        self.assertEqual(response.get_data(as_text=True).count('type="submit">AI Analyze'), 3)

    def test_provider_failure_and_empty_response(self):
        self.api.chat.completions.create.side_effect = RuntimeError('provider unavailable')
        response = self.web.post('/nutrition', data={'csrf_token': self.token, 'data': 'nutrition_over_time'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'could not analyze', response.data)
        self.api.chat.completions.create.side_effect = None
        self.api.chat.completions.create.return_value.choices[0].message.content = ' '
        response = self.web.post('/nutrition', data={'csrf_token': self.token, 'data': 'nutrition_over_time'})
        self.assertIn(b'could not analyze', response.data)

    def test_invalid_graph_does_not_call_ai(self):
        response = self.web.post('/nutrition', data={'csrf_token': self.token, 'data': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Choose a nutrition chart', response.data)
        self.api.chat.completions.create.assert_not_called()

    def test_get_does_not_call_ai(self):
        self.assertEqual(self.web.get('/nutrition').status_code, 200)
        self.api.chat.completions.create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
