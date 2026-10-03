"""Account-scoped bookmarks for the app's public-data charts."""
from contextlib import closing
from datetime import datetime, timezone

from flask import abort, jsonify, redirect, request, session, url_for

from dataset_workspace import connect


CHARTS = {
    'vaccination-trends': ('vaccination_page', 'Vaccination trends', 'COVID-19 vaccinations', 'bi-graph-up-arrow'),
    'vaccination-states': ('vaccination_page', 'Vaccination coverage by state', 'COVID-19 vaccinations', 'bi-bar-chart'),
    'vaccination-map': ('vaccination_page', 'Vaccination coverage map', 'COVID-19 vaccinations', 'bi-map'),
    'disease-trends': ('disease_page', 'Disease cases over time', 'Reported disease cases', 'bi-graph-up-arrow'),
    'disease-totals': ('disease_page', 'Cumulative disease cases', 'Reported disease cases', 'bi-bar-chart'),
    'nutrition-trends': ('nutrition_page', 'Nutrient trends', 'Nutrition data', 'bi-graph-up-arrow'),
    'nutrition-states': ('nutrition_page', 'Nutrient comparison by state', 'Nutrition data', 'bi-bar-chart'),
    'nutrition-map': ('nutrition_page', 'Nutrition map', 'Nutrition data', 'bi-map'),
}


def favorites_db():
    db = connect()
    db.execute('''CREATE TABLE IF NOT EXISTS saved_charts (
        user_id INTEGER NOT NULL, chart_id TEXT NOT NULL, saved_at TEXT NOT NULL,
        PRIMARY KEY (user_id, chart_id))''')
    db.commit()
    return db


def favorites_context():
    if not session.get('user_id'):
        return {'saved_charts': [], 'saved_chart_ids': []}
    with closing(favorites_db()) as db:
        rows = db.execute('SELECT chart_id FROM saved_charts WHERE user_id = ? ORDER BY saved_at DESC, chart_id',
                          (session['user_id'],)).fetchall()
    charts = []
    for row in rows:
        chart_id = row['chart_id']
        if chart_id in CHARTS:
            endpoint, title, module, icon = CHARTS[chart_id]
            charts.append(dict(id=chart_id, title=title, module=module, icon=icon,
                               url=url_for(endpoint, _anchor=chart_id)))
    return {'saved_charts': charts, 'saved_chart_ids': [chart['id'] for chart in charts]}


def update_favorite(chart_id):
    if chart_id not in CHARTS:
        abort(404)
    action = request.form.get('action')
    if action not in ('save', 'remove'):
        abort(400)
    with closing(favorites_db()) as db, db:
        if action == 'save':
            db.execute('INSERT OR IGNORE INTO saved_charts(user_id, chart_id, saved_at) VALUES (?, ?, ?)',
                       (session['user_id'], chart_id, datetime.now(timezone.utc).isoformat()))
        else:
            db.execute('DELETE FROM saved_charts WHERE user_id = ? AND chart_id = ?', (session['user_id'], chart_id))
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(saved=action == 'save')
    if request.form.get('return_to') == 'dashboard':
        return redirect(url_for('dashboard', _anchor='saved-charts'))
    return redirect(url_for(CHARTS[chart_id][0], _anchor=chart_id))
