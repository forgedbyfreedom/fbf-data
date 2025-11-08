#!/usr/bin/env bash
set -euo pipefail

SRC_BASE="/Users/weero/fbf_fetcher"
DEST_BASE="/Users/weero/Documents/fbf-data"

cd "$DEST_BASE"

# Always keep your combined feed current
if [ -f "$SRC_BASE/combined_20251107_1044.json" ]; then
  cp "$SRC_BASE/combined_20251107_1044.json" "$DEST_BASE/combined.json"
elif [ -f "$SRC_BASE/latest.json" ]; then
  cp "$SRC_BASE/latest.json" "$DEST_BASE/combined.json"
fi

# OPTIONAL: once you start generating per-sport files, uncomment these
# cp "$SRC_BASE/nfl_latest.json" "$DEST_BASE/nfl.json"
# cp "$SRC_BASE/ncaaf_latest.json" "$DEST_BASE/ncaaf.json"
# cp "$SRC_BASE/nba_latest.json" "$DEST_BASE/nba.json"
# cp "$SRC_BASE/nhl_latest.json" "$DEST_BASE/nhl.json"
# cp "$SRC_BASE/mlb_latest.json" "$DEST_BASE/mlb.json"
# cp "$SRC_BASE/ncaam_latest.json" "$DEST_BASE/ncaam.json"
# cp "$SRC_BASE/ncaaw_latest.json" "$DEST_BASE/ncaaw.json"
# cp "$SRC_BASE/ncaa_baseball_latest.json" "$DEST_BASE/ncaa_baseball.json"
# cp "$SRC_BASE/ncaa_softball_latest.json" "$DEST_BASE/ncaa_softball.json"
# cp "$SRC_BASE/olympics_latest.json" "$DEST_BASE/olympics.json"
# cp "$SRC_BASE/ufc_latest.json" "$DEST_BASE/ufc.json"

# Commit and push if any files changed
if ! git diff --quiet; then
  git add .
  git commit -m "auto update $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
fi

