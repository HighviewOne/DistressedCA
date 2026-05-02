import dash
from dash import html

dash.register_page(__name__, path="/about", title="About — DistressedCA", name="About")

COUNTIES = [
    "Los Angeles","San Diego","Riverside","San Bernardino","Orange",
    "Sacramento","Kern","Ventura","Fresno","Alameda",
    "Solano","San Joaquin","Sonoma","Shasta","Santa Cruz",
    "El Dorado","Contra Costa","San Benito","San Luis Obispo",
    "Yolo","Yuba","Santa Barbara","Imperial","Trinity",
    "San Mateo","Stanislaus","Del Norte","Siskiyou","Tulare",
    "San Francisco",
]

_FEATURES = [
    ("Stage-coded map",
     "Color-coded pins for NOD, NTS, NOR, and TDUS — instantly see where in the "
     "foreclosure lifecycle each property sits."),
    ("Equity scoring",
     "Loan-to-value and estimated market value flagged on every record. "
     "Filter for high-equity, low-LTV deals only."),
    ("Auction calendar",
     "Every upcoming trustee sale with date, time, location, minimum bid, "
     "and distance from the property."),
    ("Mailing-list export",
     "Cleaned owner names and property addresses, ready to drop into your "
     "direct-mail provider."),
]

_STAGES = [
    ("NOD", "#D97706", "Notice of Default",
     "The lender formally notifies the borrower and county that the loan is in default. "
     "The borrower has ~3 months to cure the default before a trustee sale can be scheduled."),
    ("NTS", "#DC2626", "Notice of Trustee's Sale",
     "The auction date is set. The property will be sold at a public trustee sale unless "
     "the borrower pays off the debt or negotiates a workout. Sale can be postponed multiple times."),
    ("NOR", "#059669", "Notice of Rescission",
     "The foreclosure was cancelled — the homeowner resolved the default "
     "(paid arrears, refinanced, or sold the property). A positive outcome."),
    ("TDUS", "#7C3AED", "Trustee's Deed Upon Sale",
     "The property sold at trustee sale. Ownership transferred to the winning bidder "
     "(often the lender). The former homeowner must vacate."),
]

_SOURCES = [
    ("County Recorder Portals",
     "Scraped daily from 30+ California counties via Tyler Technologies portals."),
    ("RETRAN.net",
     "Daily trust deed sale filings with enriched property and trustee data."),
    ("LA County Assessor",
     "Property characteristics (beds, baths, sqft, assessed value)."),
    ("Riverside County ArcGIS",
     "APN lookup and address enrichment via public REST API."),
]


def layout():
    return html.Div([
        html.Div(
            html.Div(
                [
                    # Hero eyebrow + headline
                    html.Div("About DistressedCA", className="dca-hero-eyebrow"),
                    html.H1(
                        ["Find distressed California homes ",
                         html.Span("weeks before they hit Zillow.",
                                   style={"color":"var(--accent)"})],
                        className="dca-hero-h1",
                        style={"maxWidth":"660px"},
                    ),
                    html.P(
                        "We track every Notice of Default, trustee's sale, rescission, and trustee deed "
                        "recorded across 30+ California counties — geocoded, scored for equity, and "
                        "surfaced on a single map. Built for investors, wholesalers, and realtors who "
                        "need lead-flow, not lead-noise.",
                        style={"fontSize":"16px","color":"var(--ink-2)","lineHeight":"1.65",
                               "marginTop":"16px","maxWidth":"660px"},
                    ),

                    # Feature grid
                    html.Div(
                        [
                            html.Div(
                                [html.H3(title, className="dca-serif",
                                         style={"fontSize":"22px","letterSpacing":"-0.01em",
                                                "margin":"0 0 4px","color":"var(--ink)"}),
                                 html.P(desc, style={"fontSize":"13.5px","color":"var(--ink-3)",
                                                     "lineHeight":"1.6","margin":"0"})],
                                className="dca-about-feature",
                            )
                            for title, desc in _FEATURES
                        ],
                        style={"display":"grid","gridTemplateColumns":"1fr 1fr",
                               "gap":"20px 28px","marginTop":"32px"},
                    ),

                    html.Hr(style={"borderColor":"var(--line)","margin":"32px 0"}),

                    # Foreclosure stages
                    html.H2("Foreclosure Stages", className="dca-serif",
                            style={"fontSize":"28px","letterSpacing":"-0.01em","margin":"0 0 20px",
                                   "color":"var(--ink)"}),
                    html.Div(
                        [
                            html.Div([
                                html.Div(
                                    [
                                        html.Span(style={"width":"10px","height":"10px",
                                                          "borderRadius":"50%","background":color,
                                                          "display":"inline-block","marginRight":"8px",
                                                          "flexShrink":"0","marginTop":"3px"}),
                                        html.Div([
                                            html.Span(
                                                [html.Strong(f"Stage — {short} "),
                                                 html.Span(f"({full})",
                                                           style={"color":"var(--ink-3)","fontWeight":"400"})],
                                                style={"fontSize":"14px","color":color,"fontWeight":"700"},
                                            ),
                                            html.P(desc, style={"fontSize":"12.5px","color":"var(--ink-3)",
                                                                  "lineHeight":"1.55","margin":"3px 0 0"}),
                                        ]),
                                    ],
                                    style={"display":"flex","alignItems":"flex-start"},
                                ),
                            ], className="dca-stage-explain")
                            for short, color, full, desc in _STAGES
                        ],
                        style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"8px 24px"},
                    ),

                    html.Hr(style={"borderColor":"var(--line)","margin":"32px 0"}),

                    # Data sources
                    html.H2("Data Sources", className="dca-serif",
                            style={"fontSize":"24px","letterSpacing":"-0.01em","margin":"0 0 16px",
                                   "color":"var(--ink)"}),
                    html.Div(
                        [
                            html.Div([
                                html.Div(name, style={"fontSize":"14px","fontWeight":"700",
                                                       "color":"var(--ink)","marginBottom":"2px"}),
                                html.Div(desc, style={"fontSize":"12.5px","color":"var(--ink-3)",
                                                       "lineHeight":"1.5"}),
                            ], style={"padding":"12px 0",
                                       "borderBottom":"1px solid var(--line)"})
                            for name, desc in _SOURCES
                        ],
                    ),

                    html.Hr(style={"borderColor":"var(--line)","margin":"32px 0"}),

                    # Counties
                    html.H2("Counties Covered", className="dca-serif",
                            style={"fontSize":"24px","letterSpacing":"-0.01em","margin":"0 0 12px",
                                   "color":"var(--ink)"}),
                    html.P(f"Currently tracking {len(COUNTIES)} counties across California.",
                           style={"fontSize":"13px","color":"var(--ink-3)","margin":"0 0 12px"}),
                    html.Div(
                        [
                            html.Span(c, style={
                                "display":"inline-block","padding":"4px 10px",
                                "borderRadius":"999px","border":"1px solid var(--line-2)",
                                "fontSize":"11.5px","color":"var(--ink-2)","margin":"3px",
                                "background":"var(--bg-elev)",
                            })
                            for c in sorted(COUNTIES)
                        ],
                    ),

                    # Disclaimer
                    html.Div(
                        [
                            html.Div("Disclaimer",
                                     style={"fontSize":"11px","fontWeight":"700",
                                            "textTransform":"uppercase","letterSpacing":"0.08em",
                                            "color":"var(--ink-3)","marginBottom":"6px"}),
                            html.P(
                                "This data is sourced from public county recorder records and is provided "
                                "for informational purposes only. It is not legal advice and may not reflect "
                                "the most current status of any property. Always verify information with the "
                                "appropriate county recorder or a licensed real estate professional before "
                                "making any decisions.",
                                style={"fontSize":"12px","color":"var(--ink-3)","lineHeight":"1.6","margin":"0"},
                            ),
                        ],
                        style={"background":"var(--bg-sunk)","borderRadius":"var(--r-md)",
                               "padding":"14px 16px","marginTop":"28px","marginBottom":"40px"},
                    ),
                ],
                className="dca-page-inner",
                style={"maxWidth":"760px"},
            ),
            className="dca-page-content",
        ),
    ])
