#!/usr/bin/env python3
"""
export_snapshot.py
==================
Merges NOD Master + RETRAN data and exports to Parquet for deployment.
Run this locally after scraping/enrichment runs, then commit + push.

Usage:
    python scripts/export_snapshot.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.loader import load_df
import pandas as pd
from pathlib import Path

OUT = Path(__file__).parent.parent / "assets" / "data" / "nod_master.parquet"

def main():
    print("Loading merged dataset (NOD Master + RETRAN)…")
    df = load_df()
    print(f"  {len(df):,} records")
    print(f"  Geocoded: {df[['Latitude','Longitude']].dropna().shape[0]:,}")
    print(f"  With sale date: {df['Sale Date'].notna().sum() if 'Sale Date' in df.columns else 0:,}")

    print(f"\nExporting to {OUT}…")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # Convert mixed-type object columns to clean strings
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).replace("nan", "")

    # Low-cardinality columns → Categorical (smaller file, faster filtering)
    for col in ["County", "Stage", "Document Type", "Hard Money Loan?",
                "Corporate Grantor?", "Owner-Occupied?", "Source",
                "Use Type", "Use Description"]:
        if col in df.columns:
            df[col] = df[col].astype("category")

    # Simple data quality check before writing
    assert len(df) > 10_000, f"Suspiciously few records: {len(df)}"
    assert df["Stage"].notna().sum() > 0, "Stage column is empty"
    geocoded = df[["Latitude", "Longitude"]].apply(pd.to_numeric, errors="coerce").dropna().shape[0]
    assert geocoded > 1_000, f"Too few geocoded records: {geocoded}"

    df.to_parquet(OUT, index=False, compression="zstd")
    size_kb = OUT.stat().st_size / 1024
    print(f"  Written: {size_kb:.0f} KB  (was 750 KB before Categorical schema)")
    print(f"  Validation passed: {len(df):,} records, {geocoded:,} geocoded")
    print("\nDone. Commit assets/data/nod_master.parquet and push to GitHub.")

if __name__ == "__main__":
    main()
