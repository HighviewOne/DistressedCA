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
from datetime import date, datetime, timedelta
import os
from urllib.parse import quote as _quote

dash.register_page(
    __name__,
    path="/",
    title="DistressedCA — California Distressed Properties",
    name="Map",
)

# ── Stage display config ───────────────────────────────────────────────────────
# New design colors (match design tokens)
_STAGE_CFG = {
    "NOD  — Notice of Default": {
        "short": "NOD", "color": "#D97706", "bg": "#FEF3C7",
        "full": "Notice of Default", "num": 1,
    },
    "NTS  — Notice of Trustee's Sale": {
        "short": "NTS", "color": "#DC2626", "bg": "#FEE2E2",
        "full": "Notice of Trustee's Sale", "num": 2,
    },
    "NOR  — Notice of Rescission": {
        "short": "NOR", "color": "#059669", "bg": "#D1FAE5",
        "full": "Notice of Rescission", "num": 3,
    },
    "TDUS — Trustee's Deed Upon Sale": {
        "short": "TDUS", "color": "#7C3AED", "bg": "#EDE9FE",
        "full": "Trustee's Deed Upon Sale", "num": 4,
    },
}
_STAGE_COLOR_MAP = {k: v["color"] for k, v in _STAGE_CFG.items()}

# ── Leaflet JS functions ───────────────────────────────────────────────────────
point_to_layer = assign("""
function(feature, latlng, context) {
    var stageColors = {1: '#D97706', 2: '#DC2626', 3: '#059669', 4: '#7C3AED'};
    var color = stageColors[feature.properties.stage_num] || '#78716C';
    var shortLabels = {1: 'NOD', 2: 'NTS', 3: 'NOR', 4: 'TDUS'};
    var label = shortLabels[feature.properties.stage_num] || '';
    var size = 28;
    var icon = L.divIcon({
        className: '',
        html: '<div style="width:' + size + 'px;height:' + size + 'px;' +
              'border-radius:50% 50% 50% 0;transform:rotate(-45deg);' +
              'background:' + color + ';border:2px solid rgba(255,255,255,0.95);' +
              'box-shadow:0 2px 6px rgba(0,0,0,0.28);' +
              'display:flex;align-items:center;justify-content:center;">' +
              '<span style="transform:rotate(45deg);font-size:6px;font-weight:700;' +
              'color:#fff;font-family:sans-serif;letter-spacing:-0.5px">' + label + '</span>' +
              '</div>',
        iconSize: [size, size],
        iconAnchor: [size/2, size],
        popupAnchor: [0, -size],
    });
    return L.marker(latlng, {icon: icon});
}
""")

on_each_feature = assign("""
function(feature, layer, context) {
    var p = feature.properties;
    var stageColors = {1: '#D97706', 2: '#DC2626', 3: '#059669', 4: '#7C3AED'};
    var color = stageColors[p.stage_num] || '#78716C';
    var tip = '<div style="font-family:system-ui;min-width:160px">';
    tip += '<div style="font-weight:600;font-size:13px;margin-bottom:3px">' + (p.address || 'Unknown') + '</div>';
    tip += '<span style="color:' + color + ';font-weight:700;font-size:11px">' + (p.stage_short || '') + '</span>';
    if (p.county) tip += '<span style="color:#78716C;font-size:11px"> &middot; ' + p.county + '</span>';
    if (p.emv) tip += '<div style="font-size:11px;color:#44403C;margin-top:2px">EMV: ' + p.emv + '</div>';
    if (p.timeline && p.timeline.length > 1)
        tip += '<div style="font-size:10px;color:#A8A29E;margin-top:2px">' + p.timeline.length + ' filings</div>';
    tip += '</div>';
    layer.bindTooltip(tip, {sticky: true, direction: 'top', offset: [0, -6],
        className: 'dca-map-tooltip'});
}
""")


# ── Helpers ────────────────────────────────────────────────────────────────────
_BUILD = "v2026-05-02c"  # visible in stat bar — bump to confirm Render deployed latest code

def _last_updated() -> str:
    try:
        from data.loader import PARQUET_SNAPSHOT
        mtime = os.path.getmtime(PARQUET_SNAPSHOT)
        age = datetime.now() - datetime.fromtimestamp(mtime)
        hours = int(age.total_seconds() // 3600)
        if hours < 1:
            return f"< 1h · {_BUILD}"
        if hours < 24:
            return f"{hours}h ago · {_BUILD}"
        return f"{hours // 24}d ago · {_BUILD}"
    except Exception:
        return _BUILD


def _money(v) -> str:
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


def _stage_pill(short: str, color: str, bg: str) -> html.Span:
    return html.Span(
        [html.Span(style={"width": "6px", "height": "6px", "borderRadius": "50%",
                          "background": color, "display": "inline-block"}),
         f" {short}"],
        style={
            "background": bg, "color": color,
            "padding": "2px 8px", "borderRadius": "999px",
            "fontSize": "10.5px", "fontWeight": "600",
            "letterSpacing": "0.03em", "display": "inline-flex",
            "alignItems": "center", "gap": "4px", "whiteSpace": "nowrap",
        }
    )


def _flag_badge(kind: str) -> html.Span | None:
    MAP = {
        "high_equity": ("High Equity", "var(--good)",   "rgba(21,128,61,0.10)"),
        "low_ltv":     ("Low LTV",     "#1D4ED8",       "rgba(29,78,216,0.10)"),
        "hard_money":  ("Hard Money",  "#A16207",       "rgba(161,98,7,0.10)"),
        "corporate":   ("Corp Owned",  "var(--ink-3)",  "rgba(120,113,108,0.12)"),
    }
    if kind not in MAP:
        return None
    label, color, bg = MAP[kind]
    return html.Span(
        label,
        className="dca-flag-badge",
        style={"color": color, "background": bg},
    )


def _prop_photo_svg(idx: int, stage_num: int) -> html.Div:
    """CSS gradient photo placeholder — no SVG needed."""
    palettes = [
        ("#E8DCC8", "#C9B79A"), ("#D4C4B0", "#A89878"), ("#C8B89E", "#8E7B5C"),
        ("#E2D4BC", "#B8A584"), ("#D8C8AE", "#9C8862"), ("#CCBCA0", "#857353"),
    ]
    sky_list = ["#B8C5D6", "#D8DCE0", "#C4CFD9", "#E0E2E5"]
    p   = palettes[(idx - 1) % len(palettes)]
    sky = sky_list[idx % 4]
    # Split gradient: sky (top 42%) | earth tone (bottom)
    bg = (f"linear-gradient(180deg, {sky} 0%, {sky} 42%, {p[0]} 42.5%, {p[1]} 100%)")
    stage_icons = {1: "bi bi-house", 2: "bi bi-hammer", 3: "bi bi-check-circle",
                   4: "bi bi-building"}
    icon_cls = stage_icons.get(stage_num, "bi bi-house")
    return html.Div(
        html.I(className=icon_cls, style={"fontSize":"28px","opacity":"0.25",
                                           "color":"#fff","position":"absolute",
                                           "bottom":"12px","right":"12px"}),
        style={
            "width": "100%", "height": "100%",
            "background": bg,
            "position": "relative",
        },
    )


# ── Property card (list rail) ─────────────────────────────────────────────────
def _prop_card(p: dict, idx: int, selected: bool = False) -> html.Div:
    cfg = None
    for k, v in _STAGE_CFG.items():
        if v["short"] == p.get("stage_short", ""):
            cfg = v
            break
    if cfg is None:
        cfg = {"short": p.get("stage_short","?"), "color":"#78716C", "bg":"#F1ECE5",
               "full": "", "num": 0}

    stage_num = cfg["num"]
    color = cfg["color"]
    bg    = cfg["bg"]

    emv_raw  = p.get("emv", "")
    sale_date = p.get("sale_date", "")
    min_bid   = p.get("min_bid", "")
    equity    = p.get("equity_pct", "")
    loan_amt  = p.get("loan_amount", "")
    rec_date  = p.get("recording_date", "")
    beds = p.get("beds", ""); baths = p.get("baths", ""); sqft = p.get("sqft", "")
    city = p.get("city", ""); county = p.get("county", ""); zip_ = p.get("zip", "")

    # Days until auction
    days_until = None
    if sale_date:
        try:
            sd = pd.to_datetime(sale_date)
            days_until = (sd - pd.Timestamp.now().normalize()).days
        except Exception:
            pass

    flags = []
    if p.get("high_equity"): flags.append("high_equity")
    if p.get("low_ltv"):     flags.append("low_ltv")
    if p.get("hard_money") == "Yes": flags.append("hard_money")
    if p.get("corporate")  == "Yes": flags.append("corporate")

    specs_parts = [x for x in [
        f"{beds} bd" if beds else "",
        f"{baths} ba" if baths else "",
        f"{sqft} sqft" if sqft else "",
    ] if x]

    card_id = {"type": "prop-card", "index": p.get("apn", str(idx))}

    info_block = None
    if sale_date and days_until is not None and days_until >= 0:
        sale_str = sale_date[:10] if len(sale_date) >= 10 else sale_date
        info_block = html.Div(
            [html.Span("Auction ", style={"fontWeight": "700", "color": "var(--nts)"}),
             html.Span(f"{sale_str}"),
             (html.Span(f" · min bid {_money(min_bid)}", style={"fontWeight": "600"})
              if min_bid else None)],
            className="dca-card-info auction",
        )
    elif rec_date or loan_amt:
        rd = rec_date[:10] if rec_date and len(rec_date) >= 10 else rec_date
        info_block = html.Div(
            [html.Span("Recorded ", style={"fontWeight": "700", "color": "var(--ink-2)"}),
             html.Span(rd or "", style={"color": "var(--ink-3)"}),
             (html.Span(f" · loan {_money(loan_amt)}", style={"color": "var(--ink-3)"})
              if loan_amt else None)],
            className="dca-card-info recorded",
        )

    return html.Div(
        id=card_id,
        className=f"dca-prop-card{'  selected' if selected else ''}",
        style={"cursor": "pointer"},
        children=[
            # Photo
            html.Div(
                [
                    _prop_photo_svg(idx + 1, stage_num),
                    _stage_pill(cfg["short"], color, bg),
                    (html.Div(
                        f"Auction in {days_until}d",
                        className="dca-card-auction-badge",
                    ) if days_until is not None and 0 <= days_until <= 14 else None),
                ],
                className="dca-card-photo",
            ),
            # Body
            html.Div(
                [
                    # Price + equity
                    html.Div(
                        [
                            html.Div(
                                [html.Span(_money(emv_raw), className="dca-card-emv"),
                                 html.Span("est. value", className="dca-card-emv-label")],
                                style={"display": "flex", "alignItems": "baseline", "gap": "4px"},
                            ),
                            (html.Span(f"{equity}% eq", className="dca-equity-pill")
                             if equity else None),
                        ],
                        className="dca-card-price",
                    ),
                    html.Div(" · ".join(specs_parts), className="dca-card-specs") if specs_parts else None,
                    html.Div(p.get("address",""), className="dca-card-address"),
                    html.Div(
                        f"{city}, CA {zip_} · {county} County",
                        className="dca-card-location",
                    ) if city or county else None,
                    info_block,
                    html.Div(
                        [b for b in [_flag_badge(f) for f in flags] if b],
                        className="dca-card-flags",
                    ) if flags else None,
                ],
                className="dca-card-body",
            ),
        ],
    )


# ── Property drawer ────────────────────────────────────────────────────────────
def _drawer_overview(p: dict) -> html.Div:
    beds = p.get("beds",""); baths = p.get("baths","")
    sqft = p.get("sqft",""); yr = p.get("year_built","")
    specs = [("Beds", beds), ("Baths", baths), ("Sqft", sqft), ("Built", yr)]

    emv  = p.get("emv",""); ltv = p.get("ltv",""); equity = p.get("equity_pct","")
    loan = p.get("loan_amount",""); default_amt = p.get("default_amount","")
    assessed = p.get("assessed_total",""); borrower = p.get("borrower","")
    rec_date = p.get("recording_date","")[:10] if p.get("recording_date","") else "—"

    stage_full = "—"
    for k, v in _STAGE_CFG.items():
        if v["short"] == p.get("stage_short",""):
            stage_full = v["full"]; break

    return html.Div([
        # Specs grid
        html.Div([
            html.Div(
                [html.Div(val or "—", className="dca-spec-val dca-serif"),
                 html.Div(lbl, className="dca-spec-label")],
                className="dca-spec-cell",
            ) for lbl, val in specs
        ], className="dca-specs-grid dca-section"),

        # Filing
        html.Div([
            html.Div("Filing", className="dca-section-title"),
            html.Div([html.Span("Recorded", className="dca-data-label"),
                      html.Span(rec_date, className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("Stage", className="dca-data-label"),
                      html.Span(stage_full, className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("County", className="dca-data-label"),
                      html.Span(p.get("county","—"), className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("Borrower", className="dca-data-label"),
                      html.Span(borrower or "—", className="dca-data-value")], className="dca-data-row"),
        ], className="dca-section"),

        # Loan
        html.Div([
            html.Div("Loan", className="dca-section-title"),
            html.Div([html.Span("Loan amount", className="dca-data-label"),
                      html.Span(loan or "—", className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("Est. market value", className="dca-data-label"),
                      html.Span(emv or "—", className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("LTV", className="dca-data-label"),
                      html.Span(f"{ltv}%" if ltv else "—",
                                className="dca-data-value",
                                style={"color": "var(--good)" if ltv and float(str(ltv).rstrip("%") or 100) < 50 else "var(--ink)"})],
                     className="dca-data-row"),
            html.Div([html.Span("Equity", className="dca-data-label"),
                      html.Span(f"{equity}%" if equity else "—",
                                className="dca-data-value",
                                style={"color": "var(--good)" if equity and float(str(equity).rstrip("%") or 0) > 30 else "var(--ink)"})],
                     className="dca-data-row"),
        ] + ([
            html.Div([html.Span("Assessed", className="dca-data-label"),
                      html.Span(assessed, className="dca-data-value")], className="dca-data-row"),
        ] if assessed else []) + ([
            html.Div([html.Span("Default amt", className="dca-data-label"),
                      html.Span(default_amt, className="dca-data-value")], className="dca-data-row"),
        ] if default_amt else []), className="dca-section"),
    ])


def _drawer_timeline(p: dict) -> html.Div:
    timeline = p.get("timeline") or []
    sale_date = p.get("sale_date","")
    events = list(timeline)
    if sale_date:
        events = events + [{"date": sale_date[:10], "stage_short": "Auction",
                            "stage_num": 2, "upcoming": True}]

    stage_descs = {
        "NOD":  "Borrower defaulted; 90-day cure period begins.",
        "NTS":  "Trustee sale scheduled; minimum bid published.",
        "NOR":  "Borrower cured the default — filing rescinded.",
        "TDUS": "Property transferred via trustee deed at auction.",
        "Auction": p.get("auction_location","") or "Trustee sale at courthouse.",
    }
    stage_colors_short = {
        "NOD": "#D97706", "NTS": "#DC2626", "NOR": "#059669",
        "TDUS": "#7C3AED", "Auction": "#DC2626",
    }

    n = len(events)
    title_txt = f"Foreclosure timeline ({n} event{'s' if n != 1 else ''})"

    items = []
    for ev in events:
        short = ev.get("stage_short","")
        num   = ev.get("stage_num", 0)
        dt    = (ev.get("date","") or "")[:10]
        upcoming = ev.get("upcoming", False)
        c = stage_colors_short.get(short, "#78716C")
        desc = stage_descs.get(short, "")
        items.append(html.Div(
            [
                html.Div(style={
                    "position": "absolute", "left": "-20px", "top": "4px",
                    "width": "14px", "height": "14px", "borderRadius": "50%",
                    "background": c, "border": "3px solid var(--bg)",
                    "boxShadow": f"0 0 0 3px {c}44" if upcoming else "none",
                }),
                html.Div(
                    [dt, html.Span(" · UPCOMING", style={"color": c, "marginLeft": "6px"}) if upcoming else None],
                    className="dca-tl-date",
                ),
                html.Div(
                    "Trustee Sale Auction" if short == "Auction" else
                    next((v["full"] for k, v in _STAGE_CFG.items() if v["short"] == short), short),
                    className="dca-tl-stage", style={"color": c},
                ),
                html.Div(desc, className="dca-tl-desc"),
            ],
            className="dca-tl-event", style={"position": "relative"},
        ))

    return html.Div([
        html.Div(title_txt, className="dca-section-title"),
        html.Div(
            [html.Div(className="dca-timeline-spine"), *items],
            className="dca-timeline",
        ),
    ], className="dca-section")


def _drawer_financials(p: dict) -> html.Div:
    emv_str  = p.get("emv","")
    ltv_str  = p.get("ltv","")
    loan_str = p.get("loan_amount","")
    sale_date = p.get("sale_date","")
    min_bid  = p.get("min_bid","")

    # Parse numeric values for equity bar
    try:
        ltv_val = float(str(ltv_str).rstrip("%") or "")
    except (ValueError, TypeError):
        ltv_val = None

    equity_bar = None
    if ltv_val is not None:
        equity_val = 100 - ltv_val
        equity_bar = html.Div([
            html.Div("EMV vs Loan", className="dca-chart-title"),
            html.Div(
                [
                    html.Div(style={"position": "absolute", "left": "0", "top": "0", "bottom": "0",
                                    "width": f"{ltv_val}%", "background": "var(--ink-2)"},
                             className="dca-equity-bar-loan"),
                    html.Div(style={"position": "absolute", "top": "0", "bottom": "0", "right": "0",
                                    "left": f"{ltv_val}%"},
                             className="dca-equity-bar-equity"),
                ],
                className="dca-equity-bar",
            ),
            html.Div(
                [
                    html.Span([html.Strong(_money(loan_str)), f" loan ({ltv_val:.0f}%)"]),
                    html.Span(
                        [html.Strong(_money(emv_str) if emv_str else "—"), f" equity ({equity_val:.0f}%)"],
                        style={"color": "var(--good)"},
                    ),
                ],
                className="dca-equity-bar-labels",
            ),
        ], className="dca-equity-bar-wrap")

    auction_section = None
    if sale_date and min_bid:
        auction_section = html.Div([
            html.Div("Auction", className="dca-section-title"),
            html.Div([html.Span("Min bid", className="dca-data-label"),
                      html.Span(_money(min_bid), className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("Sale date", className="dca-data-label"),
                      html.Span(sale_date[:10] if len(sale_date) >= 10 else sale_date,
                                className="dca-data-value",
                                style={"color": "var(--nts)"})], className="dca-data-row"),
        ], className="dca-section")

    return html.Div([
        html.Div([
            html.Div("Equity position", className="dca-section-title"),
            equity_bar,
            html.Div([html.Span("Loan amount", className="dca-data-label"),
                      html.Span(loan_str or "—", className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("Est. market value", className="dca-data-label"),
                      html.Span(emv_str or "—", className="dca-data-value")], className="dca-data-row"),
            html.Div([html.Span("LTV", className="dca-data-label"),
                      html.Span(f"{ltv_str}%" if ltv_str and not str(ltv_str).endswith("%") else ltv_str or "—",
                                className="dca-data-value")], className="dca-data-row"),
        ], className="dca-section"),

        auction_section,

        # Max Bid Calculator
        html.Div([
            html.Div("Max Bid Calculator", className="dca-section-title"),
            html.Div([
                html.Div(
                    [html.Span("Target ROI", style={"fontSize":"12px","fontWeight":"600","color":"var(--ink-2)"}),
                     html.Span(id="drawer-roi-label",
                               style={"fontSize":"13px","fontWeight":"700","color":"var(--accent-2)"})],
                    style={"display":"flex","justifyContent":"space-between","marginBottom":"8px"},
                ),
                dcc.Slider(
                    id="drawer-roi-slider",
                    min=0, max=50, step=1, value=20,
                    marks={0: "0%", 25: "25%", 50: "50%"},
                    tooltip={"placement": "bottom", "always_visible": False},
                    className="mb-2",
                ),
                html.Div(
                    [html.Span("Suggested Max Bid",
                               style={"fontSize":"10.5px","color":"var(--ink-3)",
                                      "textTransform":"uppercase","letterSpacing":"0.06em",
                                      "fontWeight":"600"}),
                     html.Span(id="drawer-max-bid",
                               className="dca-max-bid-result dca-serif")],
                    style={"display":"flex","justifyContent":"space-between",
                           "alignItems":"baseline","marginTop":"10px","paddingTop":"10px",
                           "borderTop":"1px solid rgba(184,87,40,0.25)"},
                ),
                html.Div("Based on est. market value × (1 − target ROI).",
                         style={"fontSize":"10.5px","color":"var(--ink-3)","marginTop":"4px"}),
            ], className="dca-max-bid-card"),
        ], className="dca-section"),
    ])


def _drawer_research(p: dict) -> html.Div:
    addr = p.get("address","")
    city = p.get("city","")
    lat_v = p.get("lat_val",""); lon_v = p.get("lon_val","")
    q = _quote(f"{addr} {city} CA") if addr else ""

    links = [
        ("Zillow",     f"https://www.zillow.com/homes/{q}_rb/" if q else "#",   "#006AFF"),
        ("Redfin",     f"https://www.redfin.com/search-page?s={q}" if q else "#", "#A02021"),
        ("Street View",
         f"https://maps.google.com/maps?q=&layer=c&cbll={lat_v},{lon_v}" if lat_v and lon_v else "#",
         "#1A73E8"),
        ("County Record", p.get("source_url","#") or "#",                         "var(--ink-2)"),
    ]

    trustee      = p.get("trustee_name") or p.get("trustee","")
    trustee_url  = p.get("trustee_url","")
    trustee_ph   = p.get("trustee_phone","")
    beneficiary  = p.get("beneficiary","")
    ben_ph       = p.get("ben_phone","")

    trustee_rows = []
    if trustee:
        name_el = (html.A(trustee, href=trustee_url, target="_blank",
                          style={"color":"var(--accent)"})
                   if trustee_url else html.Span(trustee))
        phone_el = ([" ", html.A(trustee_ph, href=f"tel:{trustee_ph}",
                                  style={"color":"var(--accent)"})]) if trustee_ph else []
        trustee_rows.append(
            html.Div([html.Span("Trustee", className="dca-data-label"),
                      html.Span([name_el] + phone_el, className="dca-data-value")],
                     className="dca-data-row")
        )
    if beneficiary:
        phone_el2 = ([" ", html.A(ben_ph, href=f"tel:{ben_ph}",
                                   style={"color":"var(--accent)"})]) if ben_ph else []
        trustee_rows.append(
            html.Div([html.Span("Beneficiary", className="dca-data-label"),
                      html.Span([beneficiary] + phone_el2, className="dca-data-value")],
                     className="dca-data-row")
        )

    return html.Div([
        html.Div(
            [html.Div("Trustee / Lender", className="dca-section-title")] + trustee_rows
            if trustee_rows else [],
            className="dca-section",
        ) if trustee_rows else None,

        html.Div([
            html.Div("External research", className="dca-section-title"),
            html.Div(
                [
                    html.A(
                        [html.Span(style={"width":"8px","height":"8px","borderRadius":"50%",
                                          "background":lc,"display":"inline-block",
                                          "marginRight":"7px","verticalAlign":"middle"}),
                         ln,
                         html.Span(" ↗", style={"color":"var(--ink-4)"})],
                        href=lu, target="_blank", rel="noopener noreferrer",
                        className="dca-research-link",
                    )
                    for ln, lu, lc in links
                ],
                className="dca-research-grid",
            ),
        ], className="dca-section"),
    ])


def _build_drawer(p: dict) -> list:
    """Build full drawer content from GeoJSON properties dict."""
    stage_short = p.get("stage_short","")
    stage_color = "#78716C"
    stage_bg    = "#F1ECE5"
    for k, v in _STAGE_CFG.items():
        if v["short"] == stage_short:
            stage_color = v["color"]
            stage_bg    = v["bg"]
            break

    sale_date  = p.get("sale_date","")
    sale_time  = p.get("sale_time","")
    auction_loc = p.get("auction_location","")
    dist       = p.get("auction_dist_miles","")
    min_bid    = p.get("min_bid","")
    city       = p.get("city","")
    zip_       = p.get("zip","")
    county     = p.get("county","")
    address    = p.get("address","Property Details")

    conf_map = {
        "precise":  ("📍 Rooftop",        "var(--good)"),
        "good":     ("📍 Good Match",      "#2563eb"),
        "approx":   ("⚠ Verify Location", "var(--warn)"),
        "geocoded": ("📍 Geocoded",        "var(--ink-3)"),
    }
    conf_label, conf_color = conf_map.get(p.get("geocode_confidence","geocoded"),
                                           ("📍 Geocoded", "var(--ink-3)"))

    # Days until auction
    days_until = None
    if sale_date:
        try:
            days_until = (pd.to_datetime(sale_date) - pd.Timestamp.now().normalize()).days
        except Exception:
            pass

    flags = []
    if p.get("high_equity"): flags.append("high_equity")
    if p.get("low_ltv"):     flags.append("low_ltv")
    if p.get("hard_money") == "Yes": flags.append("hard_money")
    if p.get("corporate")  == "Yes": flags.append("corporate")
    if p.get("source") == "RETRAN":  flags.append(None)  # no badge for RETRAN

    # Auction alert
    auction_alert = None
    if sale_date and days_until is not None and days_until >= 0:
        sale_str = sale_date[:10] if len(sale_date) >= 10 else sale_date
        auction_alert = html.Div([
            html.Div("⚡ Trustee Sale Auction", className="dca-auction-tag"),
            html.Div(f"{sale_str}" + (f" at {sale_time}" if sale_time else ""),
                     style={"fontSize":"16px","fontWeight":"600","color":"var(--ink)"}),
            html.Div(
                (auction_loc or "") + (f" · {dist} from property" if dist else ""),
                style={"fontSize":"12px","color":"var(--ink-2)","marginTop":"3px"},
            ) if auction_loc or dist else None,
            html.Div(
                [
                    html.Div([
                        html.Div("Min Bid", style={"fontSize":"10px","color":"var(--ink-3)",
                                                   "textTransform":"uppercase","letterSpacing":"0.06em",
                                                   "fontWeight":"600"}),
                        html.Div(_money(min_bid), className="dca-serif",
                                 style={"fontSize":"20px","lineHeight":"1.1","color":"var(--ink)"}),
                    ]) if min_bid else None,
                    html.Div([
                        html.Div("Days Until", style={"fontSize":"10px","color":"var(--ink-3)",
                                                      "textTransform":"uppercase","letterSpacing":"0.06em",
                                                      "fontWeight":"600"}),
                        html.Div(str(days_until), className="dca-serif",
                                 style={"fontSize":"20px","lineHeight":"1.1",
                                        "color":"var(--nts)" if days_until <= 7 else "var(--ink)"}),
                    ]),
                ],
                style={"display":"flex","justifyContent":"space-between","marginTop":"9px",
                       "paddingTop":"9px","borderTop":"1px solid rgba(220,38,38,0.15)"},
            ),
        ], className="dca-auction-alert")

    return [
        # Stage pill + badges row
        html.Div(
            [
                _stage_pill(stage_short, stage_color, stage_bg),
                html.Span(conf_label, style={"fontSize":"10.5px","color":conf_color,
                                              "fontWeight":"600","padding":"2px 7px",
                                              "borderRadius":"4px",
                                              "background":conf_color+"18"}),
            ] + [b for b in [_flag_badge(f) for f in flags if f] if b],
            style={"display":"flex","flexWrap":"wrap","gap":"5px","marginBottom":"12px"},
        ),

        # Auction alert (if applicable)
        auction_alert,
    ]


# ── Stat cell helper ─────────────────────────────────────────────────────────
def _stat_cell(icon: str | None, value: int, label: str, color: str) -> html.Div:
    num_str = f"{int(value):,}" if value is not None else "0"
    num_children = (
        [html.Span(icon, style={"fontSize":"12px","color":color}),
         html.Span(num_str, className="dca-serif",
                   style={"fontSize":"26px","lineHeight":"1",
                          "letterSpacing":"-0.02em","color":color})]
        if icon else
        html.Span(num_str, className="dca-serif",
                  style={"fontSize":"26px","lineHeight":"1",
                         "letterSpacing":"-0.02em","color":color})
    )
    return html.Div(
        [html.Div(num_children,
                  style={"display":"flex","alignItems":"baseline","gap":"5px"}),
         html.Div(label, className="dca-stat-label")],
        className="dca-stat-cell",
    )


# ── Layout ────────────────────────────────────────────────────────────────────
def layout():
    df     = load_df()
    stats  = get_headline_stats(df)
    all_counties = sorted(c for c in df["County"].dropna().unique().tolist() if str(c).strip())
    all_stages   = [s for s in df["Stage"].dropna().unique().tolist()
                    if s.strip() and s in STAGE_COLORS]
    max_loan     = int(df["Loan Amount"].max(skipna=True) or 5_000_000)
    min_date     = df["Recording Date"].min()
    max_date     = df["Recording Date"].max()

    # No default date restriction — recent records aren't geocoded yet so a 7-day
    # window shows almost nothing on the map. Show all pins by default; users can
    # add a date filter manually.

    updated = _last_updated()
    total_props = len(df)  # get_headline_stats doesn't return total_properties

    return html.Div([
        # ── Stores ─────────────────────────────────────────────────────────────
        dcc.Store(id="loan-defaults",           data={"min": 0, "max": max_loan}),
        dcc.Store(id="sidebar-valuation-store", data=None),
        dcc.Store(id="batch-launch-dummy",      data=None),
        dcc.Store(id="selected-card-id",        data=None),
        dcc.Download(id="download-csv"),
        dcc.Download(id="download-mailing"),

        # ── Stat Bar ───────────────────────────────────────────────────────────
        html.Div(
            [
                _stat_cell("⚡", stats.get("auctions_this_week", 0),
                           "Auctions this week", "var(--nts)"),
                _stat_cell(None, stats.get("new_nods_week", 0),
                           "New NODs (7d)", "var(--nod)"),
                _stat_cell("◆", stats.get("high_equity", 0),
                           "High-equity leads", "var(--good)"),
                _stat_cell("◇", stats.get("low_ltv", 0),
                           "Low-LTV leads", "#1D4ED8"),
                html.Div(
                    [html.Div(
                        html.Span(f"{total_props:,}", className="dca-serif",
                                  style={"fontSize":"26px","lineHeight":"1",
                                         "letterSpacing":"-0.02em","color":"var(--ink-2)"}),
                     ),
                     html.Div(
                         [html.Span("Total properties", className="dca-stat-label"),
                          html.Span(f"Updated {updated}", className="dca-updated-text")
                          if updated else None],
                     )],
                    className="dca-stat-cell",
                    style={"borderRight": "none"},
                ),
            ],
            id="dca-stat-bar",
        ),

        # ── Main shell: filter | map | list rail ──────────────────────────────
        html.Div(
            [
                # ── Filter Rail ────────────────────────────────────────────────
                html.Div(
                    _build_filter_rail(all_stages, all_counties, max_loan,
                                       min_date, max_date),
                    id="dca-filter-rail",
                ),

                # ── Map Column ─────────────────────────────────────────────────
                # IMPORTANT: dl.Map must have an explicit pixel/calc height — NOT
                # height:100% — because dcc.Loading's wrapper div has height:auto,
                # so height:100% resolves to 0 and Leaflet never renders tiles.
                html.Div(
                    [
                        dl.Map(
                                id="main-map",
                                center=[36.8, -119.4],
                                zoom=6,
                                style={"height": "calc(100vh - 130px)", "width": "100%"},
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
                                                attribution="Tiles &copy; Esri &mdash; Esri, Maxar",
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

                        # Map count chip
                        html.Div(id="dca-map-count", children="— properties on map"),

                        # Legend
                        html.Div(
                            [
                                html.Div(
                                    [html.Span(className="dca-legend-dot",
                                               style={"background": v["color"]}),
                                     v["short"]],
                                    className="dca-legend-item",
                                )
                                for v in _STAGE_CFG.values()
                            ],
                            id="dca-map-legend",
                        ),
                    ],
                    id="dca-map-col",
                ),

                # ── Property List Rail ─────────────────────────────────────────
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div([
                                    html.Span("0", id="rail-count", className="dca-rail-count"),
                                    html.Span(" of 0", id="rail-count-of", className="dca-rail-count-of"),
                                    html.Div("Distressed properties", className="dca-rail-sublabel"),
                                ]),
                                dcc.Dropdown(
                                    id="list-sort",
                                    options=[
                                        {"label": "Newest filings",    "value": "recent"},
                                        {"label": "Soonest auction",   "value": "auction"},
                                        {"label": "Most equity",       "value": "equity"},
                                        {"label": "Value: high → low", "value": "value_high"},
                                        {"label": "Value: low → high", "value": "value_low"},
                                    ],
                                    value="recent",
                                    clearable=False,
                                    style={"fontSize": "11.5px", "minWidth": "150px"},
                                ),
                            ],
                            className="dca-rail-header",
                        ),
                        dcc.Loading(type="dot", color="var(--accent)",
                            children=html.Div(id="dca-list-cards"),
                        ),
                    ],
                    id="dca-list-rail",
                ),
            ],
            id="dca-map-shell",
        ),

        # ── Property Drawer ────────────────────────────────────────────────────
        html.Div(id="dca-drawer-backdrop", n_clicks=0),
        html.Div(
            [
                # Photo header
                html.Div(
                    [
                        html.Div(id="dca-drawer-photo-content"),
                        html.Div(
                            [
                                html.Div(id="dca-drawer-address", className="dca-drawer-address"),
                                html.Div(id="dca-drawer-city",    className="dca-drawer-city"),
                            ],
                            className="dca-drawer-photo-overlay",
                        ),
                        html.Button(
                            html.I(className="bi bi-x", style={"fontSize": "16px"}),
                            id="drawer-close-btn",
                            className="dca-drawer-close",
                            n_clicks=0,
                        ),
                    ],
                    id="dca-drawer-photo",
                ),

                # Tab bar
                html.Div(
                    [
                        html.Button("Overview",   id="drawer-tab-overview",   n_clicks=0,
                                    className="dca-drawer-tab active"),
                        html.Button("Timeline",   id="drawer-tab-timeline",   n_clicks=0,
                                    className="dca-drawer-tab"),
                        html.Button("Financials", id="drawer-tab-financials", n_clicks=0,
                                    className="dca-drawer-tab"),
                        html.Button("Research",   id="drawer-tab-research",   n_clicks=0,
                                    className="dca-drawer-tab"),
                    ],
                    className="dca-drawer-tabs",
                ),

                # Body (two static sections)
                html.Div(
                    [
                        html.Div(id="dca-drawer-badges-section"),
                        html.Div(id="drawer-tab-body"),
                    ],
                    id="dca-drawer-body",
                ),
            ],
            id="dca-drawer",
        ),
    ])


def _build_filter_rail(all_stages, all_counties, max_loan, min_date, max_date):
    """Build the filter rail children."""
    # Stage toggle buttons (visual) + hidden Checklist (the actual filter store)
    stage_items = []
    for stage in all_stages:
        cfg = _STAGE_CFG.get(stage)
        if not cfg:
            continue
        color = cfg["color"]
        full  = cfg["full"]
        stage_items.append(
            html.Div(
                id={"type": "stage-btn", "index": stage},
                className="dca-stage-btn",
                n_clicks=0,
                children=[
                    html.Span(
                        [html.Span(className="dot", style={"background": color}),
                         html.Span(cfg["short"], className="stage-name"),
                         html.Span(full, className="stage-full")],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Span(id={"type": "stage-count", "index": stage},
                              className="stage-count", children=""),
                ],
            )
        )

    flags_cfg = [
        ("high_equity",       "High Equity (>30%)", "var(--good)"),
        ("low_ltv",           "Low LTV (<50%)",     "#1D4ED8"),
        ("hard_money",        "Hard Money loan",    "#A16207"),
        ("corporate",         "Corporate grantor",  "var(--ink-3)"),
        ("upcoming_auctions", "Upcoming auction",   "var(--nts)"),
    ]

    # County filter — simple multi-select dropdown (no pattern-match complexity)

    return [
        # ── Stage filter ──────────────────────────────────────────────────────
        html.Div([
            html.Div("Foreclosure Stage", className="dca-filter-group-title"),
            dbc.Checklist(
                id="stage-filter",
                options=[{"label": "", "value": s} for s in all_stages],
                value=all_stages,
                style={"display": "none"},
            ),
            *stage_items,
        ], className="dca-filter-group"),

        # ── Date range ────────────────────────────────────────────────────────
        # Default: no start_date → all pins visible. Recent scraped records haven't
        # been geocoded yet, so a 7-day window shows almost nothing on the map.
        html.Div([
            html.Div("Recording Date", className="dca-filter-group-title"),
            dcc.DatePickerRange(
                id="date-filter",
                min_date_allowed=min_date.date() if pd.notna(min_date) else None,
                max_date_allowed=max_date.date() if pd.notna(max_date) else None,
                start_date=None,
                display_format="YYYY-MM-DD",
                style={"fontSize": "12px"},
            ),
        ], className="dca-filter-group"),

        # ── Property flags ────────────────────────────────────────────────────
        html.Div([
            html.Div("Property Flags", className="dca-filter-group-title"),
            dbc.Checklist(
                id="flag-filter",
                options=[{"label": label, "value": key}
                         for key, label, _ in flags_cfg],
                value=[],
                switch=True,
                className="small",
            ),
        ], className="dca-filter-group"),

        # ── Counties ─────────────────────────────────────────────────────────
        html.Div([
            html.Div("Counties", className="dca-filter-group-title"),
            dcc.Dropdown(
                id="county-filter",
                options=[{"label": c.replace(" County", ""), "value": c} for c in all_counties],
                value=[],
                multi=True,
                placeholder="All counties…",
                style={"fontSize": "12px"},
            ),
        ], className="dca-filter-group"),

        # ── Loan slider ───────────────────────────────────────────────────────
        html.Div([
            html.Div("Loan Amount", className="dca-filter-group-title"),
            html.Div(id="loan-range-label", className="dca-range-labels"),
            dcc.RangeSlider(
                id="loan-slider",
                min=0, max=max_loan, step=25_000,
                value=[0, max_loan],
                marks={
                    0: {"label": "$0", "style": {"fontSize": "10px"}},
                    max_loan: {"label": f"${max_loan//1_000_000:.0f}M+",
                               "style": {"fontSize": "10px"}},
                },
                tooltip={"placement": "bottom", "always_visible": False},
            ),
        ], className="dca-filter-group"),

        # ── Export buttons ────────────────────────────────────────────────────
        html.Div([
            html.Button(
                [html.I(className="bi bi-download me-2"), "Export CSV"],
                id="export-btn",
                className="dca-reset-btn mb-2",
                style={"background": "var(--accent)", "color": "#fff",
                       "border": "none", "fontWeight": "600"},
            ),
            html.Button(
                [html.I(className="bi bi-envelope me-2"), "Mailing CSV"],
                id="mailing-btn",
                className="dca-reset-btn mb-2",
            ),
            html.Button(
                [html.I(className="bi bi-arrow-counterclockwise me-2"), "Reset Filters"],
                id="reset-filters-btn",
                className="dca-reset-btn",
            ),
        ], className="dca-filter-group", style={"borderBottom": "none"}),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("map-layer",       "data"),
    Output("dca-list-cards",  "children"),
    Output("rail-count",      "children"),
    Output("rail-count-of",   "children"),
    Output("dca-map-count",   "children"),
    Output("loan-range-label","children"),
    Input("county-filter",   "value"),
    Input("stage-filter",    "value"),
    Input("date-filter",     "start_date"),
    Input("date-filter",     "end_date"),
    Input("loan-slider",     "value"),
    Input("flag-filter",     "value"),
    Input("list-sort",       "value"),
    Input("global-search",   "value"),
    State("main-map",        "center"),
    State("main-map",        "zoom"),
    State("selected-card-id","data"),
)
def update_all(counties, stages, date_start, date_end, loan_range, flags,
               sort_by, search, map_center, map_zoom, selected_id):
    import traceback
    try:
        return _update_all_impl(counties, stages, date_start, date_end, loan_range, flags,
                                sort_by, search, map_center, map_zoom, selected_id)
    except Exception as exc:
        print(f"[update_all ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        raise


def _update_all_impl(counties, stages, date_start, date_end, loan_range, flags,
                     sort_by, search, map_center, map_zoom, selected_id):
    df = load_df()

    hard_money        = "hard_money"        in (flags or [])
    corporate         = "corporate"         in (flags or [])
    upcoming_auctions = "upcoming_auctions" in (flags or [])
    high_equity       = "high_equity"       in (flags or [])
    low_ltv           = "low_ltv"           in (flags or [])
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

    # Search filter
    if search and search.strip():
        s = search.strip().lower()
        text_cols = ["Property Address", "City", "ZIP", "County", "Borrower Name"]
        avail = [c for c in text_cols if c in filtered.columns]
        mask = filtered[avail].fillna("").apply(
            lambda col: col.str.lower().str.contains(s, na=False)
        ).any(axis=1)
        filtered = filtered[mask]

    geojson = to_geojson(filtered)
    geocoded_count = len(geojson["features"])
    total_count = len(filtered)

    # Loan range label
    lo = loan_range[0] if loan_range else 0
    hi = loan_range[1] if loan_range else 0
    loan_label = [
        html.Span(f"${lo:,.0f}", style={"fontWeight":"600"}),
        " – ",
        html.Span(f"${hi:,.0f}", style={"fontWeight":"600"}),
    ]

    # Property list rail cards (geocoded records only, up to 200)
    on_map = filtered.dropna(subset=["Latitude", "Longitude"])
    records = to_table_records(on_map)

    # Sort
    if sort_by == "auction":
        records = sorted(records,
            key=lambda r: r.get("Sale Date","9999") or "9999")
    elif sort_by == "equity":
        def _eq(r):
            try: return -float(str(r.get("Equity %","0") or "0").rstrip("%"))
            except: return 0
        records = sorted(records, key=_eq)
    elif sort_by == "value_high":
        def _emv(r):
            try:
                raw = str(r.get("EMV","") or r.get("Assessed Total($)","") or "0")
                return -float(raw.replace("$","").replace(",",""))
            except: return 0
        records = sorted(records, key=_emv)
    elif sort_by == "value_low":
        def _emv2(r):
            try:
                raw = str(r.get("EMV","") or r.get("Assessed Total($)","") or "0")
                return float(raw.replace("$","").replace(",",""))
            except: return 1e12
        records = sorted(records, key=_emv2)
    # default: "recent" — to_table_records is already newest-first typically

    # Build cards (cap at 200 for performance)
    display_records = records[:200]
    cards = []
    for i, rec in enumerate(display_records):
        # Map table record keys → drawer property keys
        p = {
            "address":      rec.get("Property Address",""),
            "city":         rec.get("City",""),
            "zip":          rec.get("ZIP",""),
            "county":       rec.get("County",""),
            "stage_short":  rec.get("Stage",""),
            "recording_date": str(rec.get("Recording Date","") or ""),
            "sale_date":    str(rec.get("Sale Date","") or ""),
            "sale_time":    rec.get("Time","") or "",
            "min_bid":      rec.get("Min Bid",""),
            "loan_amount":  rec.get("Loan Amount",""),
            "emv":          rec.get("EMV","") or rec.get("Assessed Total($)",""),
            "ltv":          str(rec.get("LTV","") or ""),
            "equity_pct":   str(rec.get("Equity %","") or "").rstrip("%"),
            "beds":         str(rec.get("Beds","") or ""),
            "baths":        str(rec.get("Baths","") or ""),
            "sqft":         str(rec.get("Sq Ft","") or ""),
            "apn":          str(rec.get("APN","") or str(i)),
            "hard_money":   rec.get("Hard Money Loan?",""),
            "corporate":    rec.get("Corporate Grantor?",""),
            "high_equity":  rec.get("High Equity", False),
            "low_ltv":      rec.get("Low LTV", False),
        }
        is_selected = (selected_id is not None and
                       str(p.get("apn","")) == str(selected_id))
        cards.append(_prop_card(p, i, selected=is_selected))

    if not cards:
        cards = [html.Div("No properties match the current filters.",
                          style={"padding":"30px","textAlign":"center",
                                 "color":"var(--ink-3)","fontSize":"13px"})]

    count_of_text = f" of {total_count:,}"
    map_count_text = f"{geocoded_count:,} properties on map"

    return (geojson, cards, f"{len(display_records):,}", count_of_text,
            map_count_text, loan_label)


# ── Property drawer open (map click) ─────────────────────────────────────────
@callback(
    Output("dca-drawer",                  "className"),
    Output("dca-drawer-backdrop",        "className"),
    Output("dca-drawer-badges-section",  "children"),
    Output("dca-drawer-address",         "children"),
    Output("dca-drawer-city",       "children"),
    Output("dca-drawer-photo-content", "children"),
    Output("sidebar-valuation-store", "data"),
    Output("selected-card-id",      "data"),
    Input("map-layer",              "clickData"),
    Input("drawer-close-btn",       "n_clicks"),
    Input("dca-drawer-backdrop",    "n_clicks"),
    State("dca-drawer",             "className"),
    prevent_initial_call=True,
)
def toggle_drawer(click_data, close_clicks, backdrop_clicks, current_class):
    from dash import ctx
    triggered = ctx.triggered_id

    # Close triggers
    if triggered in ("drawer-close-btn", "dca-drawer-backdrop"):
        return "dca-drawer", "", [], "", "", None, None, None

    # Map click
    if not click_data:
        raise PreventUpdate
    props = click_data.get("properties", {})
    if not props.get("address"):
        raise PreventUpdate

    p = props
    address = p.get("address","Property Details")
    city    = p.get("city","")
    zip_    = p.get("zip","")
    county  = p.get("county","")
    city_line = f"{city}, CA {zip_} · {county} County" if city else ""

    stage_short = p.get("stage_short","")
    stage_num   = next((v["num"] for k, v in _STAGE_CFG.items()
                        if v["short"] == stage_short), 0)
    photo_svg = _prop_photo_svg(abs(hash(address)) % 100 + 1, stage_num)

    # Extract valuation for max bid calc
    valuation = None
    for raw in [p.get("emv",""), p.get("assessed_total","")]:
        clean = str(raw or "").replace("$","").replace(",","").strip()
        try:
            v = float(clean)
            if v > 0:
                valuation = v
                break
        except (ValueError, TypeError):
            pass

    body_content = _build_drawer(p)

    apn_id = p.get("apn","")

    return ("dca-drawer open", "open", body_content,
            address, city_line, photo_svg, valuation, apn_id)


# ── Drawer tab switching ──────────────────────────────────────────────────────
@callback(
    Output("drawer-tab-body",         "children"),
    Output("drawer-tab-overview",     "className"),
    Output("drawer-tab-timeline",     "className"),
    Output("drawer-tab-financials",   "className"),
    Output("drawer-tab-research",     "className"),
    Input("drawer-tab-overview",      "n_clicks"),
    Input("drawer-tab-timeline",      "n_clicks"),
    Input("drawer-tab-financials",    "n_clicks"),
    Input("drawer-tab-research",      "n_clicks"),
    Input("map-layer",                "clickData"),
    prevent_initial_call=True,
)
def switch_drawer_tab(ov, tl, fi, re, click_data):
    from dash import ctx
    tid = ctx.triggered_id
    active_tab = "overview"
    if tid == "drawer-tab-timeline":   active_tab = "timeline"
    elif tid == "drawer-tab-financials": active_tab = "financials"
    elif tid == "drawer-tab-research": active_tab = "research"
    elif tid == "map-layer":           active_tab = "overview"

    # Build content from latest click_data
    p = (click_data or {}).get("properties", {})

    if active_tab == "overview":
        content = _drawer_overview(p)
    elif active_tab == "timeline":
        content = _drawer_timeline(p)
    elif active_tab == "financials":
        content = _drawer_financials(p)
    else:
        content = _drawer_research(p)

    def _cls(t):
        return f"dca-drawer-tab{' active' if t == active_tab else ''}"

    return (content,
            _cls("overview"), _cls("timeline"),
            _cls("financials"), _cls("research"))


# ── Max bid calculator (clientside) ──────────────────────────────────────────
clientside_callback(
    """function(pct, valuation) {
        if (!valuation || pct === null || pct === undefined) {
            if (typeof pct === 'number') document.getElementById('drawer-roi-label') &&
                (document.getElementById('drawer-roi-label').innerText = pct + '%');
            return '';
        }
        var bid = valuation * (1 - pct / 100);
        return bid <= 0 ? '—' : '$' + Math.round(bid).toLocaleString('en-US');
    }""",
    Output("drawer-max-bid",   "children"),
    Input("drawer-roi-slider", "value"),
    Input("sidebar-valuation-store", "data"),
)

clientside_callback(
    """function(pct) { return pct + '%'; }""",
    Output("drawer-roi-label", "children"),
    Input("drawer-roi-slider", "value"),
)


# ── Reset all filters ─────────────────────────────────────────────────────────
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


# ── Export CSV ────────────────────────────────────────────────────────────────
@callback(
    Output("download-csv", "data"),
    Input("export-btn",     "n_clicks"),
    State("county-filter",  "value"),
    State("stage-filter",   "value"),
    State("date-filter",    "start_date"),
    State("date-filter",    "end_date"),
    State("loan-slider",    "value"),
    State("flag-filter",    "value"),
    prevent_initial_call=True,
)
def export_csv(n_clicks, counties, stages, date_start, date_end, loan_range, flags):
    if not n_clicks:
        raise PreventUpdate
    df = load_df()
    hard_money = "hard_money"        in (flags or [])
    corporate  = "corporate"         in (flags or [])
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
    for col in ["Recording Date", "Sale Date"]:
        if col in export_df.columns:
            export_df[col] = export_df[col].apply(
                lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
            )
    return dcc.send_data_frame(export_df.to_csv, f"distressedca_{date.today()}.csv", index=False)


# ── Mailing CSV ───────────────────────────────────────────────────────────────
@callback(
    Output("download-mailing", "data"),
    Input("mailing-btn",      "n_clicks"),
    State("county-filter",    "value"),
    State("stage-filter",     "value"),
    State("date-filter",      "start_date"),
    State("date-filter",      "end_date"),
    State("loan-slider",      "value"),
    State("flag-filter",      "value"),
    prevent_initial_call=True,
)
def export_mailing(n_clicks, counties, stages, date_start, date_end, loan_range, flags):
    if not n_clicks:
        raise PreventUpdate
    import re as _re
    df = load_df()
    filtered = filter_df(
        df,
        counties=counties or None,
        stages=stages or None,
        date_start=date_start,
        date_end=date_end,
        hard_money="hard_money" in (flags or []),
        corporate="corporate"   in (flags or []),
        loan_min=loan_range[0] if loan_range else None,
        loan_max=loan_range[1] if loan_range else None,
        upcoming_auctions="upcoming_auctions" in (flags or []),
        high_equity="high_equity" in (flags or []),
        low_ltv="low_ltv"         in (flags or []),
    )
    mailing = filtered.copy()

    def _clean_owner(name):
        name = str(name or "").strip()
        m = _re.search(
            r'(?:LLC|INC\.?|CORP(?:ORATION)?|CREDIT\s+UNION|SERVICES?)\s+(.{4,})$',
            name, _re.I,
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
    out = out[out["Property_Address"].str.strip() != ""]
    return dcc.send_data_frame(out.to_csv, f"distressedca_mailing_{date.today()}.csv", index=False)
