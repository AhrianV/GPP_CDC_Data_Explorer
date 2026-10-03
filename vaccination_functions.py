import time
import requests
import pandas as pd
import plotly.graph_objects as go
from cache import cache


def update_graph_layout(fig):
    fig.update_layout(
            height=500,
            autosize=True,
            margin=dict(l=20, r=20, t=50, b=20)
        )

def _vaccination_query(select, group):
    rows = []
    started = time.monotonic()
    for offset in range(0, 100000, 10000):
        if time.monotonic() - started > 8:
            raise ValueError("Vaccination download exceeded its time budget")
        response = requests.get("https://data.cdc.gov/resource/8xkx-amqh.json", params={
            "$select": select, "$group": group, "$order": group,
            "$limit": 10000, "$offset": offset,
        }, timeout=(2, 5))
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list) or not all(isinstance(row, dict) for row in batch):
            raise ValueError("Unexpected CDC vaccination response")
        rows.extend(batch)
        if len(batch) < 10000:
            if not rows:
                raise ValueError("No vaccination data available")
            return pd.DataFrame(rows)
    raise ValueError("Vaccination response exceeded row limit")


@cache.cached(key_prefix="vaccination_by_date_v2")
def get_vaccination_by_date():
    df = _vaccination_query(
        "date,avg(series_complete_pop_pct) as avg_vaccination_rate", "date")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["avg_vaccination_rate"] = pd.to_numeric(df["avg_vaccination_rate"], errors="coerce")
    df = df.dropna()
    if df.empty:
        raise ValueError("No vaccination trend data available")
    return df


@cache.cached(key_prefix="vaccination_by_state_v2")
def get_vaccination_by_state_time():
    df = _vaccination_query(
        "date,recip_state,avg(series_complete_pop_pct) as series_complete_pop_pct", "date,recip_state")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["series_complete_pop_pct"] = pd.to_numeric(df["series_complete_pop_pct"], errors="coerce")
    df = df.dropna()
    if df.empty:
        raise ValueError("No vaccination state data available")
    return df


def create_vac_by_state_fig(vaccination_by_state, as_figure=False):
        
    if vaccination_by_state.empty:
        raise ValueError("No vaccination state data available")
    by_state_graph_fig = go.Figure()
    
    dates = (
    vaccination_by_state
    .groupby(vaccination_by_state["date"].dt.to_period("M"))["date"]
    .max()
    .tolist())
    
    for date in dates:
        date_df = vaccination_by_state[
        vaccination_by_state["date"] == date]
    
        state_average = (
            date_df.groupby("recip_state")["series_complete_pop_pct"]
            .mean()
            .reset_index()
        )
    
        by_state_graph_fig.add_trace(
            go.Bar(
                x=state_average["recip_state"],
                y=state_average["series_complete_pop_pct"],
                visible=False
            )
        )
        
        
        
    by_state_graph_fig.data[-1].visible = True
    
    by_state_graph_fig.update_layout(
    title="COVID-19 Vaccination Rate by State",
    xaxis_title="State",
    yaxis_title="Vaccination Rate (%)",
    updatemenus=[
        {
            "buttons": [
                {
                    "label": date.strftime("%Y-%m"),
                    "method": "update",
                    "args": [
                        {
                            "visible": [
                                i == index
                                for i in range(len(dates))
                            ]
                        }
                    ]
                }
                for index, date in enumerate(dates)
            ],
            "direction": "down",
            "active": len(dates) - 1
        }
    ]
    )
    
    update_graph_layout(by_state_graph_fig)
    
        
    if as_figure:
        return by_state_graph_fig

    by_state_graph = by_state_graph_fig.to_html(
        full_html=False,
        config={"responsive": True})   
    
        
    return by_state_graph




def create_vac_by_map_fig(vaccination_by_state, as_figure=False):
          
    if vaccination_by_state.empty:
        raise ValueError("No vaccination state data available")
    by_state_graph_fig = go.Figure()
        
    dates = (
    vaccination_by_state
    .groupby(vaccination_by_state["date"].dt.to_period("M"))["date"]
    .max()
    .tolist())
        
    for date in dates:
        date_df = vaccination_by_state[
        vaccination_by_state["date"] == date]
        
        state_average = (
            date_df.groupby("recip_state")["series_complete_pop_pct"]
            .mean()
            .reset_index()
        )
        
        by_state_graph_fig.add_trace(
        go.Choropleth(
            locations=state_average["recip_state"],
            z=state_average["series_complete_pop_pct"],
            locationmode="USA-states",
            colorscale="Blues",
            visible=False,
            colorbar_title="Vaccination Rate (%)"
            )
        )
            
            
            
    by_state_graph_fig.data[-1].visible = True
        
    by_state_graph_fig.update_layout(
    title="COVID-19 Vaccination Rate Across States",
    geo_scope="usa",
    updatemenus=[
        {
            "buttons": [
                {
                    "label": date.strftime("%Y-%m"),
                    "method": "update",
                    "args": [
                        {
                            "visible": [
                                i == index
                                for i in range(len(dates))
                            ]
                        }
                    ]
                }
                for index, date in enumerate(dates)
            ],
            "direction": "down",
            "active": len(dates) - 1
        }
    ]
    )
        
    update_graph_layout(by_state_graph_fig)
        
            
    if as_figure:
        return by_state_graph_fig

    by_state_graph = by_state_graph_fig.to_html(
        full_html=False,
        config={"responsive": True})   
    
            
    return by_state_graph
    



