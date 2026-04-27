import dash
from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from data.loader import load_df, STAGE_COLORS, STAGE_SHORT

dash.register_page(__name__, path="/trends", title="Trends — DistressedCA", name="Trends")

_STAGE_ORDER = [
    "NOD  — Notice of Default",
    "NTS  — Notice of Trustee's Sale",
    "NOR  — Notice of Rescission",
    "TDUS — Trustee's Deed Upon Sale",
]
_COLOR_MAP = {s: STAGE_COLORS[s] for s in _STAGE_ORDER if s in STAGE_COLORS}


def _navbar():
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand([html.Span("🏚", className="me-2"), "DistressedCA"],
                            href="/", className="fw-bold fs-5 text-danger"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Map",      href="/")),
                dbc.NavItem(dbc.NavLink("Auctions", href="/auctions")),
                dbc.NavItem(dbc.NavLink("Trends",   href="/trends", active=True)),
                dbc.NavItem(dbc.NavLink("About",    href="/about")),
                dbc.NavItem(dbc.NavLink(
                    [html.I(className="bi bi-github me-1"), "GitHub"],
                    href="https://github.com/HighviewOne/DistressedCA",
                    target="_blank", external_link=True,
                )),
            ], navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark", dark=True, sticky="top", className="mb-0 py-1",
    )


def layout():
    df = load_df()
    all_counties = sorted(df["County"].dropna().unique().tolist())

    return dbc.Container([
        _navbar(),
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H4("Foreclosure Trends", className="fw-bold mt-3 mb-0"),
                    html.P("California NOD filings over time", className="text-muted small mb-3"),
                ], md=8),
                dbc.Col([
                    dcc.Dropdown(
                        id="trends-county-filter",
                        options=[{"label": c, "value": c} for c in all_counties],
                        value=[],
                        multi=True,
                        placeholder="All counties",
                        className="mt-3",
                    ),
                ], md=4),
            ]),

            dbc.Row([
                # Monthly filings chart
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H6("Monthly Filings by Stage", className="mb-0 fw-bold")),
                        dbc.CardBody(dcc.Graph(id="chart-monthly", config={"displayModeBar": False})),
                    ]),
                ], lg=12, className="mb-3"),
            ]),

            dbc.Row([
                # Top counties
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H6("Top Counties by Filing Volume", className="mb-0 fw-bold")),
                        dbc.CardBody(dcc.Graph(id="chart-counties", config={"displayModeBar": False})),
                    ]),
                ], lg=6, className="mb-3"),

                # Stage mix donut
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H6("Filing Stage Breakdown", className="mb-0 fw-bold")),
                        dbc.CardBody(dcc.Graph(id="chart-stages", config={"displayModeBar": False})),
                    ]),
                ], lg=6, className="mb-3"),
            ]),

            dbc.Row([
                # Weekly pace (last 12 weeks)
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H6("Weekly Filing Pace — Last 12 Weeks", className="mb-0 fw-bold")),
                        dbc.CardBody(dcc.Graph(id="chart-weekly", config={"displayModeBar": False})),
                    ]),
                ], lg=12, className="mb-3"),
            ]),

            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H6("Foreclosure Density Map", className="mb-0 fw-bold")),
                        dbc.CardBody(dcc.Graph(id="chart-density", config={"displayModeBar": False},
                                               style={"height": "500px"})),
                    ]),
                ], lg=12, className="mb-3"),
            ]),
        ], fluid=True),
    ], fluid=True, className="p-0")


@callback(
    Output("chart-monthly",  "figure"),
    Output("chart-counties", "figure"),
    Output("chart-stages",   "figure"),
    Output("chart-weekly",   "figure"),
    Output("chart-density",  "figure"),
    Input("trends-county-filter", "value"),
)
def update_charts(counties):
    df = load_df().copy()
    df = df[df["Recording Date"].notna()]
    df = df[df["Stage"].isin(_STAGE_ORDER)]

    if counties:
        df = df[df["County"].isin(counties)]

    df["Stage Short"] = df["Stage"].map(STAGE_SHORT)
    df["Month"] = df["Recording Date"].dt.to_period("M").dt.to_timestamp()
    df["Week"]  = df["Recording Date"].dt.to_period("W").dt.to_timestamp()

    # ── Monthly bar chart ─────────────────────────────────────────────────────
    monthly = (
        df.groupby(["Month", "Stage"], observed=True)
        .size().reset_index(name="Count")
    )
    monthly["Stage Short"] = monthly["Stage"].map(STAGE_SHORT)

    fig_monthly = px.bar(
        monthly, x="Month", y="Count", color="Stage",
        color_discrete_map=_COLOR_MAP,
        category_orders={"Stage": _STAGE_ORDER},
        labels={"Month": "", "Count": "Filings", "Stage": ""},
        template="plotly_white",
    )
    fig_monthly.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=30, b=10, l=10, r=10),
        hovermode="x unified",
        bargap=0.15,
    )

    # ── Top 15 counties bar chart ─────────────────────────────────────────────
    top_counties = (
        df.groupby("County", observed=True)
        .size().reset_index(name="Count")
        .sort_values("Count", ascending=True)
        .tail(15)
    )
    fig_counties = px.bar(
        top_counties, x="Count", y="County", orientation="h",
        color="Count", color_continuous_scale="Reds",
        labels={"Count": "Total Filings", "County": ""},
        template="plotly_white",
    )
    fig_counties.update_layout(
        coloraxis_showscale=False,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis=dict(tickfont=dict(size=11)),
    )

    # ── Stage donut ───────────────────────────────────────────────────────────
    stage_counts = df.groupby("Stage", observed=True).size().reset_index(name="Count")
    stage_counts["Label"] = stage_counts["Stage"].map(STAGE_SHORT)
    fig_stages = go.Figure(go.Pie(
        labels=stage_counts["Label"],
        values=stage_counts["Count"],
        hole=0.55,
        marker_colors=[STAGE_COLORS.get(s, "#6b7280") for s in stage_counts["Stage"]],
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:,} filings<extra></extra>",
    ))
    fig_stages.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        annotations=[dict(text=f"{len(df):,}<br>total", x=0.5, y=0.5,
                          font_size=14, showarrow=False)],
    )

    # ── Weekly pace ───────────────────────────────────────────────────────────
    cutoff = df["Recording Date"].max() - pd.Timedelta(weeks=12)
    weekly = (
        df[df["Recording Date"] >= cutoff]
        .groupby(["Week", "Stage"], observed=True)
        .size().reset_index(name="Count")
    )
    fig_weekly = px.area(
        weekly, x="Week", y="Count", color="Stage",
        color_discrete_map=_COLOR_MAP,
        category_orders={"Stage": _STAGE_ORDER},
        labels={"Week": "", "Count": "Filings", "Stage": ""},
        template="plotly_white",
    )
    fig_weekly.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=30, b=10, l=10, r=10),
        hovermode="x unified",
    )

    # ── Density heatmap ───────────────────────────────────────────────────────
    geo = df.dropna(subset=["Latitude", "Longitude"]).copy()
    geo["Stage Short"] = geo["Stage"].map(STAGE_SHORT).fillna("Other")
    fig_density = px.density_map(
        geo,
        lat="Latitude", lon="Longitude",
        z=None,  # uniform intensity — pure density
        radius=12,
        center={"lat": 36.8, "lon": -119.4},
        zoom=5,
        map_style="carto-positron",
        color_continuous_scale="Reds",
        hover_name="Property Address",
        hover_data={"Latitude": False, "Longitude": False, "Stage Short": True, "County": True},
        title=None,
        height=500,
    )
    fig_density.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        coloraxis_showscale=False,
    )

    return fig_monthly, fig_counties, fig_stages, fig_weekly, fig_density
