import dash
from dash import html, dcc, callback, Output, Input, State, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from dash_extensions.javascript import assign
from data.loader import (
    load_df, filter_df, to_geojson, to_table_records,
    STAGE_COLORS, STAGE_SHORT,
)
import pandas as pd
from datetime import date, datetime, timezone
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

# Popup shown on marker click
on_each_feature = assign("""
function(feature, layer, context) {
    var p = feature.properties;
    var popup = '<div style="min-width:240px;font-size:0.85rem;line-height:1.6">';

    // Header: address + stage badge
    popup += '<b style="font-size:0.95rem">' + (p.address || 'Address unknown') + '</b><br>';
    if (p.city) popup += p.city + (p.zip ? '&nbsp;' + p.zip : '') + '<br>';
    popup += '<span style="background:' + p.color + ';color:#fff;padding:1px 7px;border-radius:3px;font-size:0.75rem;font-weight:bold">' + (p.stage_short || '') + '</span>';
    if (p.county) popup += ' <span style="font-size:0.8rem;color:#555">' + p.county + '</span>';
    popup += '<br>';

    // Auction block (NTS only)
    if (p.sale_date) {
        popup += '<div style="margin:6px 0;padding:6px 8px;background:#fff1f1;border-left:3px solid #ef4444;border-radius:2px">';
        popup += '<b style="color:#ef4444">&#127942; Auction: ' + p.sale_date;
        if (p.sale_time) popup += ' at ' + p.sale_time;
        popup += '</b>';
        if (p.auction_location) popup += '<br><span style="font-size:0.78rem">' + p.auction_location + '</span>';
        if (p.min_bid) popup += '<br>Min Bid: <b>' + p.min_bid + '</b>';
        popup += '</div>';
    }

    // Financial row
    popup += 'Loan: <b>' + (p.loan_amount || 'N/A') + '</b>';
    if (p.ltv) popup += ' &nbsp;LTV: <b>' + p.ltv + '</b>';
    if (p.emv) popup += ' &nbsp;EMV: ' + p.emv;
    popup += '<br>';

    if (p.default_amount) popup += 'Default Amt: <b>' + p.default_amount + '</b><br>';
    popup += 'Recorded: ' + (p.recording_date || '') + '<br>';
    if (p.borrower) popup += 'Borrower: ' + p.borrower + '<br>';

    // Property details
    if (p.beds || p.baths || p.sqft || p.year_built) {
        var details = [];
        if (p.beds) details.push(p.beds + ' bd');
        if (p.baths) details.push(p.baths + ' ba');
        if (p.sqft) details.push(p.sqft + ' sqft');
        if (p.year_built) details.push('Built ' + p.year_built);
        popup += details.join(' &middot; ') + '<br>';
    }
    if (p.assessed_total) popup += 'Assessed: ' + p.assessed_total + '<br>';

    if (p.beneficiary) {
        popup += 'Lender: ' + p.beneficiary;
        if (p.ben_phone) popup += ' <a href="tel:' + p.ben_phone + '">' + p.ben_phone + '</a>';
        popup += '<br>';
    }

    // Badges
    var badges = '';
    if (p.hard_money === 'Yes') badges += '<span style="background:#fbbf24;color:#000;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px">Hard Money</span>';
    if (p.corporate === 'Yes') badges += '<span style="background:#6b7280;color:#fff;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px">Corporate</span>';
    if (p.source === 'RETRAN') badges += '<span style="background:#3b82f6;color:#fff;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px">RETRAN</span>';
    if (p.high_equity) badges += '<span style="background:#16a34a;color:#fff;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px">💰 High Equity ' + (p.equity_pct ? p.equity_pct + '%' : '') + '</span>';
    if (p.low_ltv) badges += '<span style="background:#2563eb;color:#fff;padding:1px 5px;border-radius:3px;font-size:0.7rem">🔒 Low LTV</span>';
    if (badges) popup += badges + '<br>';

    // Trustee portal link
    var trustee_display = p.trustee_name || p.trustee || '';
    if (trustee_display) {
        popup += 'Trustee: ';
        if (p.trustee_url) {
            popup += '<a href="' + p.trustee_url + '" target="_blank" rel="noopener noreferrer">' + trustee_display + '</a>';
        } else {
            popup += trustee_display;
        }
        if (p.trustee_phone) popup += ' <a href="tel:' + p.trustee_phone + '">' + p.trustee_phone + '</a>';
        popup += '<br>';
    }

    // County recorder link
    if (p.source_url) popup += '<a href="' + p.source_url + '" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem">County Record ↗</a>  ';

    // One-click research suite
    if (p.address && p.address !== 'Address unknown') {
        var full_addr = encodeURIComponent(p.address + ' ' + (p.city || '') + ' CA');
        var lat = p.lat_val, lon = p.lon_val;
        popup += '<span style="font-size:0.8rem">';
        popup += '<a href="https://www.zillow.com/homes/' + full_addr + '_rb/" target="_blank" rel="noopener noreferrer">Zillow</a> · ';
        popup += '<a href="https://www.redfin.com/search-page?s=' + full_addr + '" target="_blank" rel="noopener noreferrer">Redfin</a>';
        if (p.lat_val && p.lon_val) {
            popup += ' · <a href="https://maps.google.com/maps?q=&layer=c&cbll=' + p.lat_val + ',' + p.lon_val + '" target="_blank" rel="noopener noreferrer">Street View</a>';
        }
        popup += '</span>';
    }

    popup += '</div>';
    layer.bindPopup(popup, {maxWidth: 300});
    layer.bindTooltip(p.address || 'Click for details', {sticky: true, direction: 'top', offset: [0, -5]});
}
""")

LEGEND_ITEMS = [
    ("NOD", "#f59e0b", "Notice of Default"),
    ("NTS", "#ef4444", "Notice of Trustee's Sale"),
    ("NOR", "#22c55e", "Notice of Rescission"),
    ("TDUS", "#7c3aed", "Trustee's Deed Upon Sale"),
]


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
    df = load_df()
    all_counties = sorted(df["County"].dropna().unique().tolist())
    all_stages = [s for s in df["Stage"].dropna().unique().tolist() if s.strip() and s in STAGE_COLORS]
    max_loan = int(df["Loan Amount"].max(skipna=True) or 5_000_000)
    min_date = df["Recording Date"].min()
    max_date = df["Recording Date"].max()

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
        dcc.Store(id="loan-defaults", data={"min": 0, "max": max_loan}),

        # Navbar
        dbc.Navbar(
            dbc.Container([
                dbc.NavbarBrand([
                    html.Span("🏚", className="me-2"),
                    "DistressedCA",
                ], href="/", className="fw-bold fs-5 text-danger"),
                dbc.Nav([
                    dbc.NavItem(dbc.NavLink("Map", href="/", active="exact")),
                    dbc.NavItem(dbc.NavLink("Trends", href="/trends")),
                    dbc.NavItem(dbc.NavLink("About", href="/about")),
                    dbc.NavItem(dbc.NavLink(
                        [html.I(className="bi bi-github me-1"), "GitHub"],
                        href="https://github.com/HighviewOne/DistressedCA",
                        target="_blank", external_link=True,
                    )),
                ], navbar=True, className="ms-auto"),
            ], fluid=True),
            color="dark", dark=True, sticky="top", className="mb-0 py-1",
        ),

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
    Input("main-map", "center"),
    Input("main-map", "zoom"),
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
                html.Div("total records", className="text-muted" ),
            ]), width=6),
            dbc.Col(html.Div([
                html.Span(f"{geocoded_count:,}", className="fw-bold fs-4"),
                html.Div("on map", className="text-muted"),
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
            data=records,
            columns=[{"name": c, "id": c} for c in cols],
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
    return all_stages, [], None, None, []


@callback(
    Output("loan-slider", "value"),
    Input("reset-filters-btn", "n_clicks"),
    State("loan-defaults", "data"),
    prevent_initial_call=True,
)
def reset_loan_slider(_, defaults):
    return [defaults["min"], defaults["max"]]
