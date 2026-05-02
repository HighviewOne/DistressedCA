import dash
from dash import html, dcc, callback, Output, Input
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
_NEW_COLORS = {
    "NOD  — Notice of Default":         "#D97706",
    "NTS  — Notice of Trustee's Sale":  "#DC2626",
    "NOR  — Notice of Rescission":      "#059669",
    "TDUS — Trustee's Deed Upon Sale":  "#7C3AED",
}
_SHORT_COLORS = {"NOD": "#D97706", "NTS": "#DC2626", "NOR": "#059669", "TDUS": "#7C3AED"}


def _plotly_layout(**kwargs):
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Geist, system-ui, sans-serif", "color": "#44403C", "size": 11},
        margin={"t": 20, "b": 30, "l": 10, "r": 10},
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "xanchor": "right", "x": 1, "font": {"size": 10}},
        xaxis={"gridcolor": "#E7E2DA", "linecolor": "#E7E2DA", "tickfont": {"size": 10}},
        yaxis={"gridcolor": "#E7E2DA", "linecolor": "#E7E2DA", "tickfont": {"size": 10}},
    )
    base.update(kwargs)
    return base


def layout():
    df = load_df()
    all_counties = sorted(c for c in df["County"].dropna().unique().tolist() if str(c).strip())

    return html.Div([
        html.Div(
            html.Div(
                [
                    html.Div("Trends", className="dca-hero-eyebrow"),
                    html.H1("Distress trends", className="dca-hero-h1"),
                    html.Div(
                        [
                            html.P(
                                "Filing activity broken out by stage and county.",
                                className="dca-hero-lead",
                                style={"margin": "0"},
                            ),
                            dcc.Dropdown(
                                id="trends-county-filter",
                                options=[{"label": c, "value": c} for c in all_counties],
                                value=[],
                                multi=True,
                                placeholder="All counties…",
                                style={"minWidth": "220px", "fontSize": "13px"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center",
                               "justifyContent": "space-between", "gap": "16px",
                               "marginTop": "12px", "flexWrap": "wrap"},
                    ),

                    # Row 1: filings by stage + top counties
                    html.Div(
                        [
                            html.Div([
                                html.Div("Filings by stage", className="dca-chart-title"),
                                html.Div(id="chart-stage-bars"),
                            ], className="dca-card dca-chart-card"),
                            html.Div([
                                html.Div("Top counties", className="dca-chart-title"),
                                html.Div(id="chart-county-bars"),
                            ], className="dca-card dca-chart-card"),
                        ],
                        className="dca-two-col",
                        style={"marginTop": "22px"},
                    ),

                    # Row 2: monthly filings
                    html.Div([
                        html.Div("Monthly filings by stage", className="dca-chart-title"),
                        dcc.Graph(id="chart-monthly",
                                  config={"displayModeBar": False},
                                  style={"height": "300px"}),
                    ], className="dca-card dca-chart-card", style={"marginTop": "16px"}),

                    # Row 3: weekly pace
                    html.Div([
                        html.Div("12-week filing volume", className="dca-chart-title"),
                        dcc.Graph(id="chart-weekly",
                                  config={"displayModeBar": False},
                                  style={"height": "240px"}),
                    ], className="dca-card dca-chart-card", style={"marginTop": "16px"}),

                    # Row 4: density map
                    html.Div([
                        html.Div("Foreclosure density map", className="dca-chart-title"),
                        dcc.Graph(id="chart-density",
                                  config={"displayModeBar": False},
                                  style={"height": "480px"}),
                    ], className="dca-card dca-chart-card",
                       style={"marginTop": "16px", "marginBottom": "40px"}),
                ],
                className="dca-page-inner",
            ),
            className="dca-page-content",
        ),
    ])


@callback(
    Output("chart-stage-bars",  "children"),
    Output("chart-county-bars", "children"),
    Output("chart-monthly",     "figure"),
    Output("chart-weekly",      "figure"),
    Output("chart-density",     "figure"),
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
    total = len(df)

    # ── Stage bars (custom HTML) ──────────────────────────────────────────────
    by_stage = df.groupby("Stage", observed=True).size().reset_index(name="n")
    max_n = by_stage["n"].max() or 1
    stage_bar_items = []
    for _, row in by_stage.sort_values("n", ascending=False).iterrows():
        short = STAGE_SHORT.get(row["Stage"], "")
        color = _NEW_COLORS.get(row["Stage"], "#78716C")
        pct   = row["n"] / total * 100
        stage_bar_items.append(html.Div([
            html.Div(
                [html.Span(short, style={"fontWeight":"600","color":color}),
                 html.Span(f"{pct:.0f}% · ", style={"color":"var(--ink-3)"}),
                 html.Strong(f"{row['n']:,}")],
                className="dca-bar-row-header",
            ),
            html.Div(
                html.Div(style={"width":f"{pct:.1f}%","height":"100%",
                                "background":color,"borderRadius":"4px"}),
                className="dca-bar-track",
            ),
        ], className="dca-bar-row"))

    # ── County bars (custom HTML) ─────────────────────────────────────────────
    by_county = (df.groupby("County", observed=True).size()
                   .reset_index(name="n")
                   .sort_values("n", ascending=False).head(10))
    max_c = by_county["n"].max() or 1
    county_bar_items = []
    for _, row in by_county.iterrows():
        pct = row["n"] / max_c * 100
        county_bar_items.append(html.Div([
            html.Div(
                [html.Span(str(row["County"]), style={"fontWeight":"500","fontSize":"12px"}),
                 html.Strong(f"{row['n']:,}")],
                className="dca-bar-row-header",
            ),
            html.Div(
                html.Div(style={"width":f"{pct:.1f}%","height":"100%",
                                "background":"var(--accent)","borderRadius":"4px"}),
                className="dca-bar-track",
            ),
        ], className="dca-bar-row"))

    # ── Monthly bar chart ─────────────────────────────────────────────────────
    monthly = (df.groupby(["Month","Stage"], observed=True)
                 .size().reset_index(name="Count"))
    fig_monthly = px.bar(
        monthly, x="Month", y="Count", color="Stage",
        color_discrete_map=_NEW_COLORS,
        category_orders={"Stage": _STAGE_ORDER},
        labels={"Month":"","Count":"Filings","Stage":""},
        template="plotly_white",
    )
    fig_monthly.update_layout(**_plotly_layout(bargap=0.2, hovermode="x unified"))
    fig_monthly.update_traces(marker_line_width=0)

    # ── Weekly pace ───────────────────────────────────────────────────────────
    cutoff = df["Recording Date"].max() - pd.Timedelta(weeks=12)
    weekly = (df[df["Recording Date"] >= cutoff]
              .groupby(["Week","Stage"], observed=True)
              .size().reset_index(name="Count"))
    fig_weekly = px.area(
        weekly, x="Week", y="Count", color="Stage",
        color_discrete_map=_NEW_COLORS,
        category_orders={"Stage": _STAGE_ORDER},
        labels={"Week":"","Count":"Filings","Stage":""},
        template="plotly_white",
    )
    fig_weekly.update_layout(**_plotly_layout(hovermode="x unified"))

    # ── Density map ───────────────────────────────────────────────────────────
    geo = df.dropna(subset=["Latitude","Longitude"]).copy()
    geo["Stage Short"] = geo["Stage"].map(STAGE_SHORT).fillna("Other")
    fig_density = px.density_map(
        geo, lat="Latitude", lon="Longitude",
        radius=12, center={"lat":36.8,"lon":-119.4}, zoom=5,
        map_style="carto-positron",
        color_continuous_scale="Reds",
        hover_name="Property Address",
        hover_data={"Latitude":False,"Longitude":False,"Stage Short":True,"County":True},
        height=480,
    )
    fig_density.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin={"t":0,"b":0,"l":0,"r":0},
        coloraxis_showscale=False,
    )

    return (
        stage_bar_items or [html.P("No data", style={"color":"var(--ink-3)"})],
        county_bar_items or [html.P("No data", style={"color":"var(--ink-3)"})],
        fig_monthly, fig_weekly, fig_density,
    )
