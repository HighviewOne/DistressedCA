import dash
from dash import html, dcc, callback, clientside_callback, Output, Input, State, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from dash_extensions.javascript import assign
from data.loader import (
    load_df, filter_df, to_geojson, to_table_records,
    get_headline_stats, STAGE_COLORS, STAGE_SHORT,
)
import pandas as pd
from datetime import date, datetime, timedelta, timezone
import os

dash.register_page(
    __name__,
    path="/",
    title="DistressedCA — California Distressed Properties",
    name="Map",
)

# Custom colored circle markers based on foreclosure stage
point_to_layer = assign("""
function(feature, latlng, context) {
    var stageColors = {1: '#f59e0b', 2: '#ef4444', 3: '#22c55e', 4: '#7c3aed'};
    var color = stageColors[feature.properties.stage_num] || '#6b7280';
    return L.circleMarker(latlng, {
        radius: 7,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.85
    });
}
""")

# Simplified: tooltip only — full details open in sidebar on click
on_each_feature = assign("""
function(feature, layer, context) {
    var p = feature.properties;
    var tip = '<b style="font-size:0.85rem">' + (p.address || 'Unknown') + '</b><br>';
    tip += '<span style="color:' + p.color + ';font-weight:bold">' + (p.stage_short || '') + '</span>';
    if (p.county) tip += ' &middot; ' + p.county;
    if (p.timeline && p.timeline.length > 1)
        tip += '<br><span style="font-size:0.75rem;color:#9ca3af">' + p.timeline.length + ' filings — click for timeline</span>';
    layer.bindTooltip(tip, {sticky: true, direction: 'top', offset: [0, -5]});
}
""")

LEGEND_ITEMS = [
    ("NOD", "#f59e0b", "Notice of Default"),
    ("NTS", "#ef4444", "Notice of Trustee's Sale"),
    ("NOR", "#22c55e", "Notice of Rescission"),
    ("TDUS", "#7c3aed", "Trustee's Deed Upon Sale"),
]


def _badge(label: str, color: str, text: str = "white") -> dbc.Badge:
    return dbc.Badge(label, style={"backgroundColor": color, "color": text}, className="me-1")


def _section(title: str, children: list) -> html.Div:
    return html.Div([
        html.P(title, className="text-uppercase fw-bold mb-1",
               style={"fontSize": "0.7rem", "letterSpacing": "0.08em", "color": "#9ca3af"}),
        *children,
        html.Hr(className="my-2"),
    ])


def _build_sidebar(p: dict) -> list:
    """Build Offcanvas body from a clicked GeoJSON feature's properties dict."""
    color      = p.get("color", "#6b7280")
    stage_short= p.get("stage_short", "")
    timeline   = p.get("timeline") or []

    sections = []

    # ── Stage + confidence badges ─────────────────────────────────────────────
    conf_map = {
        "precise":  ("📍 Rooftop",         "#15803d"),
        "good":     ("📍 Good Match",       "#2563eb"),
        "approx":   ("⚠ Verify Location",  "#d97706"),
        "geocoded": ("📍 Geocoded",         "#6b7280"),
    }
    conf_label, conf_color = conf_map.get(p.get("geocode_confidence","geocoded"),
                                          ("📍 Geocoded", "#6b7280"))
    badges = [dbc.Badge(stage_short, style={"backgroundColor": color}, className="me-1 mb-2")]
    badges.append(dbc.Badge(conf_label,
                             style={"backgroundColor": conf_color, "fontSize": "0.68rem"},
                             className="me-1 mb-2"))
    if p.get("hard_money") == "Yes": badges.append(_badge("Hard Money", "#fbbf24", "#000"))
    if p.get("corporate")  == "Yes": badges.append(_badge("Corporate", "#6b7280"))
    if p.get("source")     == "RETRAN": badges.append(_badge("RETRAN", "#3b82f6"))
    if p.get("high_equity"): badges.append(_badge(f"💰 High Equity {p.get('equity_pct','')}%", "#16a34a"))
    if p.get("low_ltv"):    badges.append(_badge("🔒 Low LTV", "#2563eb"))
    sections.append(html.Div(badges, className="mb-3"))

    # ── Location ──────────────────────────────────────────────────────────────
    sections.append(html.Div([
        html.P([p.get("city",""), "  ", p.get("zip",""), " · ", p.get("county","")],
               className="text-muted small mb-1"),
        html.P(["Recorded: ", html.Strong(p.get("recording_date",""))], className="small mb-0"),
    ], className="mb-3"))

    # ── Auction block ─────────────────────────────────────────────────────────
    if p.get("sale_date"):
        dist = p.get("auction_dist_miles","")
        sections.append(dbc.Alert([
            html.Div([html.Strong(f"🔨 Auction: {p['sale_date']}"),
                      html.Span(f"  at {p['sale_time']}" if p.get("sale_time") else "")]),
            html.Div(p.get("auction_location",""), className="small") if p.get("auction_location") else None,
            html.Div([
                html.Span(f"Min Bid: {p.get('min_bid','')}", className="me-3 fw-bold") if p.get("min_bid") else None,
                html.Span(f"📍 {dist} from property", className="text-muted small") if dist else None,
            ]),
        ], color="danger", className="mb-3 py-2"))

    # ── Timeline ──────────────────────────────────────────────────────────────
    if len(timeline) > 1:
        stage_clrs = {1:"#f59e0b", 2:"#ef4444", 3:"#22c55e", 4:"#7c3aed"}
        tl_items = []
        for i, ev in enumerate(timeline):
            c = stage_clrs.get(ev.get("stage_num", 0), "#6b7280")
            tl_items.append(html.Div([
                html.Span("●", style={"color": c, "marginRight": "6px"}),
                html.Span(ev.get("date",""), className="me-2 text-muted"),
                html.Span(ev.get("stage_short",""), style={"color": c}),
            ], className="small"))
        sections.append(_section(f"Foreclosure Timeline ({len(timeline)} filings)", tl_items))

    # ── Financial ─────────────────────────────────────────────────────────────
    fin = []
    if p.get("loan_amount") and p["loan_amount"] != "N/A":
        fin.append(html.Div([html.Span("Loan Amount: ", className="text-muted small"),
                              html.Strong(p["loan_amount"])]))
    for label, key in [("LTV", "ltv"), ("EMV", "emv"), ("Equity", "equity_pct"),
                        ("Default Amt", "default_amount")]:
        val = p.get(key,"")
        if val:
            fin.append(html.Div([html.Span(f"{label}: ", className="text-muted small"),
                                  html.Strong(val + ("%" if key == "equity_pct" else ""))]))
    if fin:
        sections.append(_section("Financial", fin))

    # ── Property ──────────────────────────────────────────────────────────────
    prop = []
    details = " · ".join(filter(None,[
        (p.get("beds","")  + " bd")   if p.get("beds") else "",
        (p.get("baths","") + " ba")   if p.get("baths") else "",
        (p.get("sqft","")  + " sqft") if p.get("sqft") else "",
        ("Built " + p.get("year_built","")) if p.get("year_built") else "",
    ]))
    if details: prop.append(html.P(details, className="small mb-1"))
    if p.get("assessed_total"):
        prop.append(html.P(["Assessed: ", html.Strong(p["assessed_total"])], className="small mb-1"))
    if p.get("borrower"):
        prop.append(html.P(["Owner: ", p["borrower"]], className="small mb-0"))
    if prop:
        sections.append(_section("Property", prop))

    # ── Trustee / Lender ──────────────────────────────────────────────────────
    tl_items2 = []
    trustee = p.get("trustee_name") or p.get("trustee","")
    if trustee:
        name_el = html.A(trustee, href=p["trustee_url"], target="_blank",
                         rel="noopener noreferrer") if p.get("trustee_url") else html.Span(trustee)
        phone_el = [" ", html.A(p["trustee_phone"], href=f"tel:{p['trustee_phone']}")] \
                   if p.get("trustee_phone") else []
        tl_items2.append(html.P(["Trustee: ", name_el] + phone_el, className="small mb-1"))
    if p.get("beneficiary"):
        phone_el2 = [" ", html.A(p["ben_phone"], href=f"tel:{p['ben_phone']}")] \
                    if p.get("ben_phone") else []
        tl_items2.append(html.P(["Lender: ", p["beneficiary"]] + phone_el2, className="small mb-0"))
    if tl_items2:
        sections.append(_section("Trustee / Lender", tl_items2))

    # ── Research links ────────────────────────────────────────────────────────
    addr = p.get("address","")
    city = p.get("city","")
    if addr and addr != "Address unknown":
        from urllib.parse import quote
        q = quote(f"{addr} {city} CA")
        lat_v, lon_v = p.get("lat_val",""), p.get("lon_val","")
        links = [
            dbc.Button("Zillow", href=f"https://www.zillow.com/homes/{q}_rb/",
                       target="_blank", color="warning", size="sm", className="me-1 mb-1"),
            dbc.Button("Redfin", href=f"https://www.redfin.com/search-page?s={q}",
                       target="_blank", color="danger", size="sm", className="me-1 mb-1"),
        ]
        if lat_v and lon_v:
            links.append(dbc.Button(
                "Street View",
                href=f"https://maps.google.com/maps?q=&layer=c&cbll={lat_v},{lon_v}",
                target="_blank", color="success", size="sm", className="me-1 mb-1"
            ))
        if p.get("source_url"):
            links.append(dbc.Button(
                "County Record", href=p["source_url"],
                target="_blank", color="secondary", outline=True, size="sm", className="mb-1"
            ))
        sections.append(_section("Research", links))

    return sections


def _stat_chip(label: str, color: str, href: str | None = None) -> html.Span:
    style = {
        "backgroundColor": color + "18",  # 10% opacity background
        "color": color,
        "border": f"1px solid {color}44",
        "borderRadius": "999px",
        "padding": "2px 10px",
        "fontSize": "0.78rem",
        "fontWeight": "600",
        "whiteSpace": "nowrap",
        "cursor": "pointer" if href else "default",
        "textDecoration": "none",
    }
    if href:
        return html.A(label, href=href, style=style)
    return html.Span(label, style=style)


def _last_updated() -> str:
    """Human-readable age of the Parquet snapshot."""
    try:
        from data.loader import PARQUET_SNAPSHOT
        mtime = os.path.getmtime(PARQUET_SNAPSHOT)
        age = datetime.now() - datetime.fromtimestamp(mtime)
        hours = int(age.total_seconds() // 3600)
        if hours < 1:
            return "Updated < 1 hour ago"
        if hours < 24:
            return f"Updated {hours}h ago"
        days = hours // 24
        return f"Updated {days}d ago"
    except Exception:
        return ""


def layout():
    df    = load_df()
    stats = get_headline_stats(df)
    all_counties = sorted(c for c in df["County"].dropna().unique().tolist() if str(c).strip())
    all_stages = [s for s in df["Stage"].dropna().unique().tolist() if s.strip() and s in STAGE_COLORS]
    max_loan = int(df["Loan Amount"].max(skipna=True) or 5_000_000)
    min_date  = df["Recording Date"].min()
    max_date  = df["Recording Date"].max()

    # Default date filter: last 7 days of data actually in the file
    # (avoids UTC vs local timezone mismatch on Render)
    latest_rec = df["Recording Date"].dropna().max()
    if pd.notna(latest_rec):
        week_start = (latest_rec - pd.Timedelta(days=6)).date()
    else:
        week_start = date.today() - timedelta(days=7)

    stage_options = []
    for stage in sorted(all_stages):
        short = STAGE_SHORT.get(stage, stage)
        color = STAGE_COLORS.get(stage, "#6b7280")
        stage_options.append({
            "label": html.Span([
                html.Span("●", style={"color": color, "marginRight": "5px", "fontSize": "1rem"}),
                html.Span(short, className="fw-semibold", style={"marginRight": "3px"}),
                html.Span(stage.split("—")[-1].strip() if "—" in stage else "", className="text-muted small"),
            ]),
            "value": stage,
        })

    return dbc.Container([
        dcc.Store(id="loan-defaults",           data={"min": 0, "max": max_loan}),
        dcc.Store(id="sidebar-valuation-store", data=None),
        dcc.Store(id="batch-launch-dummy",      data=None),

        # Property detail sidebar
        dbc.Offcanvas(
            id="property-sidebar",
            title="Property Details",
            placement="end",
            scrollable=True,
            is_open=False,
            style={"width": "390px"},
            children=[
                # Dynamic property content (changes per pin click)
                html.Div(id="sidebar-dynamic-content"),
                html.Hr(className="my-3"),
                # Fixed Max Bid Calculator (persists between clicks)
                html.Div(id="max-bid-section", style={"display": "none"}, children=[
                    html.P("Max Bid Calculator",
                           className="text-uppercase fw-bold mb-2",
                           style={"fontSize": "0.7rem", "letterSpacing": "0.08em",
                                  "color": "#9ca3af"}),
                    dbc.InputGroup([
                        dbc.InputGroupText("Target ROI"),
                        dbc.Input(id="max-bid-pct", type="number", value=20,
                                  min=0, max=100, step=1),
                        dbc.InputGroupText("%"),
                    ], size="sm", className="mb-2"),
                    html.Div(id="max-bid-result",
                             className="fw-bold fs-5 text-success"),
                    html.P("Based on EMV or Assessed Value",
                           className="text-muted small mb-0"),
                ]),
            ],
        ),

        # Navbar
        dbc.Navbar(
            dbc.Container([
                dbc.NavbarBrand([
                    html.Span("🏚", className="me-2"),
                    "DistressedCA",
                ], href="/", className="fw-bold fs-5 text-danger"),
                dbc.Nav([
                    dbc.NavItem(dbc.NavLink("Map",      href="/",        active="exact")),
                    dbc.NavItem(dbc.NavLink("Auctions", href="/auctions")),
                    dbc.NavItem(dbc.NavLink("Trends",   href="/trends")),
                    dbc.NavItem(dbc.NavLink("About",    href="/about")),
                    dbc.NavItem(dbc.NavLink(
                        [html.I(className="bi bi-github me-1"), "GitHub"],
                        href="https://github.com/HighviewOne/DistressedCA",
                        target="_blank", external_link=True,
                    )),
                ], navbar=True, className="ms-auto"),
            ], fluid=True),
            color="dark", dark=True, sticky="top", className="mb-0 py-1",
        ),

        # ── Headline stats bar ────────────────────────────────────────────────
        dbc.Row(dbc.Col(
            html.Div([
                _stat_chip(f"🔨 {stats['auctions_this_week']} auctions this week", "#ef4444",
                           href="/auctions"),
                _stat_chip(f"📋 {stats['new_nods_week']} new NODs (7d)", "#f59e0b"),
                _stat_chip(f"💰 {stats['high_equity']} high-equity leads", "#16a34a"),
                _stat_chip(f"🔒 {stats['low_ltv']} low-LTV leads", "#2563eb"),
            ], className="d-flex flex-wrap gap-2 py-2 px-1"),
        ), className="g-0"),

        # Mobile filter toggle (hidden on desktop)
        dbc.Row(dbc.Col(
            dbc.Button(
                [html.I(className="bi bi-sliders me-2"), "Filters"],
                id="filter-toggle-btn",
                color="secondary", outline=True, size="sm",
                className="d-lg-none w-100 mb-2",
            ),
        ), className="px-2"),

        # Main layout: sidebar + content
        dbc.Row([
            # --- Filters sidebar ---
            dbc.Col([
                dbc.Collapse(id="filter-collapse", is_open=True, children=[
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("Filters", className="mb-0 fw-bold d-inline"),
                        dbc.Button(
                            [html.I(className="bi bi-arrow-counterclockwise me-1"), "Reset"],
                            id="reset-filters-btn", size="sm", color="link",
                            className="float-end p-0 text-muted",
                        ),
                    ]),
                    dbc.CardBody([

                        # Stage
                        html.Label("Foreclosure Stage", className="small fw-bold text-muted mb-1"),
                        dbc.Checklist(
                            id="stage-filter",
                            options=stage_options,
                            value=all_stages,
                            className="mb-3",
                        ),
                        html.Hr(className="my-2"),

                        # County
                        html.Label("County", className="small fw-bold text-muted mb-1"),
                        dcc.Dropdown(
                            id="county-filter",
                            options=[{"label": c, "value": c} for c in all_counties],
                            value=[],
                            multi=True,
                            placeholder="All counties...",
                            className="mb-3",
                        ),
                        html.Hr(className="my-2"),

                        # Recording Date
                        html.Label("Recording Date", className="small fw-bold text-muted mb-1"),
                        dcc.DatePickerRange(
                            id="date-filter",
                            min_date_allowed=min_date.date() if pd.notna(min_date) else None,
                            max_date_allowed=max_date.date() if pd.notna(max_date) else None,
                            start_date=week_start,
                            display_format="YYYY-MM-DD",
                            className="mb-3 w-100",
                            style={"fontSize": "0.8rem"},
                        ),
                        html.Hr(className="my-2"),

                        # Loan Amount
                        html.Label("Loan Amount", className="small fw-bold text-muted mb-1"),
                        html.Div(id="loan-range-label", className="small text-muted mb-1"),
                        dcc.RangeSlider(
                            id="loan-slider",
                            min=0,
                            max=max_loan,
                            step=25_000,
                            value=[0, max_loan],
                            marks={
                                0: {"label": "$0", "style": {"fontSize": "0.7rem"}},
                                max_loan: {"label": f"${max_loan // 1_000_000:.0f}M+", "style": {"fontSize": "0.7rem"}},
                            },
                            tooltip={"placement": "bottom", "always_visible": False},
                            className="mb-3",
                        ),
                        html.Hr(className="my-2"),

                        # Flag filters
                        html.Label("Property Flags", className="small fw-bold text-muted mb-1"),
                        dbc.Checklist(
                            id="flag-filter",
                            options=[
                                {"label": "Hard Money Loan Only", "value": "hard_money"},
                                {"label": "Corporate Grantor Only", "value": "corporate"},
                                {"label": html.Span([
                                    html.Span("Upcoming Auctions Only ", style={"color": "#ef4444", "fontWeight": "600"}),
                                    html.Span("(NTS with sale date)", className="text-muted"),
                                ]), "value": "upcoming_auctions"},
                                {"label": html.Span([
                                    html.Span("💰 High Equity ", style={"color": "#16a34a", "fontWeight": "600"}),
                                    html.Span("(EMV − Loan > 30%)", className="text-muted"),
                                ]), "value": "high_equity"},
                                {"label": html.Span([
                                    html.Span("🔒 Low LTV ", style={"color": "#2563eb", "fontWeight": "600"}),
                                    html.Span("(< 50%)", className="text-muted"),
                                ]), "value": "low_ltv"},
                            ],
                            value=[],
                            switch=True,
                            className="small",
                        ),
                    ], style={"overflowY": "auto", "maxHeight": "70vh"}),
                ], className="mb-2"),

                # Stats card
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("Results", className="mb-0 fw-bold d-inline"),
                        html.Span(
                            _last_updated(),
                            className="float-end small text-muted fst-italic",
                            style={"fontSize": "0.7rem", "lineHeight": "1.8"},
                        ),
                    ]),
                    dbc.CardBody(html.Div(id="stats-panel", className="small")),
                ]),
                ]),  # end Collapse
            ], lg=3, md=12, className="p-2"),

            # --- Map + Table ---
            dbc.Col([
                # Download component (invisible, triggered by callback)
                dcc.Download(id="download-csv"),
                dcc.Download(id="download-mailing"),

                # Map card
                dbc.Card([
                    dcc.Loading(type="circle", color="#ef4444", children=
                    dl.Map(
                        id="main-map",
                        center=[36.8, -119.4],
                        zoom=6,
                        style={"height": "56vh", "width": "100%", "borderRadius": "4px"},
                        children=[
                            dl.LayersControl([
                                dl.BaseLayer(
                                    dl.TileLayer(
                                        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                                        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                                        maxZoom=19,
                                    ),
                                    name="Street Map", checked=True,
                                ),
                                dl.BaseLayer(
                                    dl.TileLayer(
                                        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                                        attribution="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
                                        maxZoom=19,
                                    ),
                                    name="Satellite",
                                ),
                            ]),
                            dl.GeoJSON(
                                id="map-layer",
                                data={"type": "FeatureCollection", "features": []},
                                pointToLayer=point_to_layer,
                                onEachFeature=on_each_feature,
                                cluster=True,
                                zoomToBoundsOnClick=True,
                                superClusterOptions={"radius": 80, "maxZoom": 16},
                            ),
                        ],
                    ),
                    ),  # end dcc.Loading
                ], className="mb-1 p-0 border-0 overflow-hidden"),

                # Legend
                dbc.Row([dbc.Col(html.Div([
                    html.Span([
                        html.Span("●", style={"color": color, "marginRight": "2px"}),
                        html.Span(f" {short}  ", className="small text-muted"),
                    ])
                    for short, color, _ in LEGEND_ITEMS
                ] + [
                    html.Span("  Clusters zoom in on click", className="small text-muted fst-italic"),
                ]))], className="mb-2 px-1"),

                # Data table
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("Property Records", className="mb-0 fw-bold d-inline"),
                        html.Span(id="table-count", className="ms-2 small text-muted"),
                        dbc.Button(
                            [html.I(className="bi bi-rocket me-1"), "Research Selected"],
                            id="batch-launch-btn", size="sm", color="success",
                            outline=True, disabled=True, className="float-end ms-2",
                        ),
                        dbc.Button(
                            [html.I(className="bi bi-envelope me-1"), "Mailing CSV"],
                            id="mailing-btn", size="sm", color="primary",
                            outline=True, className="float-end ms-2",
                        ),
                        dbc.Button(
                            [html.I(className="bi bi-download me-1"), "Export CSV"],
                            id="export-btn", size="sm", color="secondary",
                            outline=True, className="float-end ms-2",
                        ),
                        dbc.Switch(
                            id="bounds-filter-switch",
                            label="Current map view only",
                            value=False,
                            className="float-end small mt-1",
                            style={"fontSize": "0.8rem"},
                        ),
                    ]),
                    dbc.CardBody(
                        dcc.Loading(type="dot", color="#ef4444",
                            children=html.Div(id="table-container", style={"overflowX": "auto"}),
                        ),
                        className="p-1",
                    ),
                ]),
            ], lg=9, md=12, className="p-2"),
        ], className="g-0"),
    ], fluid=True, className="p-0")


@callback(
    Output("map-layer", "data"),
    Output("stats-panel", "children"),
    Output("table-container", "children"),
    Output("table-count", "children"),
    Output("loan-range-label", "children"),
    Input("county-filter", "value"),
    Input("stage-filter", "value"),
    Input("date-filter", "start_date"),
    Input("date-filter", "end_date"),
    Input("loan-slider", "value"),
    Input("flag-filter", "value"),
    Input("bounds-filter-switch", "value"),
    State("main-map", "center"),
    State("main-map", "zoom"),
)
def update_all(counties, stages, date_start, date_end, loan_range, flags,
               bounds_active, map_center, map_zoom):
    df = load_df()

    hard_money       = "hard_money"       in (flags or [])
    corporate        = "corporate"        in (flags or [])
    upcoming_auctions= "upcoming_auctions"in (flags or [])
    high_equity      = "high_equity"      in (flags or [])
    low_ltv          = "low_ltv"          in (flags or [])
    loan_min = loan_range[0] if loan_range else None
    loan_max = loan_range[1] if loan_range else None

    filtered = filter_df(
        df,
        counties=counties or None,
        stages=stages or None,
        date_start=date_start,
        date_end=date_end,
        hard_money=hard_money,
        corporate=corporate,
        loan_min=loan_min,
        loan_max=loan_max,
        upcoming_auctions=upcoming_auctions,
        high_equity=high_equity,
        low_ltv=low_ltv,
    )

    geojson = to_geojson(filtered)
    geocoded_count = len(geojson["features"])
    total_count = len(filtered)
    stage_counts = filtered["Stage"].value_counts()

    # Loan range label
    lo = loan_range[0] if loan_range else 0
    hi = loan_range[1] if loan_range else 0
    loan_label = f"${lo:,.0f} – ${hi:,.0f}"

    # Stats
    stats = [
        dbc.Row([
            dbc.Col(html.Div([
                html.Span(f"{total_count:,}", className="fw-bold fs-4 text-primary"),
                html.Div("total filings", className="text-muted"),
            ]), width=6),
            dbc.Col(html.Div([
                html.Span(f"{geocoded_count:,}", className="fw-bold fs-4"),
                html.Div("unique properties", className="text-muted"),
            ]), width=6),
        ], className="mb-2 text-center"),
        html.Hr(className="my-1"),
    ]
    for stage, color in STAGE_COLORS.items():
        count = int(stage_counts.get(stage, 0))
        short = STAGE_SHORT.get(stage, stage)
        desc = stage.split("—")[-1].strip() if "—" in stage else stage
        stats.append(
            html.Div([
                html.Span("●", style={"color": color, "marginRight": "5px"}),
                html.Span(f"{short}: ", className="fw-semibold"),
                html.Span(f"{count:,}", className="fw-bold"),
                html.Span(f"  {desc}", className="text-muted"),
            ], className="mb-1 small")
        )
    if total_count > 0:
        upcoming = int(filtered["Sale Date"].notna().sum()) if "Sale Date" in filtered.columns else 0
        if upcoming:
            stats.append(html.Hr(className="my-1"))
            stats.append(html.Div([
                html.Span("🔴 ", style={"fontSize": "0.75rem"}),
                html.Span(f"{upcoming:,} properties with scheduled auction", className="text-danger fw-semibold"),
            ], className="small"))

    # Table — only show records that are on the map (geocoded)
    on_map = filtered.dropna(subset=["Latitude", "Longitude"])

    # Bounds filter: restrict table (not map) to current viewport
    table_df = on_map
    if bounds_active and map_center and map_zoom is not None:
        lat, lon = map_center
        # Approximate visible span: generous (4× tile width) to avoid clipping edges
        lon_span = (360 / (2 ** int(map_zoom))) * 4
        lat_span = lon_span * 0.65
        table_df = on_map[
            on_map["Latitude"].between(lat - lat_span / 2, lat + lat_span / 2) &
            on_map["Longitude"].between(lon - lon_span / 2, lon + lon_span / 2)
        ]

    records = to_table_records(table_df)
    visible_count = len(table_df)
    suffix = " in view" if bounds_active else " on map"
    table_count_text = f"(showing {min(len(records), 500):,} of {visible_count:,}{suffix})"
    if not records:
        table = html.P("No records match the current filters.", className="text-muted small p-3 mb-0")
    else:
        cols = list(records[0].keys())
        table = dash_table.DataTable(
            id="main-table",
            data=records,
            columns=[{"name": c, "id": c} for c in cols],
            row_selectable="multi",
            selected_rows=[],
            page_size=20,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto", "fontSize": "0.8rem"},
            style_header={
                "fontWeight": "bold",
                "backgroundColor": "#f1f5f9",
                "borderBottom": "2px solid #e2e8f0",
                "padding": "6px 8px",
            },
            style_cell={
                "padding": "4px 8px",
                "textAlign": "left",
                "whiteSpace": "normal",
                "border": "1px solid #e2e8f0",
                "maxWidth": "200px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_data_conditional=[
                {
                    "if": {"filter_query": '{Stage} contains "NTS"'},
                    "backgroundColor": "#fff1f1",
                },
                {
                    "if": {"filter_query": '{Stage} contains "TDUS"'},
                    "backgroundColor": "#f5f3ff",
                },
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": "#fafafa",
                },
                {
                    "if": {"filter_query": "{High Equity} = True"},
                    "backgroundColor": "#f0fdf4",
                    "borderLeft": "3px solid #16a34a",
                },
                {
                    "if": {"filter_query": "{Low LTV} = True"},
                    "backgroundColor": "#eff6ff",
                    "borderLeft": "3px solid #2563eb",
                },
            ],
            style_filter={"backgroundColor": "#f8fafc"},
        )

    return geojson, stats, table, table_count_text, loan_label


@callback(
    Output("download-csv", "data"),
    Input("export-btn", "n_clicks"),
    State("county-filter", "value"),
    State("stage-filter", "value"),
    State("date-filter", "start_date"),
    State("date-filter", "end_date"),
    State("loan-slider", "value"),
    State("flag-filter", "value"),
    prevent_initial_call=True,
)
def export_csv(n_clicks, counties, stages, date_start, date_end, loan_range, flags):
    if not n_clicks:
        raise PreventUpdate
    df = load_df()
    hard_money = "hard_money" in (flags or [])
    corporate  = "corporate"  in (flags or [])
    upcoming   = "upcoming_auctions" in (flags or [])
    filtered = filter_df(
        df,
        counties=counties or None,
        stages=stages or None,
        date_start=date_start,
        date_end=date_end,
        hard_money=hard_money,
        corporate=corporate,
        loan_min=loan_range[0] if loan_range else None,
        loan_max=loan_range[1] if loan_range else None,
        upcoming_auctions=upcoming,
    )
    on_map = filtered.dropna(subset=["Latitude", "Longitude"])
    export_cols = [
        "Recording Date", "Property Address", "City", "ZIP", "County", "Stage",
        "Loan Amount", "Sale Date", "Min Bid", "Auction Location", "LTV",
        "Borrower Name", "Trustee/Lender", "Trustee Name", "Trustee Phone",
        "Beneficiary", "Ben Phone", "Hard Money Loan?", "Corporate Grantor?",
        "Beds", "Baths", "Sq Ft", "Year Built",
        "Assessed Total($)", "Latitude", "Longitude", "Source URL", "Source",
    ]
    available = [c for c in export_cols if c in on_map.columns]
    export_df = on_map[available].copy()
    # Clean dates to ISO strings, leave numbers raw
    for col in ["Recording Date", "Sale Date"]:
        if col in export_df.columns:
            export_df[col] = export_df[col].apply(
                lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
            )
    filename = f"distressedca_{date.today()}.csv"
    return dcc.send_data_frame(export_df.to_csv, filename, index=False)


# ── Mobile sidebar toggle ─────────────────────────────────────────────────────
@callback(
    Output("filter-collapse", "is_open"),
    Input("filter-toggle-btn", "n_clicks"),
    State("filter-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_sidebar(n_clicks, is_open):
    return not is_open


# ── Reset all filters to defaults ─────────────────────────────────────────────
@callback(
    Output("stage-filter",  "value"),
    Output("county-filter", "value"),
    Output("date-filter",   "start_date"),
    Output("date-filter",   "end_date"),
    Output("flag-filter",   "value"),
    Input("reset-filters-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_):
    df = load_df()
    all_stages = [s for s in df["Stage"].dropna().unique().tolist()
                  if s.strip() and s in STAGE_COLORS]
    df2 = load_df()
    latest = df2["Recording Date"].dropna().max()
    default_start = (latest - pd.Timedelta(days=6)).date() if pd.notna(latest) else None
    return all_stages, [], default_start, None, []


@callback(
    Output("loan-slider", "value"),
    Input("reset-filters-btn", "n_clicks"),
    State("loan-defaults", "data"),
    prevent_initial_call=True,
)
def reset_loan_slider(_, defaults):
    return [defaults["min"], defaults["max"]]


@callback(
    Output("download-mailing", "data"),
    Input("mailing-btn", "n_clicks"),
    State("county-filter", "value"),
    State("stage-filter", "value"),
    State("date-filter", "start_date"),
    State("date-filter", "end_date"),
    State("loan-slider", "value"),
    State("flag-filter", "value"),
    prevent_initial_call=True,
)
def export_mailing(n_clicks, counties, stages, date_start, date_end, loan_range, flags):
    if not n_clicks:
        raise PreventUpdate
    df = load_df()
    filtered = filter_df(
        df,
        counties=counties or None,
        stages=stages or None,
        date_start=date_start,
        date_end=date_end,
        hard_money="hard_money" in (flags or []),
        corporate="corporate" in (flags or []),
        loan_min=loan_range[0] if loan_range else None,
        loan_max=loan_range[1] if loan_range else None,
        upcoming_auctions="upcoming_auctions" in (flags or []),
        high_equity="high_equity" in (flags or []),
        low_ltv="low_ltv" in (flags or []),
    )
    # Mailing list uses all filtered records (not just geocoded) — broader reach
    mailing = filtered.copy()

    # Clean borrower name: strip lender prefix where possible
    def _clean_owner(name):
        name = str(name or "").strip()
        # Remove common lender/servicer prefixes (e.g. "GOODLEAP LLC GARCIA JUAN" → "GARCIA JUAN")
        import re as _re
        m = _re.search(
            r'(?:LLC|INC\.?|CORP(?:ORATION)?|CREDIT\s+UNION|SERVICES?)\s+(.{4,})$',
            name, _re.I
        )
        return m.group(1).strip() if m else name

    out = pd.DataFrame({
        "Owner_Name":       mailing["Borrower Name"].apply(_clean_owner),
        "Property_Address": mailing["Property Address"].fillna(""),
        "Property_City":    mailing["City"].fillna(""),
        "Property_State":   "CA",
        "Property_ZIP":     mailing["ZIP"].fillna("").astype(str).str.split(".").str[0],
        "County":           mailing["County"].fillna(""),
        "Stage":            mailing["Stage"].fillna(""),
        "Recording_Date":   mailing["Recording Date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
        ),
        "Loan_Amount":      mailing["Loan Amount"].fillna(""),
        "APN":              mailing["APN"].fillna(""),
        "Hard_Money":       mailing["Hard Money Loan?"].fillna(""),
    })
    # Drop rows with no address (useless for mailing)
    out = out[out["Property_Address"].str.strip() != ""]
    filename = f"distressedca_mailing_{date.today()}.csv"
    return dcc.send_data_frame(out.to_csv, filename, index=False)


# ── Property detail sidebar ───────────────────────────────────────────────────
@callback(
    Output("sidebar-dynamic-content", "children"),
    Output("property-sidebar",         "title"),
    Output("property-sidebar",         "is_open"),
    Output("sidebar-valuation-store",  "data"),
    Output("max-bid-section",          "style"),
    Input("map-layer", "clickData"),
    prevent_initial_call=True,
)
def open_sidebar(click_data):
    if not click_data:
        raise PreventUpdate
    props = click_data.get("properties", {})
    if not props.get("address"):
        raise PreventUpdate

    content = _build_sidebar(props)
    title   = props.get("address", "Property Details")

    # Extract numeric valuation for Max Bid Calculator (EMV preferred, Assessed fallback)
    valuation = None
    for raw in [props.get("emv",""), props.get("assessed_total","")]:
        clean = str(raw or "").replace("$","").replace(",","").strip()
        try:
            v = float(clean)
            if v > 0:
                valuation = v
                break
        except (ValueError, TypeError):
            pass
    show_calc = {"display": "block"} if valuation else {"display": "none"}
    return content, title, True, valuation, show_calc


# ── Max Bid Calculator (clientside) ──────────────────────────────────────────
clientside_callback(
    """function(pct, valuation) {
        if (!valuation || pct === null || pct === undefined) return '';
        var bid = valuation * (1 - pct / 100);
        if (bid <= 0) return 'Max Bid: —';
        return 'Max Bid: $' + Math.round(bid).toLocaleString('en-US');
    }""",
    Output("max-bid-result", "children"),
    Input("max-bid-pct", "value"),
    Input("sidebar-valuation-store", "data"),
)


# ── Batch Research Launcher (clientside) ──────────────────────────────────────
clientside_callback(
    """function(n_clicks, selected_rows, table_data) {
        if (!n_clicks || !selected_rows || selected_rows.length === 0)
            return window.dash_clientside.no_update;
        var max_tabs = Math.min(selected_rows.length, 10);
        for (var i = 0; i < max_tabs; i++) {
            var row = table_data[selected_rows[i]];
            if (!row) continue;
            var addr = encodeURIComponent(
                (row['Property Address'] || '') + ' ' + (row['City'] || '') + ' CA'
            );
            window.open('https://www.zillow.com/homes/' + addr + '_rb/', '_blank');
        }
        return null;
    }""",
    Output("batch-launch-dummy", "data"),
    Input("batch-launch-btn", "n_clicks"),
    State("main-table", "selected_rows"),
    State("main-table", "data"),
    prevent_initial_call=True,
)


# ── Update batch button label + enabled state ─────────────────────────────────
@callback(
    Output("batch-launch-btn", "children"),
    Output("batch-launch-btn", "disabled"),
    Input("main-table", "selected_rows"),
    prevent_initial_call=True,
)
def update_batch_btn(selected):
    n = len(selected or [])
    label = [html.I(className="bi bi-rocket me-1"),
             f"Research {n} Selected" if n > 0 else "Research Selected"]
    return label, n == 0
