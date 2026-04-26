import dash
from dash import html
import dash_bootstrap_components as dbc

dash.register_page(__name__, path="/about", title="About — DistressedCA", name="About")

TECH_STACK = [
    ("Python / Dash", "Interactive web framework"),
    ("Dash Leaflet", "Interactive map (OpenStreetMap tiles)"),
    ("Dash Bootstrap Components", "UI layout and styling"),
    ("Pandas", "Data processing and filtering"),
    ("US Census Geocoder", "Address geocoding (free)"),
]

DATA_SOURCES = [
    ("County Recorder Portals", "Scraped daily from 30 California counties via Tyler Technologies portals"),
    ("RETRAN.net", "Daily trust deed sale filings with enriched property and trustee data"),
    ("LA County Assessor", "Property characteristics (beds, baths, sqft, assessed value)"),
]

COUNTIES = [
    "Los Angeles", "San Diego", "Riverside", "San Bernardino", "Orange",
    "Sacramento", "Kern", "Ventura", "Fresno", "Alameda",
    "Solano", "San Joaquin", "Sonoma", "Shasta", "Santa Cruz",
    "El Dorado", "Contra Costa", "San Benito", "San Luis Obispo",
    "Yolo", "Yuba", "Santa Barbara", "Imperial", "Trinity",
    "San Mateo", "Stanislaus", "Del Norte", "Siskiyou", "Tulare",
    "San Francisco",
]


def layout():
    return dbc.Container([
        # Navbar
        dbc.Navbar(
            dbc.Container([
                dbc.NavbarBrand([
                    html.Span("🏚", className="me-2"),
                    "DistressedCA",
                ], href="/", className="fw-bold fs-5 text-danger"),
                dbc.Nav([
                    dbc.NavItem(dbc.NavLink("Map", href="/")),
                    dbc.NavItem(dbc.NavLink("Trends", href="/trends")),
                    dbc.NavItem(dbc.NavLink("About", href="/about", active=True)),
                    dbc.NavItem(dbc.NavLink(
                        [html.I(className="bi bi-github me-1"), "GitHub"],
                        href="https://github.com/HighviewOne/DistressedCA",
                        target="_blank", external_link=True,
                    )),
                ], navbar=True, className="ms-auto"),
            ], fluid=True),
            color="dark", dark=True, sticky="top", className="mb-4 py-1",
        ),

        dbc.Row([
            dbc.Col([
                # Hero
                dbc.Card([
                    dbc.CardBody([
                        html.H2("DistressedCA", className="fw-bold text-danger"),
                        html.P(
                            "An interactive map of distressed properties across California — "
                            "tracking Notice of Default (NOD), Notice of Trustee's Sale (NTS), "
                            "Rescissions, and completed Trustee Deed sales in near real-time.",
                            className="lead",
                        ),
                        html.P(
                            "When a homeowner falls behind on mortgage payments, the lender files a "
                            "Notice of Default with the county recorder. This begins a public foreclosure "
                            "timeline that can take 3–12 months. This tool tracks every step of that "
                            "process across 30 California counties.",
                        ),
                        dbc.ButtonGroup([
                            dbc.Button("View the Map", href="/", color="danger", className="me-2"),
                            dbc.Button(
                                [html.I(className="bi bi-github me-1"), "View on GitHub"],
                                href="https://github.com/HighviewOne/DistressedCA",
                                color="dark", outline=True,
                                target="_blank", external_link=True,
                            ),
                        ]),
                    ])
                ], className="mb-4 border-danger border-top border-3"),

                # Foreclosure stages explained
                dbc.Card([
                    dbc.CardHeader(html.H5("Foreclosure Stages", className="mb-0 fw-bold")),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.Span("●", style={"color": "#f59e0b", "fontSize": "1.3rem", "marginRight": "8px"}),
                                    html.Strong("Stage 1 — NOD (Notice of Default)"),
                                ], className="mb-1"),
                                html.P(
                                    "The lender formally notifies the borrower and county that the loan is "
                                    "in default. The borrower has ~3 months to cure the default before a "
                                    "trustee sale can be scheduled.",
                                    className="small ms-4 text-muted",
                                ),
                            ], lg=6),
                            dbc.Col([
                                html.Div([
                                    html.Span("●", style={"color": "#ef4444", "fontSize": "1.3rem", "marginRight": "8px"}),
                                    html.Strong("Stage 2 — NTS (Notice of Trustee's Sale)"),
                                ], className="mb-1"),
                                html.P(
                                    "The auction date is set. The property will be sold at a public trustee "
                                    "sale unless the borrower pays off the debt or negotiates a workout. "
                                    "Sale can be postponed multiple times.",
                                    className="small ms-4 text-muted",
                                ),
                            ], lg=6),
                            dbc.Col([
                                html.Div([
                                    html.Span("●", style={"color": "#22c55e", "fontSize": "1.3rem", "marginRight": "8px"}),
                                    html.Strong("Stage 3 — NOR (Notice of Rescission)"),
                                ], className="mb-1"),
                                html.P(
                                    "The foreclosure was cancelled — the homeowner resolved the default "
                                    "(paid arrears, refinanced, or sold the property). A positive outcome.",
                                    className="small ms-4 text-muted",
                                ),
                            ], lg=6),
                            dbc.Col([
                                html.Div([
                                    html.Span("●", style={"color": "#7c3aed", "fontSize": "1.3rem", "marginRight": "8px"}),
                                    html.Strong("Stage 4 — TDUS (Trustee's Deed Upon Sale)"),
                                ], className="mb-1"),
                                html.P(
                                    "The property sold at trustee sale. Ownership transferred to the winning "
                                    "bidder (often the lender). The former homeowner must vacate.",
                                    className="small ms-4 text-muted",
                                ),
                            ], lg=6),
                        ]),
                    ]),
                ], className="mb-4"),

                dbc.Row([
                    # Data sources
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader(html.H5("Data Sources", className="mb-0 fw-bold")),
                            dbc.CardBody([
                                html.Ul([
                                    html.Li([
                                        html.Strong(name),
                                        html.Br(),
                                        html.Span(desc, className="small text-muted"),
                                    ], className="mb-2")
                                    for name, desc in DATA_SOURCES
                                ], className="ps-3"),
                            ]),
                        ], className="h-100"),
                    ], lg=6),

                    # Tech stack
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader(html.H5("Tech Stack", className="mb-0 fw-bold")),
                            dbc.CardBody([
                                dbc.Table([
                                    html.Tbody([
                                        html.Tr([
                                            html.Td(html.Strong(tool), className="pe-3"),
                                            html.Td(desc, className="text-muted small"),
                                        ])
                                        for tool, desc in TECH_STACK
                                    ])
                                ], borderless=True, size="sm"),
                            ]),
                        ], className="h-100"),
                    ], lg=6),
                ], className="mb-4"),

                # Counties covered
                dbc.Card([
                    dbc.CardHeader(html.H5("California Counties Covered", className="mb-0 fw-bold")),
                    dbc.CardBody([
                        html.P(
                            f"Currently tracking {len(COUNTIES)} counties across California:",
                            className="small text-muted mb-2",
                        ),
                        html.Div([
                            dbc.Badge(c, color="secondary", className="me-1 mb-1")
                            for c in sorted(COUNTIES)
                        ]),
                    ]),
                ], className="mb-4"),

                # Disclaimer
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Disclaimer", className="fw-bold text-muted"),
                        html.P(
                            "This data is sourced from public county recorder records and is provided for "
                            "informational purposes only. It is not legal advice and may not reflect the "
                            "most current status of any property. Always verify information with the "
                            "appropriate county recorder or a licensed real estate professional before "
                            "making any decisions.",
                            className="small text-muted mb-0",
                        ),
                    ]),
                ], color="light"),
            ], lg={"size": 10, "offset": 1}),
        ]),
    ], fluid=True, className="pb-5")
