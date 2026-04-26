import os
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        dbc.icons.BOOTSTRAP,
    ],
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Interactive map of distressed properties in California — NODs, trustee sales, and foreclosure activity tracked across 30+ counties."},
    ],
    suppress_callback_exceptions=True,
)

app.title = "DistressedCA"
server = app.server  # expose for gunicorn

app.layout = dash.page_container


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=port)
