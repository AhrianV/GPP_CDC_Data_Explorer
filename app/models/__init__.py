"""Simple database helper for students.

Run this file any time you want to create the database or inspect it:

    py app/models/__init__.py
"""

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_DATABASE_URL = "sqlite:///app.db"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def get_database_path():
    """Read DATABASE_URL from .env and turn it into an app.db file path."""
    load_dotenv(dotenv_path=ENV_FILE, override=True)

    database_url = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL

    # This beginner template supports local SQLite databases like:
    # DATABASE_URL=sqlite:///app.db
    if not database_url.startswith("sqlite:///"):
        raise ValueError("DATABASE_URL must start with sqlite:///")

    return PROJECT_ROOT / database_url.replace("sqlite:///", "", 1)


def open_database():
    """Create the database file if needed, then return a connection to it."""
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection, database_path


def print_database_schema():
    """Print every table name and the SQL used to create it."""
    connection, database_path = open_database()

    with connection:
        tables = connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

    print(f"Database: {database_path}")

    if not tables:
        print("No tables yet.")
        return

    print("Tables:")
    for table_name, create_sql in tables:
        print(f"\n{table_name}")
        print(create_sql)


if __name__ == "__main__":
    print_database_schema()
