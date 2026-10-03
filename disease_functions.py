import requests
import pandas as pd
import plotly.graph_objects as go
from disease_data import get_disease_data, DiseaseDataUnavailable


CDC_DISEASE_URL = "https://data.cdc.gov/resource/x9gk-5huc.json"


def _get_disease_data(select, order_by):
    """Fetch public CDC disease rows and fail with a useful API error."""
    try:
        response = requests.get(
            CDC_DISEASE_URL,
            params={
                "$select": select,
                "$where": "location2 = 'US RESIDENTS'",
                "$order": order_by,
                "$limit": 50000,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("Unable to retrieve disease data from the CDC API") from exc

    if not isinstance(data, list):
        message = data.get("message", "unexpected response format") if isinstance(data, dict) else "unexpected response format"
        raise RuntimeError(f"CDC disease API error: {message}")

    return pd.DataFrame(data, columns=[column.strip() for column in select.split(",")])

def update_graph_layout(fig):
    fig.update_layout(
            height=500,
            autosize=True,
            margin=dict(l=20, r=20, t=50, b=20)
        )
    
    
def get_disease_cases_over_time():
    df = _get_disease_data("year,week,label,m1", "year,week")
    df = get_disease_data()
    metadata = df.attrs.copy()

    # clean data
    df = df[["year", "week", "label", "m1"]]
    df["m1"] = pd.to_numeric(df["m1"], errors="coerce")

    df = df.dropna()
    
    # group diseases
    df["disease_group"] = df["label"]
    
    df.loc[
    df["label"] == "Salmonellosis (excluding Salmonella Typhi infection and Salmonella Paratyphi infection)",
    "disease_group"
    ] = "Salmonellosis"
    
    df.loc[df["label"].str.startswith("Arboviral diseases,"), "disease_group"] = "Arboviral diseases"
    
    hepatitis_labels = [
    "Hepatitis A, Confirmed",
    "Hepatitis B, acute, Confirmed",
    "Hepatitis B, acute, Probable",
    "Hepatitis B, perinatal, Confirmed",
    "Hepatitis C, acute, Confirmed",
    "Hepatitis C, acute, Probable",
    "Hepatitis C, perinatal, Confirmed"
    ]

    df.loc[
    df["label"].isin(hepatitis_labels),
    "disease_group"
    ] = "Hepatitis"
    
    
    df.loc[df["label"].str.startswith("Meningococcal disease,"), "disease_group"] = "Meningococcal disease"

    df.loc[df["label"].str.startswith("Invasive pneumococcal disease,"), "disease_group"] = "Invasive pneumococcal disease"
    
    sti_labels = [
    "Chlamydia trachomatis infection",
    "Gonorrhea",
    "Syphilis, Primary and secondary",
    "Syphilis, Congenital"
    ]
    df.loc[df["label"].isin(sti_labels), "disease_group"] = "STIs"
    

    
    df.loc[
    df["label"].str.contains("influenza", case=False, na=False),
    "disease_group"
    ] = "Influenza"
    
    df = (
    df.groupby(["year", "week", "disease_group"], as_index=False)["m1"]
    .sum()
    )
    
    # get rid of ungrouped disease not being used
    
    
    disease_df = df[
    df["disease_group"].isin([
        "Influenza",
        "Tuberculosis",
        "Salmonellosis",
        "Campylobacteriosis",
        "Shigellosis",
        "Arboviral diseases",
        "Hepatitis",
        "Meningococcal disease",
        "Invasive pneumococcal disease",
        "STIs"
        ])
    ].copy()
    
    #convert to monthly
    
    disease_df["year"] = disease_df["year"].astype(int)
    disease_df["week"] = disease_df["week"].astype(int)

    jan4 = pd.to_datetime(
        disease_df["year"].astype(str) + "-01-04"
    )

# MMWR weeks start on Sunday
    week1_start = jan4 - pd.to_timedelta(
        (jan4.dt.dayofweek + 1) % 7,
        unit="D"
    )

    disease_df["week_start"] = (
        week1_start
        + pd.to_timedelta((disease_df["week"] - 1) * 7, unit="D")
    )
    
    disease_df["month"] = disease_df["week_start"].dt.to_period("M")
    
    monthly_disease_df = (
    disease_df
    .groupby(["month", "disease_group"], as_index=False)["m1"]
    .sum()
    )
    
    monthly_disease_df["month"] = (
    monthly_disease_df["month"].astype(str)
    )
    
    monthly_disease_df = monthly_disease_df.sort_values(
    ["month", "disease_group"]
    )
    
    
    if monthly_disease_df.empty:
        raise DiseaseDataUnavailable("No disease trend data is available")
    monthly_disease_df.attrs.update(metadata)
    return monthly_disease_df


def display_disease_cases_over_time(monthly_disease_df, as_figure=False):

    if monthly_disease_df.empty:
        raise DiseaseDataUnavailable("No disease trend data is available")
    diseases = monthly_disease_df["disease_group"].unique()

    fig = go.Figure()

    for disease in diseases:
        disease_data = monthly_disease_df[
            monthly_disease_df["disease_group"] == disease
        ]

        fig.add_trace(
            go.Scatter(
                x=disease_data["month"],
                y=disease_data["m1"],
                mode="lines+markers",
                name=disease,
                visible=(disease == diseases[0])
            )
        )

    buttons = []

    for i, disease in enumerate(diseases):
        visible = [False] * len(diseases)
        visible[i] = True

        buttons.append(
            dict(
                label=disease,
                method="update",
                args=[
                    {"visible": visible},
                    {"title.text": f"{disease} Cases Over Time"}
                ]
            )
        )

    fig.update_layout(
        title=f"{diseases[0]} Cases Over Time",
        xaxis_title="Month",
        yaxis_title="Cases",
        updatemenus=[
            dict(
                buttons=buttons,
                direction="down",
                showactive=True
            )
        ]
    )
    
    update_graph_layout(fig)

    if as_figure:
        return fig

    graph = fig.to_html(
            full_html=False,
            config={"responsive": True})

    return graph

def get_cumulative_disease_cases():
    df = _get_disease_data("year,label,m3", "year")
    df = get_disease_data()
    metadata = df.attrs.copy()

    # clean data
    df = df[["year", "label", "m3"]]
    df["m3"] = pd.to_numeric(df["m3"], errors="coerce")

    df = df.dropna()
    
    # group diseases
    df["disease_group"] = df["label"]
    
    df.loc[
    df["label"] == "Salmonellosis (excluding Salmonella Typhi infection and Salmonella Paratyphi infection)",
    "disease_group"
    ] = "Salmonellosis"
    
    df.loc[df["label"].str.startswith("Arboviral diseases,"), "disease_group"] = "Arboviral diseases"
    
    hepatitis_labels = [
    "Hepatitis A, Confirmed",
    "Hepatitis B, acute, Confirmed",
    "Hepatitis B, acute, Probable",
    "Hepatitis B, perinatal, Confirmed",
    "Hepatitis C, acute, Confirmed",
    "Hepatitis C, acute, Probable",
    "Hepatitis C, perinatal, Confirmed"
    ]

    df.loc[
    df["label"].isin(hepatitis_labels),
    "disease_group"
    ] = "Hepatitis"
    
    
    df.loc[df["label"].str.startswith("Meningococcal disease,"), "disease_group"] = "Meningococcal disease"

    df.loc[df["label"].str.startswith("Invasive pneumococcal disease,"), "disease_group"] = "Invasive pneumococcal disease"
    
    sti_labels = [
    "Chlamydia trachomatis infection",
    "Gonorrhea",
    "Syphilis, Primary and secondary",
    "Syphilis, Congenital"
    ]
    df.loc[df["label"].isin(sti_labels), "disease_group"] = "STIs"
    

    
    df.loc[
    df["label"].str.contains("influenza", case=False, na=False),
    "disease_group"
    ] = "Influenza"
    
    
    # get rid of ungrouped disease not being used
    
    
    disease_df = df[
    df["disease_group"].isin([
        "Influenza",
        "Tuberculosis",
        "Salmonellosis",
        "Campylobacteriosis",
        "Shigellosis",
        "Arboviral diseases",
        "Hepatitis",
        "Meningococcal disease",
        "Invasive pneumococcal disease",
        "STIs"
        ])
    ].copy()
    
    # Find the latest year
    latest_year = disease_df["year"].max()

    # Keep only the latest year
    latest_year_df = disease_df[
        disease_df["year"] == latest_year
    ].copy()

    # Get the largest cumulative value for each disease
    cumulative_df = (
        latest_year_df
        .groupby("disease_group", as_index=False)["m3"]
        .max()
    )
    

    
    
    if cumulative_df.empty:
        raise DiseaseDataUnavailable("No cumulative disease data is available")
    cumulative_df.attrs.update(metadata)
    return cumulative_df, int(latest_year)

def display_cumulative_disease_cases_graph(cumulative_df, latest_year, as_figure=False):
    if cumulative_df.empty:
        raise DiseaseDataUnavailable("No cumulative disease data is available")
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=cumulative_df["m3"],
            y=cumulative_df["disease_group"],
            orientation="h",
            name="Cumulative Cases"
        )
    )

    fig.update_layout(
        title=f"Cumulative Disease Cases — {latest_year}",
        xaxis_title="Cumulative Cases",
        yaxis_title="Disease",
        xaxis_type="log"
    )

    update_graph_layout(fig)
    
    if as_figure:
        return fig

    graph = fig.to_html(
        full_html=False,
        config={"responsive": True})
    
    return graph
