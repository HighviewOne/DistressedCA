import dash
from dash import html, dcc, callback, Output, Input, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date
from data.loader import load_df, _calc_auction_dist, STAGE_COLORS, STAGE_SHORT

dash.register_page(
    __name__,
    path="/auctions",
    title="Upcoming Auctions — DistressedCA",
    name="Auctions",
)

_NAVBAR_LINKS = [
    ("Map",      "/",         False),
    ("Auctions", "/auctions", True),
    ("Trends",   "/trends",   False),
    ("About",    "/about",    False),
]


def _navbar():
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand([html.Span("🏚", className="me-2"), "DistressedCA"],
                            href="/", className="fw-bold fs-5 text-danger"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink(name, href=href, active=active))
                for name, href, active in _NAVBAR_LINKS
            ] + [dbc.NavItem(dbc.NavLink(
                [html.I(className="bi bi-github me-1"), "GitHub"],
                href="https://github.com/HighviewOne/DistressedCA",
                target="_blank", external_link=True,
            ))], navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark", dark=True, sticky="top", className="mb-0 py-1",
    )


def layout():
    df = load_df()
    all_counties = sorted(df["County"].dropna().unique().tolist())

    upcoming = df[df["Sale Date"].notna() &
                  (df["Sale Date"] >= pd.Timestamp("today").normalize())].copy()
    total = len(upcoming)
    this_week = (upcoming["Sale Date"] <= pd.Timestamp("today") + pd.Timedelta(days=7)).sum()
    total_min_bid = upcoming["Min Bid"].dropna().sum()

    max_bid_raw = upcoming["Min Bid"].max(skipna=True) or 5_000_000

    return dbc.Container([
        _navbar(),
        dbc.Container([
            # Header row
            dbc.Row([
                dbc.Col([
                    html.H4("Upcoming Trustee Sale Auctions", className="fw-bold mt-3 mb-0"),
                    html.P(f"{total:,} scheduled auctions · {this_week:,} this week · "
                           f"Total min bids: ${total_min_bid:,.0f}",
                           className="text-muted small mb-3"),
                ], md=8),
                dbc.Col([
                    dcc.Dropdown(
                        id="auctions-county",
                        options=[{"label": c, "value": c} for c in all_counties],
                        value=[],
                        multi=True,
                        placeholder="All counties",
                        className="mt-3",
                    ),
                ], md=4),
            ]),

            # Min bid slider
            dbc.Row([
                dbc.Col([
                    html.Label("Min Bid Range", className="small fw-bold text-muted mb-1"),
                    dcc.RangeSlider(
                        id="auctions-bid-slider",
                        min=0, max=int(max_bid_raw), step=25_000,
                        value=[0, int(max_bid_raw)],
                        marks={0: "$0", int(max_bid_raw): f"${max_bid_raw/1e6:.1f}M"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                ], md=8),
                dbc.Col([
                    dbc.Button(
                        [html.I(className="bi bi-download me-1"), "Export CSV"],
                        id="auctions-export-btn", color="secondary",
                        outline=True, size="sm", className="mt-4 w-100",
                    ),
                    dcc.Download(id="auctions-download"),
                ], md=4),
            ], className="mb-3"),

            # Stats cards
            html.Div(id="auctions-stats", className="mb-3"),

            # Table
            dbc.Card([
                dbc.CardBody(
                    dcc.Loading(
                        html.Div(id="auctions-table"),
                        type="dot", color="#ef4444",
                    ),
                    className="p-1",
                ),
            ]),
        ], fluid=True, className="pb-5"),
    ], fluid=True, className="p-0")


def _build_auction_records(df: pd.DataFrame) -> list[dict]:
    """Convert filtered auction DataFrame to table-ready records."""
    today = pd.Timestamp("today").normalize()
    cols_out = []
    for _, row in df.iterrows():
        sale_date = row.get("Sale Date")
        days_until = (sale_date - today).days if pd.notna(sale_date) else None
        min_bid = row.get("Min Bid")
        emv_raw = row.get("EMV") or row.get("Assessed Total($)")
        try:
            emv = float(str(emv_raw or "").replace("$","").replace(",",""))
        except (ValueError, TypeError):
            emv = None
        equity = row.get("Equity %")
        lat, lon = row.get("Latitude"), row.get("Longitude")
        auction_loc = str(row.get("Auction Location") or "").strip()
        dist = _calc_auction_dist(lat, lon, auction_loc) \
               if pd.notna(lat) and pd.notna(lon) else ""

        cols_out.append({
            "Sale Date":   sale_date.strftime("%Y-%m-%d") if pd.notna(sale_date) else "",
            "Days Away":   days_until if days_until is not None else "",
            "Time":        str(row.get("Sale Time") or "").strip(),
            "Address":     str(row.get("Property Address") or "").strip(),
            "City":        str(row.get("City") or "").strip(),
            "County":      str(row.get("County") or "").strip(),
            "Min Bid":     f"${min_bid:,.0f}" if pd.notna(min_bid) else "",
            "Distance":    dist,
            "Auction Site":auction_loc.replace(" nan","").strip(" ,"),
            "EMV":         f"${emv:,.0f}" if emv else "",
            "Equity %":    f"{equity:.1f}%" if pd.notna(equity) else "",
            "Loan Amount": f"${row['Loan Amount']:,.0f}" if pd.notna(row.get("Loan Amount")) else "",
            "Stage":       STAGE_SHORT.get(str(row.get("Stage") or ""), ""),
        })
    return cols_out


@callback(
    Output("auctions-table",  "children"),
    Output("auctions-stats",  "children"),
    Input("auctions-county",      "value"),
    Input("auctions-bid-slider",  "value"),
)
def update_auctions(counties, bid_range):
    df = load_df()
    today = pd.Timestamp("today").normalize()

    upcoming = df[df["Sale Date"].notna() &
                  (df["Sale Date"] >= today)].copy()

    if counties:
        upcoming = upcoming[upcoming["County"].isin(counties)]
    if bid_range:
        lo, hi = bid_range
        mask = upcoming["Min Bid"].isna() | upcoming["Min Bid"].between(lo, hi)
        upcoming = upcoming[mask]

    upcoming = upcoming.sort_values("Sale Date")
    records = _build_auction_records(upcoming)

    # Stats cards
    this_week = upcoming[upcoming["Sale Date"] <= today + pd.Timedelta(days=7)]
    by_county = upcoming["County"].value_counts().head(5)
    stats = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Span(f"{len(upcoming):,}", className="fw-bold fs-3 text-danger"),
            html.Div("total upcoming", className="text-muted small"),
        ]), className="text-center"), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Span(f"{len(this_week):,}", className="fw-bold fs-3 text-warning"),
            html.Div("this week", className="text-muted small"),
        ]), className="text-center"), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Span(f"${upcoming['Min Bid'].dropna().sum()/1e6:.1f}M",
                      className="fw-bold fs-3"),
            html.Div("total min bids", className="text-muted small"),
        ]), className="text-center"), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Span(
                str(int(upcoming[upcoming.get("High Equity", pd.Series(False))
                                  .astype(bool)].shape[0])),
                className="fw-bold fs-3 text-success",
            ),
            html.Div("high-equity auctions", className="text-muted small"),
        ]), className="text-center"), md=3),
    ], className="g-2")

    if not records:
        table = html.P("No upcoming auctions match the current filters.",
                       className="text-muted p-3 mb-0")
        return table, stats

    cols = list(records[0].keys())
    table = dash_table.DataTable(
        id="auctions-main-table",
        data=records,
        columns=[{"name": c, "id": c} for c in cols],
        sort_action="native",
        filter_action="native",
        page_size=25,
        style_table={"overflowX": "auto", "fontSize": "0.82rem"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f1f5f9",
                      "borderBottom": "2px solid #e2e8f0"},
        style_cell={"padding": "5px 8px", "textAlign": "left", "border": "1px solid #e2e8f0"},
        style_data_conditional=[
            {"if": {"filter_query": "{Days Away} = 0 || {Days Away} = 1 || {Days Away} = 2"},
             "backgroundColor": "#fff1f1", "borderLeft": "3px solid #ef4444"},
            {"if": {"filter_query": '{Equity %} contains "%"'},
             "backgroundColor": "#f0fdf4"},
            {"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"},
        ],
    )
    return table, stats


@callback(
    Output("auctions-download", "data"),
    Input("auctions-export-btn", "n_clicks"),
    Input("auctions-county", "value"),
    Input("auctions-bid-slider", "value"),
    prevent_initial_call=True,
)
def export_auctions(n_clicks, counties, bid_range):
    from dash.exceptions import PreventUpdate
    if not n_clicks:
        raise PreventUpdate
    df = load_df()
    today = pd.Timestamp("today").normalize()
    upcoming = df[df["Sale Date"].notna() & (df["Sale Date"] >= today)].copy()
    if counties:
        upcoming = upcoming[upcoming["County"].isin(counties)]
    if bid_range:
        lo, hi = bid_range
        mask = upcoming["Min Bid"].isna() | upcoming["Min Bid"].between(lo, hi)
        upcoming = upcoming[mask]
    upcoming = upcoming.sort_values("Sale Date")
    records = _build_auction_records(upcoming)
    out = pd.DataFrame(records)
    return dcc.send_data_frame(out.to_csv, f"auctions_{date.today()}.csv", index=False)
