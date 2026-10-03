"""Bounded CDC reads with a last-successful snapshot for upstream outages."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from flask import current_app
import pandas as pd
import requests

from cache import cache

URL = "https://data.cdc.gov/resource/x9gk-5huc.json"
FRESH_SECONDS = 86400
RETRY_SECONDS = 60
PAGE_SIZE = 10000
_refresh_lock = threading.Lock()


class DiseaseDataUnavailable(ValueError):
    pass


def _validate(rows):
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise DiseaseDataUnavailable("CDC returned no usable disease records")
    frame = pd.DataFrame(rows)
    if not {"year", "week", "label"}.issubset(frame.columns):
        raise DiseaseDataUnavailable("CDC disease response is missing required columns")
    frame = frame.reindex(columns=["year", "week", "label", "m1", "m3"])
    for column in ("year", "week", "m1", "m3"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = (frame["year"].between(1900, 2100) & frame["week"].between(1, 53)
             & frame["year"].mod(1).eq(0) & frame["week"].mod(1).eq(0)
             & frame["label"].map(lambda value: isinstance(value, str) and bool(value.strip())))
    frame = frame.loc[valid].copy()
    if frame.empty or frame[["m1", "m3"]].isna().all().all():
        raise DiseaseDataUnavailable("CDC returned no usable disease counts")
    return frame


def _fetch_rows():
    rows = []
    started = time.monotonic()
    for page in range(10):
        if time.monotonic() - started > 15:
            raise DiseaseDataUnavailable("CDC disease download exceeded its time budget")
        response = requests.get(URL, params={
            "$select": "year,week,label,m1,m3",
            "$where": "location2 = 'US RESIDENTS'",
            "$order": "year,week,label,:id",
            "$limit": PAGE_SIZE, "$offset": page * PAGE_SIZE,
        }, timeout=(3, 8))
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list) or not all(isinstance(row, dict) for row in batch):
            raise DiseaseDataUnavailable("Unexpected CDC response format")
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            _validate(rows)
            return rows
    raise DiseaseDataUnavailable("CDC response exceeded the row limit; refusing partial data")


def get_disease_data():
    """Share one validated snapshot between charts; never cache failed responses."""
    path = Path(current_app.config.get(
        "DISEASE_CACHE_PATH", Path(current_app.instance_path) / "disease-cache.json"))
    key = "disease-snapshot-v1:" + str(path)
    snapshot = cache.get(key)
    if snapshot is None:
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            _validate(candidate["rows"])
            float(candidate["fetched_at"])
            snapshot = candidate
            cache.set(key, snapshot, timeout=0)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    now = time.time()
    if snapshot is None or now - float(snapshot["fetched_at"]) >= FRESH_SECONDS:
        if not cache.get(key + ":retry") and _refresh_lock.acquire(blocking=False):
            try:
                # Another thread may have refreshed between the read and lock.
                snapshot = cache.get(key) or snapshot
                if snapshot is None or now - float(snapshot["fetched_at"]) >= FRESH_SECONDS:
                    rows = _fetch_rows()
                    snapshot = {"rows": rows, "fetched_at": time.time()}
                    cache.set(key, snapshot, timeout=0)
                    temporary = None
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                                         delete=False) as handle:
                            temporary = handle.name
                            json.dump(snapshot, handle)
                        os.replace(temporary, path)
                    except OSError:
                        current_app.logger.warning("Could not persist disease snapshot")
                    finally:
                        if temporary and os.path.exists(temporary):
                            try:
                                os.unlink(temporary)
                            except OSError:
                                pass
            except (requests.RequestException, ValueError):
                cache.set(key + ":retry", True, timeout=RETRY_SECONDS)
                current_app.logger.warning("CDC disease refresh failed", exc_info=True)
            finally:
                _refresh_lock.release()
        if snapshot is None:
            raise DiseaseDataUnavailable("CDC disease data is temporarily unavailable")

    frame = _validate(snapshot["rows"])
    frame.attrs["fetched_at"] = float(snapshot["fetched_at"])
    frame.attrs["stale"] = time.time() - frame.attrs["fetched_at"] >= FRESH_SECONDS
    return frame
