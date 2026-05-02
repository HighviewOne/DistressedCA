import glob
import math
import os
import re
import pandas as pd
from functools import lru_cache

_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.join(_DIR, "..")
PARQUET_SNAPSHOT = os.path.join(_APP_ROOT, "assets", "data", "nod_master.parquet")
NOD_MASTER = os.path.join(_APP_ROOT, "..", "NOD_Data", "SoCal_NOD_Master.xlsx")
RETRAN_GLOB = os.path.join(_APP_ROOT, "..", "retran", "RETRAN_NODs_*.csv")
RETRAN_MYFILE_GLOB = os.path.join(_APP_ROOT, "..", "Downloads", "MyFile*.csv")

STAGE_COLORS = {
    "NOD  — Notice of Default": "#f59e0b",
    "NTS  — Notice of Trustee's Sale": "#ef4444",
    "NOR  — Notice of Rescission": "#22c55e",
    "TDUS — Trustee's Deed Upon Sale": "#7c3aed",
}

STAGE_SHORT = {
    "NOD  — Notice of Default": "NOD",
    "NTS  — Notice of Trustee's Sale": "NTS",
    "NOR  — Notice of Rescission": "NOR",
    "TDUS — Trustee's Deed Upon Sale": "TDUS",
}

# Known California foreclosure auction sites (lat, lon)
_AUCTION_COORDS: dict[str, tuple[float, float]] = {
    "250 MAIN EL CAJON":       (32.7948, -116.9625),  # San Diego Co.
    "400 CIVIC POMONA":        (34.0553, -117.7509),  # LA Co. East
    "13111 SYCAMORE NORWALK":  (33.9064, -118.0839),  # LA Co.
    "815 SIXTH CORONA":        (33.8783, -117.5667),  # Riverside Co.
    "849 SIXTH CORONA":        (33.8783, -117.5667),  # Riverside Co.
    "13220 CENTRAL CHINO":     (34.0166, -117.6882),  # SB Co.
    "13260 CENTRAL CHINO":     (34.0166, -117.6882),
    "10650 TREENA SAN DIEGO":  (32.8783, -117.1478),
    "17305 GILMORE LAKE BALBOA":(34.1946, -118.4928), # LA Co.
    "2607 COLORADO EAGLE ROCK":(34.1343, -118.2001),  # LA Co.
    "100 CITY DRIVE ORANGE":   (33.8002, -117.8740),  # OC
    "700 CIVIC SANTA ANA":     (33.7479, -117.8677),  # OC
    "8180 KAISER ANAHEIM":     (33.8501, -117.7551),  # OC
    "217 CIVIC VISTA":         (33.2000, -117.2423),  # SD Co.
    "351 ARROWHEAD SAN BERNARDINO": (34.1066, -117.2929),
    "800 VICTORIA VENTURA":    (34.2652, -119.2290),
}

_CLEAN_AUCTION = re.compile(r'\b(NAN|CA|AT ENTRANCE|MAIN ENTRANCE|SUITE?\s*\d+)\b|[,\.\(\)]', re.I)


def _auction_coords(location: str) -> tuple[float, float] | None:
    """Return (lat, lon) for a known auction location string, else None."""
    raw = _CLEAN_AUCTION.sub(' ', str(location or "")).upper()
    raw = re.sub(r'\s+', ' ', raw).strip()
    # Extract street number + first keyword + city keyword
    tokens = raw.split()
    if len(tokens) < 2:
        return None
    key = " ".join(t for t in tokens if t not in ("E", "W", "N", "S", "ST", "AVE", "AV",
                                                    "BLVD", "DR", "RD", "DRIVE", "STREET",
                                                    "BOULEVARD"))[:40]
    for pattern, coords in _AUCTION_COORDS.items():
        parts = pattern.split()
        if all(p in key for p in parts):
            return coords
    return None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = (math.sin((lat2-lat1)/2)**2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2-lon1)/2)**2)
    return round(2 * R * math.asin(math.sqrt(a)), 1)


TRUSTEE_PORTALS: dict[str, str] = {
    "CLEAR RECON":        "https://clearreconcorp.com/",
    "TRUSTEE CORPS":      "https://www.trusteecorps.com/",
    "QUALITY LOAN":       "https://qualityloan.com/",
    "CALIFORNIA TD":      "https://www.caltd.com/",
    "WESTERN PROGRESSIVE":"https://westernprogressive.com/",
    "NATIONAL DEFAULT":   "https://www.ndscal.com/",
    "ZBS LAW":            "https://zbs-law.com/",
    "BARRETT DAFFIN":     "https://bdfgroup.com/",
    "FIRST AMERICAN":     "https://www.firstam.com/",
    "T.D. SERVICE":       "https://tdsc.com/",
    "TD SERVICE":         "https://tdsc.com/",
    "AFFINIA":            "https://www.affiniadefault.com/",
    "PRESTIGE DEFAULT":   "https://www.prestigedefaultservices.com/",
    "WITKIN AND NEAL":    "https://www.witkinandneal.com/",
    "NESTOR SOLUTIONS":   "https://nestorsolutions.com/",
}


def _trustee_portal(name: str) -> str:
    """Return portal URL for a known CA foreclosure trustee, or empty string."""
    upper = (name or "").upper()
    for key, url in TRUSTEE_PORTALS.items():
        if key in upper:
            return url
    return ""


_DOC_TO_STAGE = {
    "TR": ("NTS  — Notice of Trustee's Sale", 2),
    "TD": ("TDUS — Trustee's Deed Upon Sale", 4),
    "DF": ("NOD  — Notice of Default", 1),
}

_COUNTY_CODES = {
    "": "Los Angeles County",
    "OC": "Orange County",
    "RI": "Riverside County",
    "SD": "San Diego County",
    "SR": "San Bernardino County",
    "VE": "Ventura County",
}


def _norm_apn(s) -> str:
    return str(s or "").replace("-", "").replace(" ", "").upper().strip()


@lru_cache(maxsize=1)
def _load_retran_raw() -> pd.DataFrame:
    """Load and deduplicate all enriched 109-column RETRAN CSV files."""
    files = glob.glob(RETRAN_GLOB) + glob.glob(RETRAN_MYFILE_GLOB)
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, low_memory=False)
            if "document_type" in df.columns and "APN" in df.columns:
                dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    combined["apn_norm"] = combined["APN"].apply(_norm_apn)

    # Parse dates
    combined["sale_date"] = pd.to_datetime(combined["sale_date"], errors="coerce")
    combined["recording_date_rt"] = pd.to_datetime(combined["recording_date"], errors="coerce")

    # Deduplicate: one row per APN + document_type + recording_date
    combined = combined.drop_duplicates(subset=["apn_norm", "document_type", "recording_date"])

    # Normalize lat/lon
    combined["latitude"] = pd.to_numeric(combined["latitude"], errors="coerce")
    combined["longtitude"] = pd.to_numeric(combined["longtitude"], errors="coerce")

    # Normalize county from code
    combined["county_rt"] = combined["county"].fillna("").map(_COUNTY_CODES).fillna(
        combined["county"].fillna("").apply(lambda c: _COUNTY_CODES.get(str(c).strip(), str(c).strip() or "Unknown"))
    )

    return combined


def _norm_address_key(s):
    """Clean and normalize address for fuzzy matching fallback."""
    s = str(s or "").upper().strip()
    # Remove ZIP and CA
    s = re.sub(r"\bCA\b", "", s)
    s = re.sub(r"\b\d{5}(-\d{4})?\b", "", s)
    # Basic suffix normalization
    s = re.sub(r"\bSTREET\b", "ST", s)
    s = re.sub(r"\bAVENUE\b", "AVE", s)
    s = re.sub(r"\bBOULEVARD\b", "BLVD", s)
    s = re.sub(r"\bDRIVE\b", "DR", s)
    s = re.sub(r"\bROAD\b", "RD", s)
    s = re.sub(r"\bLANE\b", "LN", s)
    s = re.sub(r"\bCIRCLE\b", "CIR", s)
    s = re.sub(r"\bCOURT\b", "CT", s)
    s = re.sub(r"\bPLACE\b", "PL", s)
    s = re.sub(r"\bHIGHWAY\b", "HWY", s)
    s = re.sub(r"\bNORTH\b", "N", s)
    s = re.sub(r"\bSOUTH\b", "S", s)
    s = re.sub(r"\bEAST\b", "E", s)
    s = re.sub(r"\bWEST\b", "W", s)
    # Remove punctuation and extra spaces
    s = re.sub(r"[^A-Z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _build_retran_enrichment(rt: pd.DataFrame) -> pd.DataFrame:
    """Return one row per APN with the most useful RETRAN fields for enriching NOD Master."""
    if rt.empty:
        return pd.DataFrame(columns=["apn_norm"])

    # Prefer TR (NTS) rows for sale info, then others
    order = {"TR": 0, "DF": 1, "TD": 2}
    rt = rt.copy()
    rt["_sort"] = rt["document_type"].map(order).fillna(9)
    rt = rt.sort_values(["apn_norm", "_sort", "sale_date"], na_position="last")

    # Build address key for fallback matching
    def _rt_addr(r):
        h = str(r.get("Situs_House") or "").strip()
        s = str(r.get("Situs_Street") or "").strip()
        c = str(r.get("Situs_City") or "").strip()
        if s.startswith(h) and h:
            return _norm_address_key(f"{s} {c}")
        return _norm_address_key(f"{h} {s} {c}")

    rt["addr_key"] = rt.apply(_rt_addr, axis=1)

    agg = rt.groupby("apn_norm", sort=False).agg(
        sale_date=("sale_date", "first"),
        sale_time=("sale_time", "first"),
        min_bid=("min_bid", "first"),
        sale_location=("sale_location", "first"),
        sale_location_city=("sale_location_city", "first"),
        ltv=("ltv", "first"),
        emv=("assessed_value", "first"),
        default_amount=("amount", "first"),
        trustee_name=("trustee_name", "first"),
        trustee_phone=("tee_phone", "first"),
        beneficiary=("beneficiary_name", "first"),
        ben_phone=("ben_phone", "first"),
        addr_key=("addr_key", "first"),
    ).reset_index()

    return agg


def _make_standalone_retran(rt: pd.DataFrame, master_apns: set) -> pd.DataFrame:
    """Build a NOD-Master-shaped DataFrame from RETRAN records not in NOD Master."""
    if rt.empty:
        return pd.DataFrame()

    standalone = rt[~rt["apn_norm"].isin(master_apns)].copy()
    if standalone.empty:
        return pd.DataFrame()

    def _address(row):
        house  = str(row.get("Situs_House")  or "").strip()
        street = str(row.get("Situs_Street") or "").strip()
        if not house and not street:
            return ""
        # Situs_Street sometimes already includes the house number
        if house and street and street.startswith(house):
            return street
        return f"{house} {street}".strip()

    rows = []
    for _, r in standalone.iterrows():
        doc = str(r.get("document_type") or "").upper().strip()
        stage, stage_num = _DOC_TO_STAGE.get(doc, ("NOD  — Notice of Default", 1))
        loan = pd.to_numeric(r.get("loan_amt"), errors="coerce")
        lat = r.get("latitude")
        lon = r.get("longtitude")
        sale_date = r.get("sale_date")
        min_bid = pd.to_numeric(r.get("min_bid"), errors="coerce")
        ltv = pd.to_numeric(r.get("ltv"), errors="coerce")
        emv = r.get("assessed_value")

        rows.append({
            "APN": r.get("APN"),
            "apn_norm": r.get("apn_norm"),
            "Property Address": _address(r),
            "City": str(r.get("Situs_City") or "").strip(),
            "ZIP": str(r.get("Situs_Zip") or "").strip().split(".")[0],
            "Borrower Name": str(r.get("trustor_full_name") or "").strip(),
            "Trustee/Lender": str(r.get("trustee_name") or "").strip(),
            "Loan Amount": loan,
            "Document Type": doc,
            "Stage": stage,
            "Stage #": stage_num,
            "County": str(r.get("county_rt") or "").strip(),
            "Recording Date": r.get("recording_date_rt"),
            "Hard Money Loan?": "No",
            "Corporate Grantor?": "No",
            "Beds": pd.to_numeric(r.get("bed"), errors="coerce"),
            "Baths": pd.to_numeric(r.get("bath"), errors="coerce"),
            "Sq Ft": pd.to_numeric(r.get("sq_feet"), errors="coerce"),
            "Year Built": pd.to_numeric(r.get("yr_built"), errors="coerce"),
            "Assessed Total($)": pd.to_numeric(str(emv or "").replace(",", ""), errors="coerce"),
            "Latitude": lat if pd.notna(lat) else None,
            "Longitude": lon if pd.notna(lon) else None,
            "Source URL": "",
            # RETRAN-specific
            "Sale Date": sale_date,
            "Sale Time": str(r.get("sale_time") or "").strip(),
            "Min Bid": min_bid,
            "Auction Location": " ".join(filter(None, [
                str(r.get("sale_location") or "").strip(),
                str(r.get("sale_location_city") or "").strip(),
            ])),
            "LTV": ltv,
            "EMV": pd.to_numeric(str(emv or "").replace(",", ""), errors="coerce"),
            "Default Amount": pd.to_numeric(r.get("default_amount"), errors="coerce"),
            "Trustee Name": str(r.get("trustee_name") or "").strip(),
            "Trustee Phone": str(r.get("tee_phone") or "").strip(),
            "Beneficiary": str(r.get("beneficiary_name") or "").strip(),
            "Ben Phone": str(r.get("ben_phone") or "").strip(),
            "Source": "RETRAN",
        })

    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def load_df() -> pd.DataFrame:
    """Load from Parquet snapshot (production) or build from raw sources (development)."""
    if os.path.exists(PARQUET_SNAPSHOT):
        df = pd.read_parquet(PARQUET_SNAPSHOT)
        df["Recording Date"] = pd.to_datetime(df["Recording Date"], errors="coerce")
        df["Sale Date"] = pd.to_datetime(df["Sale Date"], errors="coerce")
        df["Loan Amount"] = pd.to_numeric(df["Loan Amount"], errors="coerce")
        df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
        df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
        df["Stage #"] = pd.to_numeric(df["Stage #"], errors="coerce").fillna(0).astype(int)
        df["Min Bid"] = pd.to_numeric(df["Min Bid"], errors="coerce")
        df["LTV"] = pd.to_numeric(df["LTV"], errors="coerce")
        df["EMV"] = pd.to_numeric(df["EMV"], errors="coerce")
        return _add_investor_flags(df)

    # Dev fallback: build from raw Excel + RETRAN CSVs
    master = pd.read_excel(NOD_MASTER)
    master["Recording Date"] = pd.to_datetime(master["Recording Date"], errors="coerce")
    master["Loan Amount"] = pd.to_numeric(master["Loan Amount"], errors="coerce")
    master["Latitude"] = pd.to_numeric(master["Latitude"], errors="coerce")
    master["Longitude"] = pd.to_numeric(master["Longitude"], errors="coerce")
    master["Stage #"] = pd.to_numeric(master.get("Stage #", 0), errors="coerce").fillna(0).astype(int)
    master["apn_norm"] = master["APN"].apply(_norm_apn)
    master["addr_key"] = master["Property Address"].apply(_norm_address_key)
    master["Source"] = "NOD Master"

    rt = _load_retran_raw()
    if not rt.empty:
        enrichment = _build_retran_enrichment(rt)

        # Build Auction Location as a combined field before renaming
        enrichment["Auction Location"] = (
            enrichment["sale_location"].fillna("").str.strip()
            + " "
            + enrichment["sale_location_city"].fillna("").str.strip()
        ).str.strip()

        enrich_df = enrichment.rename(columns={
            "sale_date":      "Sale Date",
            "sale_time":      "Sale Time",
            "min_bid":        "Min Bid",
            "ltv":            "LTV",
            "emv":            "EMV",
            "default_amount": "Default Amount",
            "trustee_name":   "Trustee Name",
            "trustee_phone":  "Trustee Phone",
            "beneficiary":    "Beneficiary",
            "ben_phone":      "Ben Phone",
        })[["apn_norm", "addr_key", "Sale Date", "Sale Time", "Min Bid", "Auction Location",
            "LTV", "EMV", "Default Amount", "Trustee Name",
            "Trustee Phone", "Beneficiary", "Ben Phone"]]

        # Primary match: APN
        master = master.merge(enrich_df.drop(columns="addr_key"), on="apn_norm", how="left")

        # Fallback match: Address (for records missing APN in Master)
        no_apn = master[master["apn_norm"] == ""].index
        if not no_apn.empty and "addr_key" in enrich_df.columns:
            # Create a dedicated address lookup (dropping rows with empty keys)
            addr_lookup = enrich_df[enrich_df["addr_key"] != ""].drop_duplicates("addr_key")
            # Join onto the no-APN subset
            fallback = master.loc[no_apn, ["addr_key"]].merge(addr_lookup, on="addr_key", how="inner")
            if not fallback.empty:
                # Update master with fallback values for columns that are currently NaN
                # We need to align the indexes for the update
                for col in addr_lookup.columns:
                    if col in master.columns and col not in ["addr_key", "apn_norm"]:
                        # Use a temporary series to handle the mapping
                        mapper = fallback.set_index("addr_key")[col]
                        master.loc[no_apn, col] = master.loc[no_apn, col].fillna(master.loc[no_apn, "addr_key"].map(mapper))

        # Append standalone RETRAN records
        master_apns = set(master["apn_norm"].tolist())
        standalone = _make_standalone_retran(rt, master_apns)
        if not standalone.empty:
            master = pd.concat([master, standalone], ignore_index=True)
    else:
        for col in ["Sale Date", "Sale Time", "Min Bid", "Auction Location",
                    "LTV", "EMV", "Default Amount", "Trustee Name",
                    "Trustee Phone", "Beneficiary", "Ben Phone"]:
            master[col] = None

    master["Sale Date"] = pd.to_datetime(master["Sale Date"], errors="coerce")
    return _add_investor_flags(master)


def _add_investor_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Equity % and boolean investor flags from EMV/Assessed + Loan."""
    emv     = pd.to_numeric(df.get("EMV",              pd.Series(dtype=float)), errors="coerce")
    assessed= pd.to_numeric(df.get("Assessed Total($)",pd.Series(dtype=float)), errors="coerce")
    loan    = pd.to_numeric(df.get("Loan Amount",      pd.Series(dtype=float)), errors="coerce")
    ltv_col = pd.to_numeric(df.get("LTV",              pd.Series(dtype=float)), errors="coerce")

    # Use EMV if available (RETRAN), fall back to assessor value
    valuation = emv.where(emv > 0).fillna(assessed.where(assessed > 0))
    equity_pct = ((valuation - loan) / valuation * 100).round(1)

    df = df.copy()
    df["Equity %"]   = equity_pct
    df["High Equity"]= equity_pct > 30
    df["Low LTV"]    = ltv_col.between(0.1, 49.9, inclusive="both")
    return df


def get_headline_stats(df: pd.DataFrame) -> dict:
    """Return global snapshot numbers for the headline bar (ignores active filters)."""
    today   = pd.Timestamp("today").normalize()
    week_ahead = today + pd.Timedelta(days=7)
    week_ago   = today - pd.Timedelta(days=7)
    return {
        "auctions_this_week": int(
            (df["Sale Date"].notna() &
            (df["Sale Date"] >= today) &
            (df["Sale Date"] <= week_ahead)).sum()
        ) if "Sale Date" in df.columns else 0,
        "new_nods_week": int(
            ((df["Stage"] == "NOD  — Notice of Default") &
            (df["Recording Date"] >= week_ago)).sum()
        ) if "Recording Date" in df.columns else 0,
        "high_equity": int(df.get("High Equity", pd.Series(False)).sum()),
        "low_ltv":     int(df.get("Low LTV",     pd.Series(False)).sum()),
        "total_upcoming": int(
            (df["Sale Date"].notna() & (df["Sale Date"] >= today)).sum()
        ) if "Sale Date" in df.columns else 0,
    }


def filter_df(
    df: pd.DataFrame,
    counties=None,
    stages=None,
    date_start=None,
    date_end=None,
    hard_money=False,
    corporate=False,
    loan_min=None,
    loan_max=None,
    upcoming_auctions=False,
    high_equity=False,
    low_ltv=False,
) -> pd.DataFrame:
    if counties:
        df = df[df["County"].isin(counties)]
    if stages:
        df = df[df["Stage"].isin(stages)]
    if date_start:
        df = df[df["Recording Date"] >= pd.Timestamp(date_start)]
    if date_end:
        df = df[df["Recording Date"] <= pd.Timestamp(date_end)]
    if hard_money:
        df = df[df["Hard Money Loan?"] == "Yes"]
    if corporate:
        df = df[df["Corporate Grantor?"] == "Yes"]
    if loan_min is not None and loan_min > 0:
        df = df[df["Loan Amount"].isna() | (df["Loan Amount"] >= loan_min)]
    if loan_max is not None:
        df = df[df["Loan Amount"].isna() | (df["Loan Amount"] <= loan_max)]
    if upcoming_auctions:
        df = df[df["Sale Date"].notna() & (df["Sale Date"] >= pd.Timestamp("today"))]
    if high_equity:
        df = df[df.get("High Equity", pd.Series(False, index=df.index)) == True]
    if low_ltv:
        df = df[df.get("Low LTV", pd.Series(False, index=df.index)) == True]
    return df


def _fmt(val, prefix="", suffix="", decimals=0, na=""):
    if pd.isna(val) or val == "" or str(val).strip() in ("nan", "None", ""):
        return na
    try:
        n = float(val)
        if decimals == 0:
            return f"{prefix}{n:,.0f}{suffix}"
        return f"{prefix}{n:,.{decimals}f}{suffix}"
    except (ValueError, TypeError):
        return str(val).strip() or na


_STAGE_PRIORITY = {
    "NTS  — Notice of Trustee's Sale": 0,   # most urgent first
    "NOD  — Notice of Default": 1,
    "NOR  — Notice of Rescission": 2,
    "TDUS — Trustee's Deed Upon Sale": 3,
}


def _geocode_confidence(row) -> str:
    """Return confidence level: precise | good | approx | geocoded."""
    if str(row.get("Source") or "") == "RETRAN":
        return "precise"   # parcel centroid from county ArcGIS
    score = pd.to_numeric(row.get("Match Score"), errors="coerce")
    if pd.notna(score):
        if score >= 0.9:  return "precise"   # exact APN match
        if score >= 0.65: return "good"      # single name match
        return "approx"                      # ambiguous — verify!
    return "geocoded"  # Census geocoder — generally reliable


def _calc_auction_dist(prop_lat: float, prop_lon: float, location: str) -> str:
    """Return formatted distance string (e.g. '12.3 mi') or empty string."""
    if not location or str(location).upper().strip() in ("", "NAN", "NONE"):
        return ""
    coords = _auction_coords(location)
    if coords is None:
        return ""
    dist = _haversine_miles(prop_lat, prop_lon, coords[0], coords[1])
    return f"{dist} mi"


def _group_by_apn(geo: pd.DataFrame) -> pd.DataFrame:
    """
    Consolidate multi-filing records into one row per unique property using APN.
    Attaches a '_timeline' list to each primary row. Records with no APN pass through.
    """
    geo = geo.copy()
    geo["_apn_key"] = geo["APN"].apply(_norm_apn)

    has_apn = geo[geo["_apn_key"] != ""]
    no_apn  = geo[geo["_apn_key"] == ""].copy()
    no_apn["_timeline"] = [[] for _ in range(len(no_apn))]

    primaries = []
    for apn_key, group in has_apn.groupby("_apn_key", observed=True, sort=False):
        # Deduplicate same (stage + date) within the APN
        group = group.drop_duplicates(subset=["Stage", "Recording Date"]).copy()

        # Build chronological timeline from dated events
        dated = group.dropna(subset=["Recording Date"]).sort_values("Recording Date")
        timeline = [
            {
                "date": str(r["Recording Date"])[:10],
                "stage": str(r.get("Stage") or ""),
                "stage_short": STAGE_SHORT.get(str(r.get("Stage") or ""), ""),
                "stage_num": int(r.get("Stage #") or 0),
            }
            for _, r in dated.iterrows()
        ]

        # Pick primary: most urgent stage, then most recent date
        group["_priority"] = group["Stage"].map(_STAGE_PRIORITY).fillna(9)
        primary = (
            group.sort_values(["_priority", "Recording Date"], ascending=[True, False])
            .iloc[0]
            .to_dict()
        )
        primary["_timeline"] = timeline
        primaries.append(primary)

    grouped = pd.DataFrame(primaries) if primaries else pd.DataFrame()
    if "_priority" in grouped.columns:
        grouped = grouped.drop(columns=["_priority"])

    parts = [p for p in [grouped, no_apn] if not p.empty]
    result = pd.concat(parts, ignore_index=True) if parts else geo
    return result.drop(columns=["_apn_key"], errors="ignore")


def to_geojson(df: pd.DataFrame) -> dict:
    geo = _group_by_apn(df.dropna(subset=["Latitude", "Longitude"]))
    features = []
    for _, row in geo.iterrows():
        stage = str(row.get("Stage") or "")
        source_url = str(row.get("Source URL") or "").strip()
        sale_date = row.get("Sale Date")
        sale_date_str = sale_date.strftime("%B %-d, %Y") if pd.notna(sale_date) else ""
        sale_time = str(row.get("Sale Time") or "").strip()
        auction_loc = str(row.get("Auction Location") or "").strip()

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["Longitude"]), float(row["Latitude"])],
            },
            "properties": {
                "address": str(row.get("Property Address") or "").strip() or "Address unknown",
                "city": str(row.get("City") or "").strip(),
                "zip": str(row.get("ZIP") or "").strip(),
                "borrower": str(row.get("Borrower Name") or "").strip(),
                "trustee": str(row.get("Trustee/Lender") or "").strip(),
                "loan_amount": _fmt(row.get("Loan Amount"), prefix="$", na="N/A"),
                "doc_type": str(row.get("Document Type") or "").strip(),
                "stage": stage,
                "stage_short": STAGE_SHORT.get(stage, stage[:4]),
                "stage_num": int(row.get("Stage #") or 0),
                "recording_date": str(row.get("Recording Date") or "")[:10],
                "county": str(row.get("County") or "").strip(),
                "hard_money": str(row.get("Hard Money Loan?") or "").strip(),
                "corporate": str(row.get("Corporate Grantor?") or "").strip(),
                "beds": _fmt(row.get("Beds"), decimals=0),
                "baths": _fmt(row.get("Baths"), decimals=0),
                "sqft": _fmt(row.get("Sq Ft"), decimals=0),
                "year_built": _fmt(row.get("Year Built"), decimals=0),
                "assessed_total": _fmt(row.get("Assessed Total($)"), prefix="$"),
                "source_url": source_url if source_url and source_url != "nan" else "",
                "color": STAGE_COLORS.get(stage, "#6b7280"),
                "source": str(row.get("Source") or "NOD Master"),
                # RETRAN enrichment
                "sale_date": sale_date_str,
                "sale_time": sale_time,
                "min_bid": _fmt(row.get("Min Bid"), prefix="$", na=""),
                "auction_location": auction_loc,
                "ltv": _fmt(row.get("LTV"), suffix="%", decimals=1, na=""),
                "emv": _fmt(row.get("EMV"), prefix="$", na=""),
                "default_amount": _fmt(row.get("Default Amount"), prefix="$", na=""),
                "trustee_name": str(row.get("Trustee Name") or "").strip(),
                "trustee_phone": str(row.get("Trustee Phone") or "").strip(),
                "beneficiary": str(row.get("Beneficiary") or "").strip(),
                "ben_phone": str(row.get("Ben Phone") or "").strip(),
                "lat_val": float(row["Latitude"]),
                "lon_val": float(row["Longitude"]),
                "geocode_confidence": _geocode_confidence(row),
                "trustee_url": _trustee_portal(
                    str(row.get("Trustee Name") or row.get("Trustee/Lender") or "")
                ),
                "auction_dist_miles": _calc_auction_dist(
                    float(row["Latitude"]), float(row["Longitude"]),
                    str(row.get("Auction Location") or "")
                ),
                "equity_pct": _fmt(row.get("Equity %"), decimals=1, na=""),
                "high_equity": bool(row.get("High Equity") is True),
                "low_ltv": bool(row.get("Low LTV") is True),
                "timeline": row.get("_timeline") or [],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def to_table_records(df: pd.DataFrame, max_rows: int = 500) -> list[dict]:
    cols = [
        "Recording Date", "Property Address", "City", "County", "Stage",
        "Loan Amount", "Sale Date", "Min Bid", "Auction Location",
        "LTV", "Equity %", "High Equity", "Low LTV",
        "Borrower Name", "Trustee/Lender",
        "Hard Money Loan?", "Beds", "Baths", "Sq Ft", "Source",
    ]
    available = [c for c in cols if c in df.columns]
    subset = df[available].head(max_rows).copy()

    if "Recording Date" in subset.columns:
        subset["Recording Date"] = subset["Recording Date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
        )
    if "Sale Date" in subset.columns:
        subset["Sale Date"] = subset["Sale Date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
        )
    if "Loan Amount" in subset.columns:
        subset["Loan Amount"] = subset["Loan Amount"].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else ""
        )
    if "Min Bid" in subset.columns:
        subset["Min Bid"] = subset["Min Bid"].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else ""
        )
    if "LTV" in subset.columns:
        subset["LTV"] = subset["LTV"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else ""
        )
    for col in ["Beds", "Baths", "Sq Ft"]:
        if col in subset.columns:
            subset[col] = subset[col].apply(
                lambda x: str(int(x)) if pd.notna(x) else ""
            )
    # Categorical columns can't accept "" as a fill value — convert to plain str first
    for col in subset.columns:
        if hasattr(subset[col], 'cat'):
            subset[col] = subset[col].astype(str).replace("nan", "")
    return subset.fillna("").to_dict("records")
