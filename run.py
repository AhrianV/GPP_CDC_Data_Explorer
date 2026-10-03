#!/usr/bin/env python3
"""Flask app for the Group Project Program."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))


from dotenv import load_dotenv
from flask import Flask
from google import genai
from datetime import timedelta
from cache import cache
from database import configure_databases
import threading
import time


# 12-Factor apps keep settings in environment variables.
# In local development, python-dotenv reads those values from .env.
# On a hosting service, the platform provides real environment variables.
load_dotenv()

app = Flask(__name__)

environment = os.getenv("FLASK_ENV", "production").lower()
debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ["true", "1", "yes"]
secret_key = os.getenv("SECRET_KEY")

#configurate 
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# A fallback secret is okay for students running locally, but production must
# provide a real SECRET_KEY so cookies and sessions are not easy to forge.
if not secret_key:
    if environment == "development":
        secret_key = "dev-key-change-me"
    else:
        raise RuntimeError("SECRET_KEY must be set in the environment.")

app.config["SECRET_KEY"] = secret_key
configure_databases(app)


cache.init_app(app)

# Import routes after app is created to avoid circular imports
from routes import *

# creates user table if it does not exist upon running the app
from models.user import create_users_table
create_users_table()



from cache import cache_ready
from vaccination_functions import get_vaccination_by_date, get_vaccination_by_state_time

def warm_cache():
    while True:
        print("warming cache")
        cache_ready.clear()
        print("vaccination page not available")

        get_vaccination_by_date()
        get_vaccination_by_state_time()

        cache_ready.set()
        
        print("sleeping")
        time.sleep(23 * 60 * 60)



if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(
            target=warm_cache,
            daemon=True
        ).start()
    
    # PORT lets a hosting platform choose where the web process listens.
    # Locally, it still defaults to the familiar http://localhost:5000.
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=debug_mode)
