from flask_caching import Cache
import threading

cache_ready = threading.Event()

cache = Cache(
    config={
        "CACHE_TYPE": "SimpleCache",
        "CACHE_DEFAULT_TIMEOUT": 86400
    }
)
