import os
import dash
from dash import html, dcc, clientside_callback, Output, Input, State
import dash_bootstrap_components as dbc

# ── Google Fonts ────────────────────────────────────────────────────────────────
_GFONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Instrument+Serif:ital@0;1&"
    "family=Geist:wght@300;400;500;600;700&"
    "family=JetBrains+Mono:wght@400;500&"
    "display=swap"
)
_GFONTS_PRECONNECT = "https://fonts.gstatic.com"

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        dbc.icons.BOOTSTRAP,
        {"rel": "preconnect", "href": "https://fonts.googleapis.com"},
        {"rel": "preconnect", "href": _GFONTS_PRECONNECT, "crossorigin": ""},
        _GFONTS,
    ],
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Interactive map of distressed properties in California — NODs, trustee sales, and foreclosure activity tracked across 30+ counties."},
    ],
    suppress_callback_exceptions=True,
)

app.title = "DistressedCA"
server = app.server  # expose for gunicorn

# ── Logo SVG (from ui.jsx) ───────────────────────────────────────────────────────
# dcc.Markdown with dangerously_allow_html renders inline SVG that inherits CSS vars.
# html.Svg is not available in Dash 4.x; this is the clean workaround.
_LOGO_SVG = """<svg width="28" height="28" viewBox="0 0 32 32" fill="none"
  aria-hidden="true" style="flex-shrink:0;display:block">
  <path d="M3 16 L16 5 L29 16 L29 27 Q29 28 28 28 L4 28 Q3 28 3 27 Z"
    stroke="var(--ink)" stroke-width="1.8" stroke-linejoin="round" fill="none"/>
  <path d="M16 13.5 L21 22 L11 22 Z" fill="var(--accent)"/>
  <rect x="15.4" y="15.5" width="1.2" height="3.2" rx="0.4" fill="var(--bg-elev)"/>
  <rect x="15.4" y="19.4" width="1.2" height="1.2" rx="0.6" fill="var(--bg-elev)"/>
</svg>"""


def _logo():
    return dcc.Markdown(_LOGO_SVG, dangerously_allow_html=True,
                        className="dca-logo-svg")


def _header():
    nav_links = [
        ("Map",      "/"),
        ("Auctions", "/auctions"),
        ("Trends",   "/trends"),
        ("About",    "/about"),
    ]
    return html.Header(
        [
            # Wordmark
            html.A(
                [
                    _logo(),
                    html.Div(
                        [
                            html.Div(
                                [html.Span("Distressed"), html.Span("CA", className="dca-ca")],
                                className="dca-brand-name",
                            ),
                            html.Div("California Foreclosure Intelligence", className="dca-tagline"),
                        ],
                        style={"display": "flex", "flexDirection": "column", "lineHeight": "1"},
                    ),
                ],
                href="/", className="dca-wordmark",
                style={"textDecoration": "none"},
            ),

            # Nav
            html.Nav(
                [
                    html.A(label, href=href, className="dca-nav-link", id=f"nav-{href.strip('/') or 'map'}")
                    for label, href in nav_links
                ],
                className="dca-nav",
            ),

            # Search
            html.Div(
                [
                    html.Span(
                        html.I(className="bi bi-search", style={"fontSize": "13px"}),
                        className="dca-search-icon",
                    ),
                    dcc.Input(
                        id="global-search",
                        type="text",
                        placeholder="Search address, city, ZIP, or county",
                        debounce=True,
                        className="dca-search-input",
                        value="",
                    ),
                ],
                className="dca-search-wrap",
            ),

            # Theme toggle
            html.Button(
                [
                    html.I(className="bi bi-moon-fill theme-sun", style={"fontSize": "14px"}),
                    html.I(className="bi bi-sun-fill theme-moon", style={"fontSize": "14px"}),
                ],
                id="theme-toggle",
                className="dca-icon-btn",
                title="Toggle dark mode",
                n_clicks=0,
            ),

            # Theme store
            dcc.Store(id="theme-store", data="light", storage_type="local"),
        ],
        id="dca-header",
    )


app.layout = html.Div(
    [
        _header(),
        dash.page_container,
    ],
    id="dca-app-root",
)


# ── Theme toggle (clientside) ─────────────────────────────────────────────────
clientside_callback(
    """function(n_clicks, current) {
        var t = (n_clicks > 0)
            ? (current === 'dark' ? 'light' : 'dark')
            : (current || 'light');
        document.documentElement.setAttribute('data-theme', t);
        return t;
    }""",
    Output("theme-store", "data"),
    Input("theme-toggle",  "n_clicks"),
    State("theme-store",   "data"),
)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=port)
