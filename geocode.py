"""
Geocode missing addresses in SoCal_NOD_Master.xlsx using the US Census Geocoder.

The Census batch geocoder is completely free — no API key, no account needed.
Batch limit: 10,000 records per request.

Usage:
    python geocode.py                # dry run, shows stats
    python geocode.py --run          # geocodes and saves results
    python geocode.py --run --limit 1000   # geocode first 1000 missing records
"""

import argparse
import io
import os
import sys
import time

import pandas as pd
import requests

NOD_MASTER = os.path.join(os.path.dirname(__file__), "..", "NOD_Data", "SoCal_NOD_Master.xlsx")
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 9_000  # stay under 10,000 limit with some headroom


def prepare_batch(df_missing: pd.DataFrame) -> pd.DataFrame:
    """Build a Census-compatible address CSV (ID, Street, City, State, ZIP)."""
    batch = pd.DataFrame({
        "id": df_missing.index,
        "street": df_missing["Property Address"].fillna(""),
        "city": df_missing["City"].fillna(""),
        "state": "CA",
        "zip": df_missing["ZIP"].fillna("").astype(str).str.split(".").str[0],
    })
    # Drop rows with no street address
    batch = batch[batch["street"].str.strip() != ""]
    return batch


def call_census_batch(batch_df: pd.DataFrame) -> pd.DataFrame:
    """Submit one batch to the Census geocoder and return a results DataFrame."""
    csv_buffer = io.StringIO()
    batch_df.to_csv(csv_buffer, index=False, header=False)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    resp = requests.post(
        CENSUS_URL,
        files={"addressFile": ("batch.csv", csv_bytes, "text/csv")},
        data={"benchmark": "Public_AR_Current", "vintage": "Current_Current"},
        timeout=120,
    )
    resp.raise_for_status()

    # Census returns CSV with columns:
    # id, input_address, match_status, match_type, output_address, coords, tiger_id, side
    results = pd.read_csv(
        io.StringIO(resp.text),
        header=None,
        names=["id", "input_address", "match_status", "match_type",
               "output_address", "coords", "tiger_id", "side"],
        dtype={"id": str},
    )
    return results


def parse_coords(results: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """Extract {original_index: (lat, lon)} from Census results."""
    coord_map = {}
    matched = results[results["match_status"].str.upper() == "MATCH"]
    for _, row in matched.iterrows():
        try:
            idx = int(row["id"])
            lon_str, lat_str = str(row["coords"]).split(",")
            coord_map[idx] = (float(lat_str.strip()), float(lon_str.strip()))
        except (ValueError, AttributeError):
            continue
    return coord_map


def geocode_all(df: pd.DataFrame, limit: int | None = None) -> dict[int, tuple[float, float]]:
    """Geocode all rows missing lat/lon. Returns index → (lat, lon)."""
    missing = df[df["Latitude"].isna() & df["Property Address"].notna()].copy()
    if limit:
        missing = missing.head(limit)

    total_missing = len(missing)
    print(f"Records to geocode: {total_missing:,}")

    all_coords: dict[int, tuple[float, float]] = {}
    batches = range(0, total_missing, BATCH_SIZE)

    for i, start in enumerate(batches):
        chunk = missing.iloc[start : start + BATCH_SIZE]
        batch_df = prepare_batch(chunk)
        addressable = len(batch_df)
        print(f"  Batch {i+1}/{len(batches) + 1}: submitting {addressable:,} addresses...", end=" ", flush=True)

        try:
            results = call_census_batch(batch_df)
            coords = parse_coords(results)
            matched_count = len(coords)
            print(f"matched {matched_count:,} ({matched_count/addressable*100:.0f}%)")
            all_coords.update(coords)
        except Exception as exc:
            print(f"ERROR: {exc}")

        if start + BATCH_SIZE < total_missing:
            time.sleep(1)  # be polite to the Census server

    return all_coords


def main():
    parser = argparse.ArgumentParser(description="Geocode missing addresses via US Census Geocoder")
    parser.add_argument("--run", action="store_true", help="Actually geocode and save (default: dry run)")
    parser.add_argument("--limit", type=int, default=None, help="Max records to geocode")
    args = parser.parse_args()

    print(f"Loading {NOD_MASTER}...")
    df = pd.read_excel(NOD_MASTER)
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

    total = len(df)
    has_coords = df[["Latitude", "Longitude"]].dropna().shape[0]
    missing_coords = total - has_coords
    has_address = df["Property Address"].notna().sum()

    print(f"\nDataset summary:")
    print(f"  Total records:        {total:,}")
    print(f"  Already geocoded:     {has_coords:,} ({has_coords/total*100:.1f}%)")
    print(f"  Missing coordinates:  {missing_coords:,}")
    print(f"  Have street address:  {has_address:,}")
    print(f"  Geocodable (missing coords + has address): {df[df['Latitude'].isna() & df['Property Address'].notna()].shape[0]:,}")

    if not args.run:
        print("\nDry run — use --run to geocode and save.")
        print("Estimated time: ~2 batches × 30 seconds = ~1 minute for all missing records.")
        sys.exit(0)

    print("\nStarting geocoding...")
    coord_map = geocode_all(df, limit=args.limit)
    print(f"\nTotal matched: {len(coord_map):,}")

    # Apply results back to the DataFrame
    newly_geocoded = 0
    for idx, (lat, lon) in coord_map.items():
        if pd.isna(df.at[idx, "Latitude"]):
            df.at[idx, "Latitude"] = lat
            df.at[idx, "Longitude"] = lon
            newly_geocoded += 1

    print(f"Newly geocoded: {newly_geocoded:,}")
    print(f"Total geocoded after update: {df[['Latitude','Longitude']].dropna().shape[0]:,} / {total:,}")

    # Save back
    backup_path = NOD_MASTER.replace(".xlsx", "_backup.xlsx")
    import shutil
    shutil.copy2(NOD_MASTER, backup_path)
    print(f"Backed up original to: {backup_path}")

    df.to_excel(NOD_MASTER, index=False)
    print(f"Saved updated data to: {NOD_MASTER}")


if __name__ == "__main__":
    main()
