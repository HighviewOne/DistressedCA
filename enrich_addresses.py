#!/usr/bin/env python3
"""
enrich_addresses.py
===================
Fills in missing Property Address (and lat/lon) for NOD Master records
by querying free, public county GIS APIs.

Supported counties:
  Riverside  — ArcGIS parcel layer (APN lookup + owner-name search)
  LA County  — ArcGIS parcel layer (owner-name search, via assessor_lookup.py)

Usage:
    python enrich_addresses.py              # dry run — shows stats only
    python enrich_addresses.py --run        # enriches and saves
    python enrich_addresses.py --run --county Riverside
    python enrich_addresses.py --run --limit 100
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

NOD_MASTER = Path(__file__).parent.parent / "NOD_Data" / "SoCal_NOD_Master.xlsx"
API_PAUSE  = 0.35   # seconds between GIS calls

# ── Riverside County ArcGIS parcel layer ──────────────────────────────────────
_RV_URL = (
    "https://gis.countyofriverside.us/arcgis/rest/services"
    "/plus/plus_mSrvc_data_prod/MapServer/16/query"
)
_RV_FIELDS = "APN,SITUS_STREET,SITUS_CITY,ZIP_CODE,CLASS_CODE,PRIMARY_OWNER,LAND,STRUCTURES"

# ── Name-cleaning helpers (from enrich_master.py) ─────────────────────────────
_INST = re.compile(
    r"\b(BANK|FINANCIAL|MORTGAGE|LENDING|CAPITAL|INVESTMENT|PROPERTIES|"
    r"REALTY|LLC|LP|INC|CORP|CORPORATION|ASSOCIATION|CREDIT.?UNION|"
    r"FEDERAL|NATIONAL|FUND|TITLE|COMPANY|ESCROW|DEFAULT|SERVICES|"
    r"DEPARTMENT|GRADING|PAVING|HOLDINGS|GROUP|TRUST|VENTURES?)\b",
    re.I,
)
_AFTER_INST = re.compile(
    r"(?:CREDIT\s+UNION|DEFAULT\s+SERVICES?|LLC|INC\.?|LP|"
    r"CORP(?:ORATION)?|ASSOCIATION|TRUST)\s+(.+?)$", re.I,
)
_BEFORE_INST = re.compile(
    r"^(.+?)\s+(?:NATIONAL|FEDERAL|DEPARTMENT|DEFAULT)\b", re.I,
)


def _clean(name: str) -> str:
    words = name.split()
    half = len(words) // 2
    if half > 0 and words[:half] == words[half : half * 2]:
        return " ".join(words[:half])
    return name


def extract_name(borrower: str, lender: str = "") -> str:
    """Strip corporate noise from a NETR borrower field; return searchable name."""
    b = _clean((borrower or "").strip().upper())
    ldr = (lender or "").strip().upper()

    # Strategy 1: subtract lender tokens
    if ldr:
        ldr_toks = set(ldr.split())
        b_toks = b.split()
        filtered = [t for t in b_toks if t not in ldr_toks]
        if filtered and len(filtered) < len(b_toks):
            candidate = " ".join(filtered)
            if not _INST.search(candidate):
                return candidate
            b = candidate

    # Strategy 2: name after last institutional marker
    last_m = None
    for m in _AFTER_INST.finditer(b):
        last_m = m
    if last_m and last_m.group(1).strip():
        return _clean(last_m.group(1).strip())

    # Strategy 3: name before first institutional word
    m2 = _BEFORE_INST.search(b)
    if m2 and m2.group(1).strip():
        return _clean(m2.group(1).strip())

    return b


def is_corporate(name: str) -> bool:
    return bool(_INST.search((name or "").upper()))


# ── Coordinate helpers ─────────────────────────────────────────────────────────

def _centroid(rings: list) -> tuple[float, float] | tuple[None, None]:
    """Compute centroid (lat, lon) from ArcGIS polygon rings in WGS84."""
    if not rings:
        return None, None
    ring = rings[0]
    if not ring:
        return None, None
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    # Sanity check: CA bounding box
    if 32 <= lat <= 42 and -125 <= lon <= -114:
        return round(lat, 6), round(lon, 6)
    return None, None


# ── Riverside GIS helpers ──────────────────────────────────────────────────────

def _rv_query(where: str) -> list[dict]:
    params = {
        "where": where,
        "outFields": _RV_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": 5,
        "f": "json",
    }
    try:
        r = requests.get(_RV_URL, params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("features", [])
    except Exception as e:
        print(f"    Riverside API error: {e}", file=sys.stderr)
        return []


def _rv_parse(feat: dict) -> dict | None:
    """Extract address + coords from a Riverside ArcGIS feature."""
    a = feat.get("attributes", {})
    situs = (a.get("SITUS_STREET") or "").strip()
    if not situs:
        return None  # vacant lot or missing data

    city_full = (a.get("SITUS_CITY") or "").strip()
    # SITUS_CITY = "PERRIS  CA 92570" — extract just the city name
    city_m = re.match(r"^(.+?)\s+CA\b", city_full, re.I)
    city = city_m.group(1).strip() if city_m else city_full
    zip_ = (a.get("ZIP_CODE") or "").strip().split("-")[0]

    # Build full address
    address = situs  # SITUS_STREET already has house number
    if city:
        address = f"{situs}, {city}, CA {zip_}".strip(", ")

    # Centroid from polygon
    rings = (feat.get("geometry") or {}).get("rings", [])
    lat, lon = _centroid(rings)

    land  = float(a.get("LAND") or 0)
    struc = float(a.get("STRUCTURES") or 0)

    return {
        "Property Address": situs,
        "City": city,
        "ZIP": zip_,
        "Latitude": lat,
        "Longitude": lon,
        "Assessed Land($)": land if land else None,
        "Assessed Imp($)": struc if struc else None,
        "Assessed Total($)": (land + struc) if (land or struc) else None,
        "Match Score": 1.0 if "apn" in (a.get("APN") or "").lower() else 0.7,
        "_owner_found": a.get("PRIMARY_OWNER", ""),
    }


def lookup_rv_by_apn(apn: str) -> dict | None:
    time.sleep(API_PAUSE)
    clean_apn = re.sub(r"[^0-9]", "", str(apn or ""))
    feats = _rv_query(f"APN='{clean_apn}'")
    if not feats:
        return None
    result = _rv_parse(feats[0])
    if result:
        result["Match Score"] = 1.0
    return result


def lookup_rv_by_name(borrower: str, lender: str = "") -> dict | None:
    name = extract_name(borrower, lender)
    if not name or is_corporate(name) or len(name) < 4:
        return None

    tokens = [t.replace("'", "''") for t in name.split()[:2] if len(t) > 2]
    if not tokens:
        return None

    where = " AND ".join(f"UPPER(PRIMARY_OWNER) LIKE '%{t}%'" for t in tokens)
    time.sleep(API_PAUSE)
    feats = _rv_query(where)

    # Filter to residential / improved properties only
    residential = [
        f for f in feats
        if "residential" in (f.get("attributes", {}).get("CLASS_CODE") or "").lower()
        or float(f.get("attributes", {}).get("STRUCTURES") or 0) > 0
    ]
    target = residential[0] if residential else (feats[0] if feats else None)
    if not target:
        return None

    result = _rv_parse(target)
    if result:
        result["Match Score"] = 0.7 if len(residential) == 1 else 0.5
    return result


# ── LA County ─────────────────────────────────────────────────────────────────

def _get_la_lookup():
    """Lazy import of assessor_lookup from ~/NOD/ so this script is standalone."""
    import importlib.util, sys as _sys
    nod_dir = Path.home() / "NOD"
    spec = importlib.util.spec_from_file_location(
        "assessor_lookup", nod_dir / "assessor_lookup.py"
    )
    if spec is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["assessor_lookup"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Column map: result key → Excel column name ────────────────────────────────
_COL_MAP = {
    "Property Address": "Property Address",
    "City":             "City",
    "ZIP":              "ZIP",
    "Latitude":         "Latitude",
    "Longitude":        "Longitude",
    "Assessed Land($)": "Assessed Land($)",
    "Assessed Imp($)":  "Assessed Imp($)",
    "Assessed Total($)":"Assessed Total($)",
    "Match Score":      "Match Score",
}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Enrich NOD Master with missing addresses")
    parser.add_argument("--run",     action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--county",  default="all", help="Riverside | LA | all")
    parser.add_argument("--limit",   type=int, default=0, help="Max rows per county (0=all)")
    args = parser.parse_args()

    print(f"Loading {NOD_MASTER} …")
    try:
        df = pd.read_excel(NOD_MASTER, sheet_name="NOD Records", dtype=str)
    except ValueError:
        df = pd.read_excel(NOD_MASTER, sheet_name=0, dtype=str)
    print(f"  {len(df):,} records loaded")

    def blank(val):
        return pd.isna(val) or str(val).strip() in ("", "nan", "None", "NaN")

    missing = df[df["Property Address"].apply(blank)]
    print(f"  Missing address: {len(missing):,}")

    county_arg = args.county.lower()

    # ── Riverside ─────────────────────────────────────────────────────────────��
    if county_arg in ("all", "riverside"):
        rv_rows = missing[missing["County"].str.contains("Riverside", case=False, na=False)]
        rv_limit = args.limit or len(rv_rows)
        rv_apn  = rv_rows[rv_rows["APN"].apply(lambda v: not blank(v))].head(rv_limit)
        rv_name = rv_rows[rv_rows["APN"].apply(blank)].head(rv_limit)

        print(f"\nRiverside County:")
        print(f"  APN lookup:  {len(rv_apn):,} records")
        print(f"  Name lookup: {len(rv_name):,} records")

        if not args.run:
            pass  # dry run: just show counts
        else:
            rv_found = rv_skipped = 0
            lender_col = next((c for c in df.columns if "trustee" in c.lower()), None)

            # Phase A — APN lookup
            for i, (idx, row) in enumerate(rv_apn.iterrows(), 1):
                apn = str(row.get("APN", "")).strip()
                result = lookup_rv_by_apn(apn)
                if result and not blank(result.get("Property Address")):
                    for col, key in _COL_MAP.items():
                        if col in df.columns and result.get(key) is not None:
                            df.at[idx, col] = str(result[key])
                    rv_found += 1
                    if i % 20 == 0:
                        print(f"    APN [{i}/{len(rv_apn)}] ✓{rv_found} — {result['Property Address']}")
                else:
                    rv_skipped += 1

            # Phase B — name lookup
            for i, (idx, row) in enumerate(rv_name.iterrows(), 1):
                borrower = str(row.get("Borrower Name", "")).strip()
                lender   = str(row.get(lender_col, "")).strip() if lender_col else ""
                result   = lookup_rv_by_name(borrower, lender)
                if result and not blank(result.get("Property Address")):
                    for col, key in _COL_MAP.items():
                        if col in df.columns and result.get(key) is not None:
                            df.at[idx, col] = str(result[key])
                    rv_found += 1
                    if i % 25 == 0 or i <= 3:
                        pct = i / len(rv_name) * 100
                        print(f"    Name [{i}/{len(rv_name)}  {pct:.0f}%] "
                              f"✓{rv_found}  — {borrower[:35]} → {result['Property Address']}")
                else:
                    rv_skipped += 1

            print(f"  Riverside result: ✓{rv_found} found  ✗{rv_skipped} not found")

    # ── LA County ──────────────────────────────────────────────────────────────
    if county_arg in ("all", "la"):
        la_rows = missing[missing["County"].str.contains("LA County", case=False, na=False)]
        la_limit = args.limit or len(la_rows)
        la_rows = la_rows.head(la_limit)
        print(f"\nLA County:")
        print(f"  Name lookup: {len(la_rows):,} records")

        if not args.run:
            pass
        else:
            la_mod = _get_la_lookup()
            if la_mod is None:
                print("  SKIP — assessor_lookup.py not found in ~/NOD/")
            else:
                la_found = la_skipped = 0
                lender_col = next((c for c in df.columns if "trustee" in c.lower()), None)

                for i, (idx, row) in enumerate(la_rows.iterrows(), 1):
                    borrower = str(row.get("Borrower Name", "")).strip()
                    lender   = str(row.get(lender_col, "")).strip() if lender_col else ""
                    name     = extract_name(borrower, lender)
                    if not name or is_corporate(name):
                        la_skipped += 1
                        continue

                    result = la_mod.lookup_by_name(name)
                    if result and not blank(result.get("property_address")):
                        la_map = {
                            "Property Address": result.get("property_address"),
                            "City":             result.get("situs_city"),
                            "ZIP":              result.get("situs_zip"),
                            "Latitude":         result.get("latitude"),
                            "Longitude":        result.get("longitude"),
                            "Assessed Land($)": result.get("assessed_land"),
                            "Assessed Imp($)":  result.get("assessed_imp"),
                            "Assessed Total($)":result.get("assessed_total"),
                            "Match Score":      result.get("match_score"),
                        }
                        for col, val in la_map.items():
                            if col in df.columns and val not in (None, ""):
                                df.at[idx, col] = str(val)
                        la_found += 1
                        if i % 20 == 0 or i <= 3:
                            print(f"    LA [{i}/{len(la_rows)}] ✓{la_found} — {borrower[:35]}")
                    else:
                        la_skipped += 1

                print(f"  LA result: ✓{la_found} found  ✗{la_skipped} not found")

    # ── Summary ────────────────────────────────────────────────────────────────
    if not args.run:
        total_addressable = len(missing[
            missing["County"].str.contains("Riverside|LA County", case=False, na=False)
        ])
        print(f"\nDry run complete.")
        print(f"  Records this script can attempt: ~{total_addressable:,}")
        print(f"  Expected yield: ~40–70% match rate = ~{int(total_addressable*0.55):,} new addresses")
        print(f"\nRun with --run to start enrichment:")
        print(f"  python enrich_addresses.py --run --county Riverside   # fastest, ~10 min")
        print(f"  python enrich_addresses.py --run                       # all counties, ~20 min")
        print(f"\nAfter enrichment, geocode any new addresses:")
        print(f"  python geocode.py --run")
        return

    # Save
    addr_after = df["Property Address"].apply(lambda v: not blank(v)).sum()
    print(f"\nTotal addressable records after enrichment: {addr_after:,} / {len(df):,}")

    backup = NOD_MASTER.with_name(NOD_MASTER.stem + "_pre_enrich.xlsx")
    import shutil
    shutil.copy2(NOD_MASTER, backup)
    print(f"Backed up to: {backup.name}")

    xl = pd.ExcelFile(NOD_MASTER)
    all_sheets = {s: xl.parse(s, dtype=str).fillna("") for s in xl.sheet_names}
    xl.close()
    all_sheets[xl.sheet_names[0]] = df
    with pd.ExcelWriter(NOD_MASTER, engine="openpyxl") as writer:
        for sname, sdf in all_sheets.items():
            sdf.to_excel(writer, sheet_name=sname, index=False)

    print(f"Saved → {NOD_MASTER}")
    print(f"\nNext: python geocode.py --run   (geocode the newly added addresses)")


if __name__ == "__main__":
    main()
