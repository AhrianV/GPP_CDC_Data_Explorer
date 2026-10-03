#!/usr/bin/env python3
"""Flask app for the Group Project Program."""

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal environments
    def load_dotenv():
        return False

from flask import Flask
from database import configure_databases

# 12-Factor apps keep settings in environment variables.
# In local development, python-dotenv reads those values from .env.
# On a hosting service, the platform provides real environment variables.
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

environment = os.getenv("FLASK_ENV", "development").lower()
debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ["true", "1", "yes"]
secret_key = os.getenv("SECRET_KEY")

# A fallback secret is okay for students running locally, but production must
# provide a real SECRET_KEY so cookies and sessions are not easy to forge.
if not secret_key:
    if environment == "development":
        secret_key = "dev-key-change-me"
    else:
        raise RuntimeError("SECRET_KEY must be set in the environment.")

app.config["SECRET_KEY"] = secret_key
configure_databases(app)

# Import routes after app is created to avoid circular imports
from routes import *

if __name__ == '__main__':
    # PORT lets a hosting platform choose where the web process listens.
    # Locally, it still defaults to the familiar http://localhost:5000.
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=debug_mode)
