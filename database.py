"""SQLite connections configured by .env or deployment environment variables."""
import os
from pathlib import Path
import sqlite3
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv
from flask import current_app, has_app_context

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / '.env')


def sqlite_path(url):
    if not url:
        raise RuntimeError('Set DATABASE_URL in .env or the server environment before starting the app.')
    parsed = urlsplit(url)
    if not url.startswith('sqlite:///') or parsed.netloc or parsed.query or parsed.fragment:
        raise RuntimeError('This app uses SQLite. Configure a sqlite:///path/to/database.db URL without query parameters.')
    value = unquote(url[len('sqlite:///'):])
    if not value:
        raise RuntimeError('The SQLite database URL must include a database path.')
    if value == ':memory:':
        return value
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


def configure_databases(app):
    primary = os.getenv('DATABASE_URL')
    workspace = os.getenv('WORKSPACE_DATABASE_URL') or primary
    # Validate at startup; never silently create a database at a fallback path.
    sqlite_path(primary)
    sqlite_path(workspace)
    app.config.update(DATABASE_URL=primary, WORKSPACE_DATABASE_URL=workspace)


def connect_database(workspace=False):
    settings = current_app.config if has_app_context() else os.environ
    url = settings.get('DATABASE_URL')
    if workspace:
        url = settings.get('WORKSPACE_DATABASE_URL') or url
    path = sqlite_path(url)
    if path != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection
