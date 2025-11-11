#!/usr/bin/env python3
"""
fix_combined_from_league_files.py

Rebuilds explicit per-team spreads in combined.json by reading league files.
Outputs:
  - away_team, home_team
  - away_spread, home_spread
  - away_ml, home_ml (if available)

Adjust LEAGUE_FILES mapping if your filenames differ.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

ROOT = Path(".")  # run inside ~/Documents/fbf-data
COMBINED = ROOT / "combined.json"
BACKUP = ROOT / "combined_backup_before_fix.json"

# Map sport_key to its league file. Adjust names here if needed.
LEAGUE_FILES: Dict[str, Path] = {
    "americanfootball_nfl": ROOT / "nfl.json",
    "americanfootball_ncaaf": ROOT / "ncaaf.json",
    "icehockey_nhl": ROOT / "nhl.json",
    "baseball_mlb": ROOT / "mlb.json",
    "basketball_ncaab": ROOT / "ncaab.json",
    "basketball_ncaaw": ROOT / "ncaaw.json",
    "mma_mixedmartialarts": ROOT / "ufc.json",
}

def load_json_maybe(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return None

def parse_matchup(s: str) -> Tuple[str, str]:
    parts = (s or "").split("@")
    away = parts[0].strip() if len(parts) > 0 else ""
    home = parts[1].strip() if len(parts) > 1 else ""
    return away, home

def normalize_team_name(name: str) -> str:
    return " ".join(name.replace(".", "").replace("-", " ").split()).lower()

def extract_per_team_lines_from_league(
    league_blob: Any, away: str, home: str
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Returns away_spread, home_spread, away_ml, home_ml by matching the event
    in the league file and reading its markets.
    Supports a few common shapes; mirror if only one side is present.
    """
    if league_blob is None:
        return None, None, None, None

    events = league_blob.get("data") if isinstance(league_blob, dict) else league_blob
    if not isinstance(events, list):
        return None, None, None, None

    ta = normalize_team_name(away)
    th = normalize_team_name(home)

    match = None
    for ev in events:
        m = ev.get("matchup") or f'{ev.get("away_team","")}@{ev.get("home_team","")}'
        a, h = parse_matchup(m)
        if normalize_team_name(a) == ta and normalize_team_name(h) == th:
            match = ev
            break
    if match is None:
        return None, None, None, None

    away_spread = None
    home_spread = None
    away_ml = None
    home_ml = None

    markets = match.get("markets") or {}

    # ---- spreads ----
    spread_lists = []
    for k in ("spreads", "spread", "point_spread"):
        if isinstance(markets.get(k), list):
            spread_lists.extend(markets[k])
    if not spread_lists:
        for v in markets.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and ("point" in v[0] or "handicap" in v[0]):
                spread_lists.extend(v)

    def get_point(d: Dict[str, Any]) -> Optional[float]:
        if "point" in d and isinstance(d["point"], (int, float)):
            return float(d["point"])
        if "handicap" in d and isinstance(d["handicap"], (int, float)):
            return float(d["handicap"])
        return None

    for o in spread_lists:
        nm = normalize_team_name(o.get("name",""))
        pt = get_point(o)
        if pt is None:
            continue
        if nm == ta:
            away_spread = pt
        elif nm == th:
            home_spread = pt

    if away_spread is not None and home_spread is None:
        home_spread = -away_spread
    if home_spread is not None and away_spread is None:
        away_spread = -home_spread

    # ---- moneyline ----
    ml_lists = []
    for k in ("h2h", "moneyline", "ml"):
        if isinstance(markets.get(k), list):
            ml_lists.extend(markets[k])
    if not ml_lists:
        for v in markets.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and ("price" in v[0] or "odds" in v[0]):
                ml_lists.extend(v)

    def get_price(d: Dict[str, Any]) -> Optional[float]:
        if "price" in d and isinstance(d["price"], (int, float)):
            return float(d["price"])
        if "odds" in d and isinstance(d["odds"], (int, float)):
            return float(d["odds"])
        return None

    for o in ml_lists:
        nm = normalize_team_name(o.get("name",""))
        pr = get_price(o)
        if pr is None:
            continue
        if nm == ta:
            away_ml = pr
        elif nm == th:
            home_ml = pr

    return away_spread, home_spread, away_ml, home_ml

def main():
    if not COMBINED.exists():
        raise SystemExit(f"combined.json not found in {COMBINED.parent}")

    BACKUP.write_bytes(COMBINED.read_bytes())
    print(f"Backup → {BACKUP}")

    with COMBINED.open("r", encoding="utf-8") as f:
        root = json.load(f)

    data = root.get("data") if isinstance(root, dict) else root
    if not isinstance(data, list):
        raise SystemExit("combined.json must be a list or {data:[...]}")

    leagues = {k: load_json_maybe(p) for k, p in LEAGUE_FILES.items()}

    fixed = []
    missing = 0

    for row in data:
        r = dict(row)
        sport = r.get("sport_key","")
        matchup = r.get("matchup","")
        away, home = parse_matchup(matchup)

        r["away_team"] = away or r.get("away_team","")
        r["home_team"] = home or r.get("home_team","")

        a_spread, h_spread, a_ml, h_ml = extract_per_team_lines_from_league(
            leagues.get(sport), r["away_team"], r["home_team"]
        )

        if a_spread is not None or h_spread is not None:
            r["away_spread"] = a_spread
            r["home_spread"] = h_spread
        else:
            sp = r.get("spread", None)
            if isinstance(sp, (int,float)):
                r["away_spread"] = float(sp)
                r["home_spread"] = -float(sp)
                r["_note"] = "fallback_from_single_spread"
            else:
                r["away_spread"] = None
                r["home_spread"] = None
                r["_note"] = "no_spread_found"
                missing += 1

        if a_ml is not None: r["away_ml"] = a_ml
        if h_ml is not None: r["home_ml"] = h_ml

        fixed.append(r)

    if isinstance(root, dict):
        root["data"] = fixed
    else:
        root = fixed

    COMBINED.write_text(json.dumps(root, indent=2), encoding="utf-8")
    print(f"Updated {len(fixed)} rows in {COMBINED}")
    if missing:
        print(f"WARNING: {missing} rows without per-team spreads in league files: {missing}")

if __name__ == "__main__":
    main()

