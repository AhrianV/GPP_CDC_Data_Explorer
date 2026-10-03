"""Plotly payloads used by the live pages and the bundled demo snapshot."""
import json
import threading
from datetime import datetime, timezone

import plotly.express as px
from cache import cache

from disease_functions import (get_disease_cases_over_time, get_cumulative_disease_cases,
                               display_disease_cases_over_time, display_cumulative_disease_cases_graph)
from vaccination_functions import (get_vaccination_by_date, get_vaccination_by_state_time,
                                   create_vac_by_state_fig, create_vac_by_map_fig, update_graph_layout)


PAGE_DETAILS = {
    "diseases": {
        "endpoint": "disease_page", "eyebrow": "Disease surveillance",
        "title": "Reported Disease Cases",
        "description": "Review reported case trends over time and compare cumulative totals.",
        "charts": [("disease-trends", "Disease cases over time", "over_time"),
                   ("disease-totals", "Cumulative disease cases", "cumulative_cases")],
    },
    "vaccinations": {
        "endpoint": "vaccination_page", "eyebrow": "Vaccination coverage",
        "title": "COVID-19 Vaccination Data",
        "description": "Track vaccination progress over time and compare rates across states.",
        "charts": [("vaccination-trends", "Vaccination trends", "over_time"),
                   ("vaccination-states", "Vaccination coverage by state", "state_time_bar"),
                   ("vaccination-map", "Vaccination coverage map", "state_time_map")],
    },
}

_locks = {page: threading.Lock() for page in PAGE_DETAILS}


def get_chart_payload(page):
    key = "public-chart-payload-v1:" + page
    payload = cache.get(key)
    if payload is not None:
        return payload
    if cache.get(key + ":retry") or not _locks[page].acquire(blocking=False):
        raise ValueError("A CDC refresh is unavailable or already in progress")
    try:
        payload = build_chart_payload(page)
        cache.set(key, payload, timeout=300)
        return payload
    except Exception:
        cache.set(key + ":retry", True, timeout=60)
        raise
    finally:
        _locks[page].release()


def build_chart_payload(page):
    if page == "diseases":
        monthly = get_disease_cases_over_time()
        cumulative, year = get_cumulative_disease_cases()
        # The browser must offer the explicit snapshot choice when a refresh failed.
        if monthly.attrs.get("stale") or cumulative.attrs.get("stale"):
            raise ValueError("Recent CDC disease data could not be refreshed")
        figures = {
            "disease-trends": display_disease_cases_over_time(monthly, as_figure=True),
            "disease-totals": display_cumulative_disease_cases_graph(cumulative, year, as_figure=True),
        }
        latest = str(year)
        source = "https://data.cdc.gov/resource/x9gk-5huc.json"
    elif page == "vaccinations":
        trend = get_vaccination_by_date()
        states = get_vaccination_by_state_time()
        line = px.line(trend, x="date", y="avg_vaccination_rate",
                       title="COVID-19 Vaccination Rate Over Time",
                       labels={"date": "Date", "avg_vaccination_rate": "Vaccination Rate (%)"})
        update_graph_layout(line)
        figures = {
            "vaccination-trends": line,
            "vaccination-states": create_vac_by_state_fig(states, as_figure=True),
            "vaccination-map": create_vac_by_map_fig(states, as_figure=True),
        }
        latest = states["date"].max().strftime("%Y-%m-%d")
        source = "https://data.cdc.gov/resource/8xkx-amqh.json"
    else:
        raise ValueError("Unknown public data page")
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "latest_reporting_period": latest,
        "source": source,
        "charts": {name: json.loads(figure.to_json()) for name, figure in figures.items()},
    }
