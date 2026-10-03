import os

from app import app


def main():
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() in ['true', '1', 'yes']

    try:
        from waitress import serve
    except ImportError:
        app.run(host=host, port=port, debug=debug_mode)
    else:
        serve(app, host=host, port=port)


if __name__ == '__main__':
    main()
