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
    # Convert mixed-type object columns to string so Parquet accepts them
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).replace("nan", "")
    df.to_parquet(OUT, index=False, compression="zstd")
    size_kb = OUT.stat().st_size / 1024
    print(f"  Written: {size_kb:.0f} KB")
    print("\nDone. Commit assets/data/nod_master.parquet and push to GitHub.")

if __name__ == "__main__":
    main()
