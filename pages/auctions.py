import dash
from dash import html, dcc, callback, Output, Input
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

_STAGE_COLORS_NEW = {
    "NOD": ("#D97706", "#FEF3C7"),
    "NTS": ("#DC2626", "#FEE2E2"),
    "NOR": ("#059669", "#D1FAE5"),
    "TDUS": ("#7C3AED", "#EDE9FE"),
}


def _money_short(v) -> str:
    if v is None:
        return "—"
    try:
        n = float(str(v).replace("$", "").replace(",", ""))
        if n >= 1e6:
            return f"${n/1e6:.2f}M".rstrip("0").rstrip(".")
        if n >= 1e3:
            return f"${round(n/1e3)}K"
        return f"${n:.0f}"
    except (ValueError, TypeError):
        return str(v)


def _stage_pill(short: str) -> html.Span:
    color, bg = _STAGE_COLORS_NEW.get(short, ("#78716C", "#F1ECE5"))
    return html.Span(
        [html.Span(style={"width": "5px", "height": "5px", "borderRadius": "50%",
                          "background": color, "display": "inline-block"}),
         f" {short}"],
        style={"background": bg, "color": color, "padding": "2px 7px",
               "borderRadius": "999px", "fontSize": "10px", "fontWeight": "600",
               "display": "inline-flex", "alignItems": "center", "gap": "4px"},
    )


def _photo_thumb(idx: int) -> html.Div:
    palettes = [("#E8DCC8","#C9B79A"), ("#D4C4B0","#A89878"), ("#C8B89E","#8E7B5C")]
    p   = palettes[idx % len(palettes)]
    sky = ["#B8C5D6","#D8DCE0","#C4CFD9"][idx % 3]
    bg  = f"linear-gradient(180deg, {sky} 0%, {sky} 44%, {p[0]} 44.5%, {p[1]} 100%)"
    return html.Div(
        style={"width":"100%","height":"100%","background":bg,"borderRadius":"var(--r-sm)"},
    )


def layout():
    df = load_df()
    all_counties = sorted(c for c in df["County"].dropna().unique().tolist() if str(c).strip())

    return html.Div([
        dcc.Download(id="auctions-download"),
        html.Div(
            html.Div(
                [
                    # Hero
                    html.Div("Auctions", className="dca-hero-eyebrow"),
                    html.H1("Upcoming trustee sales", className="dca-hero-h1"),
                    html.P(
                        "All scheduled auction events from active filings. "
                        "Sales typically happen at county courthouses; verify times with the trustee before bidding.",
                        className="dca-hero-lead",
                    ),

                    # Filters row
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="auctions-county",
                                options=[{"label": c, "value": c} for c in all_counties],
                                value=[],
                                multi=True,
                                placeholder="All counties…",
                                style={"minWidth": "220px", "fontSize": "13px"},
                            ),
                            html.Button(
                                [html.I(className="bi bi-download me-2"), "Export CSV"],
                                id="auctions-export-btn",
                                className="dca-btn-accent",
                                n_clicks=0,
                            ),
                        ],
                        style={"display": "flex", "gap": "12px", "alignItems": "center",
                               "marginTop": "18px", "flexWrap": "wrap"},
                    ),

                    # Stats grid
                    html.Div(id="auctions-stats"),

                    # Auction list
                    html.Div(id="auctions-list"),
                ],
                className="dca-page-inner",
            ),
            className="dca-page-content",
        ),
    ])


def _build_auction_list(df_filtered: pd.DataFrame) -> list:
    today = pd.Timestamp("today").normalize()
    upcoming = df_filtered[
        df_filtered["Sale Date"].notna() & (df_filtered["Sale Date"] >= today)
    ].copy().sort_values("Sale Date")

    if upcoming.empty:
        return [html.P("No upcoming auctions match the current filters.",
                       style={"color": "var(--ink-3)", "padding": "24px 0"})]

    # Group by date
    by_date = {}
    for _, row in upcoming.iterrows():
        sd = row["Sale Date"]
        key = sd.strftime("%Y-%m-%d")
        by_date.setdefault(key, []).append(row)

    sections = []
    for i, (date_str, rows) in enumerate(sorted(by_date.items())):
        days_until = (pd.to_datetime(date_str) - today).days
        badge_bg = "var(--nts)" if days_until <= 7 else "var(--ink-2)"
        date_label = pd.to_datetime(date_str).strftime("%B %-d, %Y")

        cards = []
        for j, row in enumerate(rows):
            short = STAGE_SHORT.get(str(row.get("Stage","")),"")
            address = str(row.get("Property Address","")).strip()
            city    = str(row.get("City","")).strip()
            county  = str(row.get("County","")).strip()
            min_bid = row.get("Min Bid")
            equity  = row.get("Equity %")
            emv_raw = row.get("EMV") or row.get("Assessed Total($)")
            sale_time = str(row.get("Sale Time","") or "").strip()

            try:
                emv = float(str(emv_raw or "").replace("$","").replace(",",""))
            except (ValueError, TypeError):
                emv = None

            cards.append(html.Div(
                [
                    html.Div(
                        _photo_thumb(i * 10 + j),
                        className="dca-auction-thumb",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.Span(address, style={"fontSize":"13px","fontWeight":"600",
                                                           "flex":"1","overflow":"hidden",
                                                           "textOverflow":"ellipsis",
                                                           "whiteSpace":"nowrap"}),
                                 html.Span(sale_time, style={"fontSize":"11.5px","color":"var(--ink-3)",
                                                              "whiteSpace":"nowrap",
                                                              "marginLeft":"8px"}) if sale_time else None],
                                style={"display":"flex","alignItems":"baseline","gap":"4px"},
                            ),
                            html.Div(
                                [_stage_pill(short),
                                 html.Span(f"{city} · {county}",
                                           style={"fontSize":"11.5px","color":"var(--ink-3)","marginLeft":"6px"})],
                                style={"display":"flex","alignItems":"center","gap":"4px","marginTop":"4px"},
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        ["min bid ",
                                         html.Strong(_money_short(min_bid),
                                                     style={"color":"var(--ink)"})],
                                        style={"fontSize":"12.5px","color":"var(--ink-3)"},
                                    ) if min_bid else None,
                                    html.Span(
                                        f"{equity:.0f}% eq · {_money_short(emv)}",
                                        style={"fontSize":"11.5px","color":"var(--good)",
                                               "fontWeight":"600"},
                                    ) if equity else None,
                                ],
                                style={"display":"flex","justifyContent":"space-between",
                                       "marginTop":"6px","alignItems":"center"},
                            ),
                        ],
                        style={"flex":"1","minWidth":"0"},
                    ),
                ],
                className="dca-auction-card",
            ))

        sections.append(html.Div(
            [
                html.Div(
                    [
                        html.Span(date_label, className="dca-date-h2"),
                        html.Span(f"in {days_until}d",
                                  className="dca-days-badge",
                                  style={"background": badge_bg}),
                        html.Span(
                            f"{len(rows)} auction{'s' if len(rows) != 1 else ''}",
                            style={"color":"var(--ink-3)","fontSize":"12px"},
                        ),
                    ],
                    className="dca-date-heading",
                ),
                html.Div(cards, className="dca-auction-cards-grid"),
            ],
            className="dca-date-section",
        ))

    return sections


@callback(
    Output("auctions-stats", "children"),
    Output("auctions-list",  "children"),
    Input("auctions-county", "value"),
)
def update_auctions(counties):
    df = load_df()
    today = pd.Timestamp("today").normalize()

    upcoming = df[df["Sale Date"].notna() & (df["Sale Date"] >= today)].copy()
    if counties:
        upcoming = upcoming[upcoming["County"].isin(counties)]

    this_week = (upcoming["Sale Date"] <= today + pd.Timedelta(days=7)).sum()
    total_min = upcoming["Min Bid"].dropna().sum()
    high_eq   = int(upcoming.get("High Equity", pd.Series(dtype=bool)).astype(bool).sum()
                    if "High Equity" in upcoming.columns else 0)

    stats = html.Div(
        [
            html.Div(
                [html.Div(f"{len(upcoming):,}", className="dca-stat-card-num dca-serif",
                          style={"color":"var(--ink)"}),
                 html.Div("Total upcoming", className="dca-stat-card-label")],
                className="dca-stat-card",
            ),
            html.Div(
                [html.Div(f"{this_week:,}", className="dca-stat-card-num dca-serif",
                          style={"color":"var(--nts)"}),
                 html.Div("This week", className="dca-stat-card-label")],
                className="dca-stat-card",
            ),
            html.Div(
                [html.Div(_money_short(total_min), className="dca-stat-card-num dca-serif",
                          style={"color":"var(--accent)"}),
                 html.Div("Total min bids", className="dca-stat-card-label")],
                className="dca-stat-card",
            ),
            html.Div(
                [html.Div(f"{high_eq:,}", className="dca-stat-card-num dca-serif",
                          style={"color":"var(--good)"}),
                 html.Div("High-equity", className="dca-stat-card-label")],
                className="dca-stat-card",
            ),
        ],
        className="dca-stat-grid",
    )

    auction_list = _build_auction_list(upcoming)
    return stats, auction_list


@callback(
    Output("auctions-download", "data"),
    Input("auctions-export-btn", "n_clicks"),
    Input("auctions-county",     "value"),
    prevent_initial_call=True,
)
def export_auctions(n_clicks, counties):
    from dash.exceptions import PreventUpdate
    from dash import ctx
    if ctx.triggered_id != "auctions-export-btn" or not n_clicks:
        raise PreventUpdate
    df = load_df()
    today = pd.Timestamp("today").normalize()
    upcoming = df[df["Sale Date"].notna() & (df["Sale Date"] >= today)].copy()
    if counties:
        upcoming = upcoming[upcoming["County"].isin(counties)]
    upcoming = upcoming.sort_values("Sale Date")

    export_cols = ["Sale Date", "Sale Time", "Property Address", "City", "County",
                   "Min Bid", "EMV", "Equity %", "Loan Amount", "APN",
                   "Auction Location", "Stage", "Borrower Name"]
    avail = [c for c in export_cols if c in upcoming.columns]
    out = upcoming[avail].copy()
    if "Sale Date" in out.columns:
        out["Sale Date"] = out["Sale Date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
        )
    return dcc.send_data_frame(out.to_csv, f"auctions_{date.today()}.csv", index=False)
