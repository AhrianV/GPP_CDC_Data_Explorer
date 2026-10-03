import os

from run import app


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ["true", "1", "yes"]
    app.run(host=host, port=port, debug=debug)
