"""Use the same signed CSRF tokens a browser receives; never disable protection."""
from html import unescape
import re


def token_from_response(response):
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
    if not match:
        raise AssertionError('Page did not render a CSRF token')
    return unescape(match.group(1))


def csrf_token(client, path='/signin'):
    return token_from_response(client.get(path))
