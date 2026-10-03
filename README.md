# Flask Student Template

A simple, beginner-friendly Flask application template for high school students learning full-stack web development. It is set up with 12-Factor App habits so the same code can run locally or on a hosting platform.

## Project Structure

```text
run.py              <- Main app entry point
routes.py           <- All your routes/pages go here
.env.example        <- Safe example settings to copy
.env                <- Your private local settings (never commit)
Procfile            <- Production process command
requirements.txt    <- Python packages needed
app/
  models/           <- For database models
static/
  css/style.css     <- Your custom styles
  js/main.js        <- Client-side JavaScript
templates/
  base.html         <- Base layout
  index.html        <- Home page
  signin.html       <- Sign-in form
  template.html     <- Reusable template for new pages
```

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create Local Environment Settings

```bat
copy .env.example .env
```

Open `.env` and change `SECRET_KEY` to any long random value for your own local copy.

### 3. Run the App

```bash
python run.py
```

The app will start at `http://localhost:5000`.

### 4. Make Changes

When you save files, the app will automatically reload if `FLASK_DEBUG=true` in your local `.env`. Refresh your browser to see changes.

## How to Add Features

### Disease and vaccination demo fallback

`/diseases` and `/vaccinations` render immediately, then request chart data from
`/api/public-charts/<page>`. After 10 seconds, or immediately on a failed request,
the page displays a notice at the bottom with **Load without recent data**.
Clicking it renders the checked-in `window.CDC_DEMO_DATA` JavaScript object in
`static/js/cdc-demo-data.js`, without another CDC request. Late live responses
cannot overwrite the selected saved data. **Try recent data again** retries.

For presentations, `/diseases?demo=1` and `/vaccinations?demo=1` display the bundled
snapshot immediately, without contacting CDC. Sign-in is still required. The
snapshot records its capture date, CDC source URLs, and latest reporting periods.
The current bundle contains disease data through 2024 and vaccination data through
2023-05-10. These are historical datasets, not current-year case/vaccination reports.
AI analysis is only offered after recent data loads, so it cannot accidentally
analyze a different dataset from the saved charts on screen.

Plotly and its US map geometry are served locally from `static/vendor/`; drawing
the saved charts does not require a third-party chart CDN. Deploy these static
files along with the Python and template changes. No new environment variables
or initial successful CDC request are required for the bundled demo fallback.
Rebuild the snapshot with `python scripts/update_demo_data.py` when desired; the
script only replaces the bundle after both datasets have loaded successfully.

The live loaders use public CDC endpoints without API credentials, validate
responses, paginate results, and apply connection/read timeouts. Vaccinations no
longer depends on the background cache-warming thread. API refreshes are limited
to one per page per process, with a 60-second cooldown after failures. The browser
stops waiting at 10 seconds; the server's bounded request may finish afterward
and warm the cache for the next visitor. Logs retain failure details.

Successful disease data is also cached for 24 hours and saved atomically to
`instance/disease-cache.json`. Keep `instance` writable and on persistent storage
to retain this server-side cache across restarts. `DISEASE_CACHE_PATH` in Flask
config can override its location. This cache is separate from the committed demo
bundle. Workspace database errors disable the saved-chart buttons on these two
pages instead of blocking the charts.

After deploying, sign in and check both normal URLs and both `?demo=1` URLs.

### Dataset workspace

The signed-in dashboard accepts UTF-8 CSV, TSV, and JSON arrays of flat records
(up to 5 MB, 50,000 rows, and 40 columns). CSV and TSV files need unique column
headers. Uploads generate numeric distributions, category counts, a 10-row
preview, and Groq findings. Use the dataset and column selectors to change the view.

Set `GROQ_API_KEY` in the server environment or `.env` to enable analysis.
`GROQ_DATASET_MODEL` optionally overrides the default `openai/gpt-oss-20b`.
Groq receives column names, aggregate statistics, and top category labels/counts;
it does not receive the row preview. AI findings describe the whole dataset's
summaries, independently of which chart column is selected. Failed requests keep
the summary available and can be retried from the dashboard.

Summaries, previews, and analyses are saved per account in the SQLite database
specified by `WORKSPACE_DATABASE_URL`, or `DATABASE_URL` when no separate workspace
URL is set. The original uploaded files are not retained. Persist the configured
database files when hosting the app so data survives restarts or deployments.
Tests override these URL settings with isolated databases.

Run the checks with `python -m unittest discover -s tests -v`.

The heart buttons on the vaccination, disease, and nutrition charts save
account-specific shortcuts in the configured workspace database. The dashboard's Saved
charts section links directly to those charts. Saving is idempotent; charts can
be removed from either the chart page or the dashboard.

### Add a New Page

1. Create a new route in `routes.py`:

```python
@app.route('/mypage')
def my_page():
    return render_template('mypage.html')
```

2. Create `templates/mypage.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>My Page</h1>
{% endblock %}
```

### Add a Form

Check out `signin.html` for a form example. The form submission belongs in `routes.py`.

### Style Your App

Edit `static/css/style.css` to customize colors, fonts, and layouts.

## Environment Variables

### Database configuration and health check

Database connections read `DATABASE_URL` from the project-root `.env` file or
deployment environment. Existing environment variables take precedence over `.env`.
There is no hardcoded database filename fallback. Startup reports a configuration
error if `DATABASE_URL` is missing or unsupported. The current storage layer supports
SQLite URLs; it does not support PostgreSQL or MySQL URLs.

```dotenv
DATABASE_URL=sqlite:///app.db
WORKSPACE_DATABASE_URL=sqlite:///instance/workspace.db
```

The separate workspace URL is optional. If omitted, account and workspace tables
use `DATABASE_URL`. Keep it set to the existing workspace file when upgrading to
preserve access to previous uploads and saved charts. Changing a URL selects a
different database; it does not migrate data automatically.

Relative SQLite paths resolve from the project directory, regardless of the
launch directory. Absolute paths also work, such as `sqlite:////var/data/app.db`
on Linux or `sqlite:///C:/data/app.db` on Windows. See `.env.example` for settings.

`GET /healthz` is public and returns `OK` with HTTP 200. It is a liveness check and
does not query the database or external services. The existing `/api/health`
JSON endpoint remains available.

### CSRF protection and forms

Flask-WTF protects every POST, PUT, PATCH, and DELETE request. All POST forms
include a signed token tied to the browser session, valid for one hour. Fetch
requests can submit the form token or an `X-CSRFToken` header. Invalid or expired
tokens return HTTP 400 with a recovery message (JSON for AJAX). Reload the page
to obtain a fresh token. Signing in rotates the session and invalidates old forms.
Pages containing tokens are served with `Cache-Control: no-store`.

Sign-out uses a protected POST button; visiting `/logout` only shows confirmation.
Vaccination and disease AI analysis now runs directly within the protected chart
POST, without putting chart data or AI responses in session cookies. The old
`/ai-analysis` URL redirects to the dashboard and never calls Groq on GET.

The server validates username, password, and optional email lengths and formats,
rejects duplicate form fields, and restricts avatar redirects to known app pages.
Ordinary forms are capped at 64 KiB; dataset upload requests allow 5 MiB plus
128 KiB of multipart overhead. File uploads keep the existing 5 MiB file limit.
The unfinished password-reset page is informational rather than submitting to a
nonexistent reset handler.

Tests obtain signed tokens from rendered pages and leave CSRF protection enabled.
Run JavaScript checks with `node tests/test_favorites_js.cjs` in addition to the
Python test suite.

### Authentication rate limits

Sign-in POSTs allow 5 attempts per minute and 30 per hour per client IP.
Sign-up POSTs allow 5 attempts per hour per client IP. Both successful and failed
submissions count. Blocked requests return HTTP 429, an on-page retry message,
and a `Retry-After` header before password checks or account creation run.
GET requests, logout, and unrelated routes are unaffected. The current
forgot-password page has no password-reset submission endpoint.

The default `memory://` storage works for a single local app process; its counters
reset when that process restarts. For production with multiple workers or hosts,
set `RATELIMIT_STORAGE_URI` to a shared Redis URL (for example,
`redis://localhost:6379/0`). Redis support is included in `requirements.txt`.
Use a separate Redis database for each deployment.

Limits use the server-provided remote address and do not directly trust client
`X-Forwarded-For` or `X-Real-IP` headers. When deploying behind a reverse proxy,
configure the server's trusted proxies and forwarded-header handling for that
specific deployment so the remote address identifies the real client; otherwise
users behind the proxy share one rate limit.

12-Factor apps store configuration in environment variables instead of hard-coding it in Python.

Edit `.env` for local development:

- `SECRET_KEY` - Flask session secret. Required in production.
- `FLASK_DEBUG` - Set to `true` only for local development.
- `FLASK_ENV` - Use `development` locally and `production` when deployed.
- `HOST` - Local host address. Usually `127.0.0.1`.
- `PORT` - Local port. Hosting platforms usually set this automatically.
- `DATABASE_URL` - Required SQLite URL for account storage.
- `WORKSPACE_DATABASE_URL` - Optional separate SQLite URL for datasets and saved charts; defaults to `DATABASE_URL`.

Never commit `.env`. Commit `.env.example` so teammates know which settings exist.

## 12-Factor Notes for Students

- **Codebase:** Keep one repo for this app.
- **Dependencies:** Add Python packages to `requirements.txt`.
- **Config:** Put secrets and deployment settings in environment variables.
- **Backing services:** Connect to databases through `DATABASE_URL`, not hard-coded file paths.
- **Processes:** The app should not depend on files created while it runs, except temporary local learning files.
- **Port binding:** The app reads `PORT` so a hosting service can choose the port.
- **Logs:** Print/log to the console so the hosting platform can collect logs.

## Production Run Command

Hosting platforms that read a `Procfile` can start the app with:

```bash
web: waitress-serve --port=$PORT run:app
```

## Next Steps

- Configure persistent database storage using the environment settings above.
- Add user authentication with Flask-Login.
- Deploy to a hosting platform.
- Add more JavaScript interactivity.

Happy coding!
