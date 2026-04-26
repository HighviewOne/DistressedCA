import glob
import os
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


def _build_retran_enrichment(rt: pd.DataFrame) -> pd.DataFrame:
    """Return one row per APN with the most useful RETRAN fields for enriching NOD Master."""
    if rt.empty:
        return pd.DataFrame(columns=["apn_norm"])

    # Prefer TR (NTS) rows for sale info, then others
    order = {"TR": 0, "DF": 1, "TD": 2}
    rt = rt.copy()
    rt["_sort"] = rt["document_type"].map(order).fillna(9)
    rt = rt.sort_values(["apn_norm", "_sort", "sale_date"], na_position="last")

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
        house = str(row.get("Situs_House") or "").strip()
        street = str(row.get("Situs_Street") or "").strip()
        return f"{house} {street}".strip() if house or street else ""

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
        return df

    # Dev fallback: build from raw Excel + RETRAN CSVs
    master = pd.read_excel(NOD_MASTER)
    master["Recording Date"] = pd.to_datetime(master["Recording Date"], errors="coerce")
    master["Loan Amount"] = pd.to_numeric(master["Loan Amount"], errors="coerce")
    master["Latitude"] = pd.to_numeric(master["Latitude"], errors="coerce")
    master["Longitude"] = pd.to_numeric(master["Longitude"], errors="coerce")
    master["Stage #"] = pd.to_numeric(master.get("Stage #", 0), errors="coerce").fillna(0).astype(int)
    master["apn_norm"] = master["APN"].apply(_norm_apn)
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
        })[["apn_norm", "Sale Date", "Sale Time", "Min Bid", "Auction Location",
            "LTV", "EMV", "Default Amount", "Trustee Name",
            "Trustee Phone", "Beneficiary", "Ben Phone"]]

        master = master.merge(enrich_df, on="apn_norm", how="left")

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
    return master


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


def to_geojson(df: pd.DataFrame) -> dict:
    geo = df.dropna(subset=["Latitude", "Longitude"])
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
            },
        })
    return {"type": "FeatureCollection", "features": features}


def to_table_records(df: pd.DataFrame, max_rows: int = 500) -> list[dict]:
    cols = [
        "Recording Date", "Property Address", "City", "County", "Stage",
        "Loan Amount", "Sale Date", "Min Bid", "Auction Location",
        "LTV", "Borrower Name", "Trustee/Lender",
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
    return subset.fillna("").to_dict("records")
