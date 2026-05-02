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

# ── Logo mark ───────────────────────────────────────────────────────────────────
def _logo(size=28):
    """House icon with warning triangle — using Bootstrap Icons."""
    return html.Span(
        [
            html.I(
                className="bi bi-house-fill",
                style={"fontSize": f"{size}px", "color": "var(--ink)",
                       "lineHeight": "1", "display": "block"},
            ),
            html.I(
                className="bi bi-exclamation-triangle-fill",
                style={
                    "fontSize": f"{size * 0.42:.0f}px",
                    "color": "var(--accent)",
                    "position": "absolute",
                    "bottom": "-2px",
                    "right": "-3px",
                    "lineHeight": "1",
                },
            ),
        ],
        style={
            "position": "relative",
            "display": "inline-flex",
            "alignItems": "center",
            "flexShrink": "0",
            "width": f"{size + 4}px",
            "height": f"{size}px",
        },
    )


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
                    _logo(28),
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
