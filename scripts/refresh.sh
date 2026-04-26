#!/bin/bash
# refresh.sh — Refresh DistressedCA website data and deploy
#
# Runs after the NOD scraper pipeline completes. Enriches new records,
# geocodes addresses, exports a Parquet snapshot, and pushes to GitHub
# so Render auto-deploys the updated site.
#
# Crontab (runs Mon-Fri at 8 AM, after scrapers finish at ~7:30):
#   0 8 * * 1-5 /home/highview/DistressedCA/scripts/refresh.sh >> /home/highview/DistressedCA/logs/refresh.log 2>&1

set -uo pipefail

DISTRESSED_DIR="$HOME/DistressedCA"
LOG_DIR="$DISTRESSED_DIR/logs"
PYTHON="python3"

mkdir -p "$LOG_DIR"

echo ""
echo "============================================================"
echo "DistressedCA Refresh — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

cd "$DISTRESSED_DIR"

# ── Skip weekends ─────────────────────────────────────────────────────────────
DOW=$(date +%u)
if [[ "$DOW" -ge 6 && "${FORCE:-0}" != "1" ]]; then
    echo "Skipping — weekend."
    exit 0
fi

# ── Helper ────────────────────────────────────────────────────────────────────
run_step() {
    local label="$1"; shift
    echo ""
    echo "── $label ──────────────────────────────"
    echo "   $(date '+%H:%M:%S')"
    if "$@"; then
        echo "   ✓ done"
        return 0
    else
        echo "   ✗ FAILED (exit $?)"
        return 1
    fi
}

ERRORS=0

# ── Step 1: Enrich new addresses (Riverside + LA County) ─────────────────────
run_step "Address enrichment" \
    $PYTHON "$DISTRESSED_DIR/enrich_addresses.py" --run \
    || ERRORS=$((ERRORS + 1))

# ── Step 2: Geocode any new addresses via Census Geocoder ─────────────────────
run_step "Geocoding" \
    $PYTHON "$DISTRESSED_DIR/geocode.py" --run \
    || ERRORS=$((ERRORS + 1))

# ── Step 3: Export merged Parquet snapshot ───────────────────────────────────
run_step "Export Parquet snapshot" \
    $PYTHON "$DISTRESSED_DIR/scripts/export_snapshot.py" \
    || { echo "   Export failed — aborting deploy"; exit 1; }

# ── Step 4: Commit and push if snapshot changed ──────────────────────────────
echo ""
echo "── Git push ─────────────────────────────"
echo "   $(date '+%H:%M:%S')"

cd "$DISTRESSED_DIR"
git add assets/data/nod_master.parquet

if git diff --cached --quiet; then
    echo "   No data change — skipping commit"
else
    DATE=$(date '+%Y-%m-%d')
    RECORDS=$($PYTHON -c "
import pandas as pd
df = pd.read_parquet('assets/data/nod_master.parquet')
geocoded = df[['Latitude','Longitude']].dropna().shape[0]
print(f'{len(df):,} records, {geocoded:,} geocoded')
" 2>/dev/null || echo "?")
    git commit -m "Data refresh $DATE — $RECORDS"
    git push
    echo "   ✓ Pushed — Render will auto-deploy"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
if [[ $ERRORS -gt 0 ]]; then
    echo "Completed with $ERRORS non-fatal error(s) — check logs above"
else
    echo "Completed successfully"
fi
echo "Log: $LOG_DIR/refresh.log"
echo "============================================================"
