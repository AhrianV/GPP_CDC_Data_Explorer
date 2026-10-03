"""Shared CSRF protection and bounded, unambiguous form submissions."""
from flask import Request, g, jsonify, make_response, render_template, request, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect

csrf = CSRFProtect()


class FormRequest(Request):
    max_form_memory_size = 512 * 1024
    max_form_parts = 32

    @property
    def max_content_length(self):
        return 5 * 1024 * 1024 + 128 * 1024 if self.endpoint == 'dashboard_upload' else 64 * 1024


def form_error(message, status=400):
    if request.accept_mimetypes.best == 'application/json':
        response = make_response(jsonify(error=message), status)
    else:
        endpoint = request.endpoint if request.endpoint in {
            'signin', 'signup', 'nutrition_page', 'disease_page', 'vaccination_page', 'logout'
        } else 'dashboard'
        response = make_response(render_template('form_error.html', message=message,
                                                 return_url=url_for(endpoint)), status)
    response.headers['Cache-Control'] = 'no-store'
    return response


def init_form_security(app):
    app.request_class = FormRequest
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config.setdefault('WTF_CSRF_TIME_LIMIT', 3600)
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return form_error('This form expired or could not be verified. Reload the page and try again.')

    @app.errorhandler(413)
    def too_large(error):
        message = 'Upload a dataset of 5 MB or less.' if request.endpoint == 'dashboard_upload' else 'This form is too large. Shorten your input and try again.'
        return form_error(message, 413)

    @app.before_request
    def validate_form_shape():
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return
        if request.mimetype not in ('application/x-www-form-urlencoded', 'multipart/form-data'):
            return form_error('Submit this request using the form on the page.', 415)
        if any(len(request.form.getlist(key)) != 1 for key in request.form) or any(
            len(request.files.getlist(key)) != 1 for key in request.files
        ):
            return form_error('The form contains duplicate fields. Reload the page and try again.')

    @app.after_request
    def protect_form_responses(response):
        if hasattr(g, 'csrf_token'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        return response
