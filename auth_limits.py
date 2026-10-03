"""POST-only authentication throttling with optional shared Redis storage."""
import math
import os
import time

from flask import make_response, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def rate_limit_response(request_limit):
    seconds = max(1, math.ceil(request_limit.reset_at - time.time()))
    signup = request.endpoint == 'signup'
    message = f"Too many {'sign-up' if signup else 'sign-in'} attempts. Please try again in {seconds} seconds."
    response = make_response(render_template('signup.html' if signup else 'signin.html',
                                             rate_limit_message=message), 429)
    response.headers['Retry-After'] = str(seconds)
    response.headers['Cache-Control'] = 'no-store'
    return response


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
    strategy='moving-window',
    key_prefix='gpp-cdc-auth',
    on_breach=rate_limit_response,
)


def init_auth_limits(app):
    # In-memory storage suits a single local process. Redis shares counters across
    # production workers/hosts and preserves them when an app process restarts.
    app.config.setdefault('RATELIMIT_STORAGE_URI', os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
    limiter.init_app(app)
