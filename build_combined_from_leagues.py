#!/usr/bin/env python3
"""
build_combined_from_leagues.py

Rebuilds combined.json from league json files produced by fetch_espn_all.py.
Ensures final per-game format matches UI:

{
  "sport_key": "americanfootball_nfl",
  "matchup": "Away@Home",
  "home_team": "...",
  "away_team": "...",
  "favorite": "Home Team -2.5",
  "underdog": "Away Team +2.5",
  "fav_team": "...",
  "dog_team": "...",
  "fav_spread": -2.5,
  "dog_spread":  2.5,
  "spread": -2.5,
  "total": 47.5,
  "commence_time": "...",
  "book": "espn",
  "fetched_at": "..."
}

Rules:
- Negative spread = favorite.
- If spreads missing, set both to 0.0 and favorite defaults to home (if known).
"""

import json, os
from datetime import datetime, timezone

LEAGUE_FILES = [
    "nfl.json",
    "ncaaf.json",
    "nba.json",
    "ncaab.json",
    "ncaaw.json",
    "mlb.json",
    "nhl.json",
    "mixedmartialarts.json",
]

SPORT_KEY_MAP = {
    "nfl":  "americanfootball_nfl",
    "ncaaf":"americanfootball_ncaaf",
    "nba":  "basketball_nba",
    "ncaab":"basketball_ncaab",
    "ncaaw":"basketball_ncaaw",
    "mlb":  "baseball_mlb",
    "nhl":  "icehockey_nhl",
    "ufc":  "mma_mixed_martial_arts",
    "mixedmartialarts":"mma_mixed_martial_arts",
}

def safe_float(x):
    try:
        if x is None: return None
        return float(x)
    except Exception:
        return None

def normalize_sport_key(k: str) -> str:
    if not k: return "unknown"
    if k in SPORT_KEY_MAP: return SPORT_KEY_MAP[k]
    if "_" in k and k.startswith(("americanfootball_", "basketball_", "baseball_", "icehockey_", "mma_")):
        return k
    return SPORT_KEY_MAP.get(k.lower(), k.lower())

def derive_from_lines(lines):
    """
    lines = [{"team":name, "spread":-2.5}, {"team":name, "spread":2.5}]
    Return fav_team,dog_team,fav_spread,dog_spread
    """
    if not lines or len(lines) < 2:
        return None

    # keep only numeric spreads
    numeric = []
    for ln in lines:
        sp = safe_float(ln.get("spread"))
        nm = ln.get("team")
        if nm is not None and sp is not None:
            numeric.append((nm, sp))

    if len(numeric) < 2:
        return None

    # favorite: most negative spread (or smallest number)
    numeric_sorted = sorted(numeric, key=lambda x: x[1])
    fav_team, fav_spread = numeric_sorted[0]
    dog_team, dog_spread = numeric_sorted[1]

    # Make dog_spread opposite if ESPN gave both same sign
    if fav_spread is not None and dog_spread is not None and fav_spread * dog_spread > 0:
        dog_spread = -fav_spread

    return fav_team, dog_team, fav_spread, dog_spread

def normalize_event(ev, league_fallback_key):
    # sport key
    sport_key_raw = ev.get("sport_key") or league_fallback_key
    sport_key = normalize_sport_key(sport_key_raw)

    home_team = ev.get("home_team")
    away_team = ev.get("away_team")

    matchup = ev.get("matchup")
    commence_time = ev.get("commence_time") or ev.get("date")

    total = safe_float(ev.get("total"))

    fetched_at = ev.get("fetched_at") or datetime.now(timezone.utc).isoformat()
    book = (ev.get("book") or "ESPN").lower()

    # If already in final format, keep it
    if ev.get("fav_team") and ev.get("dog_team") and ev.get("fav_spread") is not None:
        fav_team = ev["fav_team"]
        dog_team = ev["dog_team"]
        fav_spread = safe_float(ev.get("fav_spread")) or 0.0
        dog_spread = safe_float(ev.get("dog_spread")) or -fav_spread
    else:
        # Derive from "lines" if present
        derived = derive_from_lines(ev.get("lines"))
        if derived:
            fav_team, dog_team, fav_spread, dog_spread = derived
        else:
            # fallback: if we have spread fields
            fav_team = ev.get("favorite_team") or ev.get("fav_team")
            dog_team = ev.get("dog_team") or ev.get("underdog_team")
            fav_spread = safe_float(ev.get("fav_spread")) or safe_float(ev.get("spread"))
            dog_spread = safe_float(ev.get("dog_spread"))

    # Final fallback if still missing
    if fav_spread is None:
        fav_spread = 0.0
    if dog_spread is None:
        dog_spread = -fav_spread

    # If fav/dog teams still missing, infer from home/away
    if not fav_team or not dog_team:
        if home_team and away_team:
            # if spread negative for home -> home favorite else away favorite
            if fav_spread < 0:
                fav_team, dog_team = home_team, away_team
            elif fav_spread > 0:
                fav_team, dog_team = away_team, home_team
            else:
                fav_team, dog_team = home_team, away_team
        else:
            # last resort from matchup string
            if matchup and "@" in matchup:
                away_team_tmp, home_team_tmp = matchup.split("@", 1)
                away_team_tmp, home_team_tmp = away_team_tmp.strip(), home_team_tmp.strip()
                home_team = home_team or home_team_tmp
                away_team = away_team or away_team_tmp
                fav_team, dog_team = home_team, away_team
            else:
                fav_team = fav_team or "Unknown"
                dog_team = dog_team or "Unknown"

    # Ensure home/away if missing
    if not home_team or not away_team:
        if matchup and "@" in matchup:
            aw, hm = matchup.split("@", 1)
            away_team = away_team or aw.strip()
            home_team = home_team or hm.strip()

    spread = fav_spread  # canonical negative spread

    favorite_str = f"{fav_team} {fav_spread:+.1f}".replace("+", "+").replace("-0.0", "-0.0")
    underdog_str = f"{dog_team} {abs(dog_spread):+.1f}".replace("+", "+").replace("+0.0", "+0.0")
    # dog_spread should be positive for display
    if dog_spread < 0:
        underdog_str = f"{dog_team} {abs(dog_spread):+.1f}"

    return {
        "sport_key": sport_key,
        "matchup": matchup or (f"{away_team}@{home_team}" if away_team and home_team else f"{fav_team}@{dog_team}"),
        "home_team": home_team,
        "away_team": away_team,

        "favorite": favorite_str,
        "underdog": underdog_str,

        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": spread,

        "total": total,
        "commence_time": commence_time,
        "book": book,
        "fetched_at": fetched_at,
    }

def main():
    combined = []
    errors = {}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    for lf in LEAGUE_FILES:
        if not os.path.exists(lf):
            continue
        try:
            with open(lf, "r", encoding="utf-8") as f:
                payload = json.load(f)
            data = payload.get("data") or payload.get("events") or []
            league_key = os.path.splitext(lf)[0].lower()

            for ev in data:
                norm = normalize_event(ev, league_key)
                if norm:
                    combined.append(norm)

        except Exception as e:
            errors[lf] = str(e)

    out = {
        "timestamp": timestamp,
        "source": "ESPN_ODDS_API",
        "data": combined,
        "errors": errors or None,
    }

    with open("combined.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"[✅] Rebuilt combined.json with {len(combined)} events @ {timestamp}")

if __name__ == "__main__":
    main()
