#!/usr/bin/env bash
set -euo pipefail

# === Base paths ===
SRC_BASE="/Users/weero/fbf_fetcher"
DEST_BASE="/Users/weero/Documents/fbf-data"

cd "$DEST_BASE"

# --- Copy the combined file (all sports) ---
if [ -f "$SRC_BASE/combined_20251107_1044.json" ]; then
  cp "$SRC_BASE/combined_20251107_1044.json" "$DEST_BASE/combined.json"
fi

# --- Individual sport files (optional, will skip if not found) ---
declare -a FILES=("nfl" "ncaaf" "nba" "ncaam" "ncaaw" "nhl" "mlb" "ncaa_baseball" "ncaa_softball" "ufc" "olympics")

for f in "${FILES[@]}"; do
  SRC_FILE="$SRC_BASE/${f}_latest.json"
  DEST_FILE="$DEST_BASE/${f}.json"
  if [ -f "$SRC_FILE" ]; then
    cp "$SRC_FILE" "$DEST_FILE"
  fi
done

# --- New metadata / enrichment layer ---
# These are optional JSONs that you’ll add soon (see Step 2 below)
declare -a META=("weather" "referees" "injuries" "ownership" "power_ratings")
for m in "${META[@]}"; do
  SRC_META="$SRC_BASE/${m}.json"
  DEST_META="$DEST_BASE/${m}.json"
  if [ -f "$SRC_META" ]; then
    cp "$SRC_META" "$DEST_META"
  fi
done

# --- Commit and push if any files changed ---
if ! git diff --quiet; then
  git add .
  git commit -m "auto update $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
fi

