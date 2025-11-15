#!/usr/bin/env python3
"""
fetch_odds_api.py

Unified odds-fetcher for "major" events only, using The Odds API.

Sports included:
  - americanfootball_nfl
  - americanfootball_ncaaf
  - basketball_nba
  - basketball_ncaab
  - icehockey_nhl
  - mma_mixed_martial_arts (UFC events only)

Output:
  combined.json

Schema (per game record):
  {
    "sport_key": str,
    "matchup": "Away Team@Home Team",
    "home_team": str,
    "away_team": str,
    "favorite": "Team -6.5" or "Team +3.5",
    "underdog": "Team +6.5" or "Team -3.5",
    "fav_team": str or null,
    "dog_team": str or null,
    "fav_spread": float or null,
    "dog_spread": float or null,
    "spread": float or null,
    "total": float or null,
    "commence_time": ISO8601 string,
    "book": bookmaker_key,
    "fetched_at": ISO8601 string (UTC),
    "fav_price": int,
    "dog_price": int
  }
"""

import os
import sys
import json
import datetime
from typing import Any, Dict, List, Optional

import requests


# The Odds API (official endpoint)
API_BASE = "https://api.the-odds-api.com/v4/sports"

# Only major sports
SPORTS = [
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "icehockey_nhl",
    "mma_mixed_martial_arts",
]

# Priority list of books
PREFERRED_BOOKMAKERS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "pointsbetus",
    "betonlineag",
    "bovada",
]


def utc_now() -> datetime.datetime:
    """Timezone-aware UTC now."""
    return datetime.datetime.now(datetime.timezone.utc)


def format_spread_value(val: float) -> str:
    """Format -6.5 → '-6.5', +3 → '+3', 0 → PK."""
    if val == 0 or abs(val) < 1e-6:
        return "PK"
    if val > 0:
        return f"+{val:g}"
    return f"{val:g}"


def get_env_api_key() -> str:
    key = os.getenv("ODDS_API_KEY")
    if not key:
        print(
            "[❌] ODDS_API_KEY is not set.\n"
            '    Run: export ODDS_API_KEY="your_real_key_here"\n'
        )
        sys.exit(1)
    return key


def fetch_sport(sport_key: str, api_key: str) -> List[Dict[str, Any]]:
    """Fetch raw events for a single sport."""
    print(f"[⏱️] Fetching {sport_key} ...")

    url = f"{API_BASE}/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
    except Exception as e:
        print(f"    ❌ Error fetching {sport_key}: {e}")
        return []

    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get("message", resp.text)
        except:
            msg = resp.text
        print(f"    ❌ API error for {sport_key}: {resp.status_code} — {msg}")
        return []

    try:
        events = resp.json()
    except Exception as e:
        print(f"    ❌ JSON parse error for {sport_key}: {e}")
        return []

    if not isinstance(events, list):
        print(f"    ❌ Unexpected response for {sport_key}")
        return []

    print(f"    → {sport_key}: {len(events)} events")
    remaining = resp.headers.get("x-requests-remaining")
    if remaining:
        print(f"    ↪ Requests remaining: {remaining}")

    return events


def choose_bookmaker(bookmakers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick the best bookmaker."""
    if not bookmakers:
        return None

    # First: preferred list
    key_map = {b.get("key"): b for b in bookmakers}
    for pref in PREFERRED_BOOKMAKERS:
        if pref in key_map:
            return key_map[pref]

    # Otherwise: latest update
    try:
        return max(bookmakers, key=lambda b: b.get("last_update", ""))
    except:
        return bookmakers[0]


def get_market(bookmaker: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """Return the first matching market."""
    for m in bookmaker.get("markets", []):
        if m.get("key") == key:
            return m
    return None


def parse_spreads(market: Optional[Dict[str, Any]]):
    """Return fav_team, dog_team, fav_spread, dog_spread, spread."""
    if not market:
        return None, None, None, None, None

    outcomes = market.get("outcomes", []) or []
    valid = [
        o for o in outcomes
        if isinstance(o, dict) and isinstance(o.get("point"), (int, float))
    ]
    if len(valid) < 2:
        return None, None, None, None, None

    fav = min(valid, key=lambda x: x["point"])
    dog = max(valid, key=lambda x: x["point"])

    fav_team = fav.get("name")
    dog_team = dog.get("name")
    fav_spread = float(fav.get("point"))
    dog_spread = float(dog.get("point"))
    return fav_team, dog_team, fav_spread, dog_spread, fav_spread


def parse_h2h_prices(market: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    prices = {}
    if market:
        for o in market.get("outcomes", []):
            prices[o.get("name")] = o.get("price")
    return prices


def pick_favorite_from_h2h(prices: Dict[str, Optional[int]]):
    """Pick favorite based on most negative moneyline."""
    valid = [(t, p) for t, p in prices.items() if isinstance(p, (int, float))]
    if len(valid) < 2:
        return None, None
    fav_team, _ = min(valid, key=lambda x: x[1])
    dog_team = next(t for t, _ in valid if t != fav_team)
    return fav_team, dog_team


def build_game_record(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert API event to our schema."""
    sport_key = event.get("sport_key")
    home_team = event.get("home_team")
    away_team = event.get("away_team")
    commence_time = event.get("commence_time")

    if not all([home_team, away_team, commence_time]):
        return None

    bookmaker = choose_bookmaker(event.get("bookmakers", []))
    if not bookmaker:
        return None

    spreads = get_market(bookmaker, "spreads")
    totals = get_market(bookmaker, "totals")
    h2h = get_market(bookmaker, "h2h")

    # Try spreads first
    fav_team, dog_team, fav_spread, dog_spread, spread = parse_spreads(spreads)

    # If still missing, fallback to h2h moneyline
    h2h_prices = parse_h2h_prices(h2h)
    if fav_team is None or dog_team is None:
        alt_fav, alt_dog = pick_favorite_from_h2h(h2h_prices)
        fav_team = fav_team or alt_fav
        dog_team = dog_team or alt_dog

    # Moneyline prices
    fav_price = h2h_prices.get(fav_team)
    dog_price = h2h_prices.get(dog_team)

    # Total
    total = None
    if totals:
        for o in totals.get("outcomes", []):
            pt = o.get("point")
            if isinstance(pt, (int, float)):
                total = float(pt)
                break

    # Display strings
    if fav_team and isinstance(fav_spread, (int, float)):
        fav_str = f"{fav_team} {format_spread_value(fav_spread)}"
    else:
        fav_str = fav_team

    if dog_team and isinstance(dog_spread, (int, float)):
        dog_str = f"{dog_team} {format_spread_value(dog_spread)}"
    else:
        dog_str = dog_team

    matchup = f"{away_team}@{home_team}"
    now = utc_now().isoformat()

    rec = {
        "sport_key": sport_key,
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "favorite": fav_str,
        "underdog": dog_str,
        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": spread,
        "total": total,
        "commence_time": commence_time,
        "book": bookmaker.get("key"),
        "fetched_at": now,
    }

    if fav_price is not None:
        rec["fav_price"] = fav_price
    if dog_price is not None:
        rec["dog_price"] = dog_price

    return rec


def main():
    api_key = get_env_api_key()

    print("\n==============================")
    print("🔥 Fetching Odds from The Odds API")
    print("==============================\n")

    all_games = []

    for sport in SPORTS:
        events = fetch_sport(sport, api_key)
        for ev in events:
            game = build_game_record(ev)
            if game:
                all_games.append(game)

    all_games.sort(key=lambda g: g.get("commence_time", ""))

    ts = utc_now().strftime("%Y%m%d_%H%M")

    output = {
        "timestamp": ts,
        "data": all_games,
    }

    with open("combined.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\n[✅] Saved {len(all_games)} games → combined.json")
    print(f"[🕒] Timestamp: {ts}\n")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
fetch_odds_api.py

Unified odds-fetcher for "major" events only, using The Odds API.

Sports included:
  - americanfootball_nfl
  - americanfootball_ncaaf
  - basketball_nba
  - basketball_ncaab
  - icehockey_nhl
  - mma_mixed_martial_arts

Output:
  combined.json

Schema (per game record):
  {
    "sport_key": str,
    "matchup": "Away Team@Home Team",
    "home_team": str,
    "away_team": str,
    "favorite": "Team -6.5" or "Team +3.5",
    "underdog": "Team +6.5" or "Team -3.5",
    "fav_team": str or null,
    "dog_team": str or null,
    "fav_spread": float or null,
    "dog_spread": float or null,
    "spread": float or null,           # same as fav_spread
    "total": float or null,
    "commence_time": ISO8601 string,
    "book": bookmaker_key (e.g. "draftkings"),
    "fetched_at": ISO8601 string (UTC)
  }
"""

import os
import sys
import json
import datetime
from typing import Any, Dict, List, Optional

import requests


API_BASE = "https://api.the-odds-api.com/v4/sports"

# Only pull the big-boy stuff
SPORTS = [
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "icehockey_nhl",
    "mma_mixed_martial_arts",
]

# Try to stick to one clean, regulated US book when possible
PREFERRED_BOOKMAKERS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "pointsbetus",
    "betonlineag",
    "bovada",
]


def utc_now() -> datetime.datetime:
    """Timezone-aware UTC now."""
    return datetime.datetime.now(datetime.timezone.utc)


def format_spread_value(val: float) -> str:
    """
    Format a spread number with sign:
      -6.5 -> "-6.5"
      +3.0 -> "+3"
      0.0  -> "PK"
    """
    if val == 0 or abs(val) < 1e-6:
        return "PK"
    if val > 0:
        return f"+{val:g}"
    return f"{val:g}"


def get_env_api_key() -> str:
    key = os.getenv("ODDS_API_KEY")
    if not key:
        print(
            "[❌] ODDS_API_KEY is not set.\n"
            "    export ODDS_API_KEY=\"your_real_key_here\" and rerun."
        )
        sys.exit(1)
    return key


def fetch_sport(sport_key: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch odds for a single sport from The Odds API.

    Returns a list of raw event objects. On error, returns an empty list.
    """
    print(f"[⏱️] Fetching {sport_key} ...")
    url = f"{API_BASE}/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",                 # US books
        "markets": "h2h,spreads,totals", # moneyline, spread, total
        "oddsFormat": "american",
        "dateFormat": "iso",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
    except Exception as e:
        print(f"    ❌ Error fetching {sport_key}: {e}")
        return []

    if resp.status_code != 200:
        # Try to show useful API error JSON if present
        try:
            err_body = resp.json()
            msg = err_body.get("message", str(err_body))
        except Exception:
            msg = resp.text
        print(f"    ❌ API error for {sport_key}: {resp.status_code} — {msg}")
        return []

    try:
        events = resp.json()
    except Exception as e:
        print(f"    ❌ Failed to parse JSON for {sport_key}: {e}")
        return []

    if not isinstance(events, list):
        print(f"    ❌ Unexpected response shape for {sport_key} (not a list).")
        return []

    print(f"    → {sport_key}: {len(events)} events")
    remaining = resp.headers.get("x-requests-remaining")
    if remaining is not None:
        print(f"    ↪ Requests remaining: {remaining}")
    return events


def choose_bookmaker(bookmakers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Pick one bookmaker to represent the odds for a game.

    Preference order:
      1) PREFERRED_BOOKMAKERS by key
      2) Otherwise, bookmaker with the latest 'last_update'
      3) Otherwise, the first in the list
    """
    if not bookmakers:
        return None

    by_key = {b.get("key"): b for b in bookmakers if isinstance(b, dict)}

    # Try preferred keys first
    for pref in PREFERRED_BOOKMAKERS:
        if pref in by_key:
            return by_key[pref]

    # Fallback: latest last_update
    try:
        return max(
            bookmakers,
            key=lambda b: b.get("last_update", ""),
        )
    except Exception:
        return bookmakers[0]


def get_market(bookmaker: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """Return the first market within this bookmaker matching the given key."""
    for m in bookmaker.get("markets", []):
        if m.get("key") == key:
            return m
    return None


def parse_spreads(
    spreads_market: Optional[Dict[str, Any]]
) -> (Optional[str], Optional[str], Optional[float], Optional[float], Optional[float]):
    """
    From a spreads market, determine:
        fav_team, dog_team, fav_spread, dog_spread, spread
    where spread == fav_spread (the line on the favorite).
    """
    if not spreads_market:
        return None, None, None, None, None

    outcomes = spreads_market.get("outcomes", []) or []
    valid = [
        o for o in outcomes
        if isinstance(o, dict) and isinstance(o.get("point"), (int, float))
    ]

    if len(valid) < 2:
        return None, None, None, None, None

    # Favorite has the more negative point (e.g. -6.5 vs +6.5)
    fav_outcome = min(valid, key=lambda o: o["point"])
    dog_outcome = max(valid, key=lambda o: o["point"])

    fav_team = fav_outcome.get("name")
    dog_team = dog_outcome.get("name")
    try:
        fav_spread = float(fav_outcome["point"])
        dog_spread = float(dog_outcome["point"])
    except Exception:
        return None, None, None, None, None

    spread = fav_spread
    return fav_team, dog_team, fav_spread, dog_spread, spread


def parse_h2h_prices(
    h2h_market: Optional[Dict[str, Any]]
) -> Dict[str, Optional[int]]:
    """
    From an h2h market, build a {team_name: price} dict.
    """
    prices: Dict[str, Optional[int]] = {}
    if not h2h_market:
        return prices

    for o in h2h_market.get("outcomes", []) or []:
        name = o.get("name")
        price = o.get("price")
        if name is not None:
            prices[name] = price
    return prices


def pick_favorite_from_h2h(prices: Dict[str, Optional[int]]) -> (Optional[str], Optional[str]):
    """
    Determine favorite and underdog based on moneyline prices.

    American odds: more negative = stronger favorite.
    Strategy: choose the outcome with smallest price as favorite.
    """
    if len(prices) < 2:
        return None, None

    # Filter out outcomes with missing prices
    valid = [(team, p) for team, p in prices.items() if isinstance(p, (int, float))]
    if len(valid) < 2:
        return None, None

    fav_team, _ = min(valid, key=lambda x: x[1])
    # pick any other team as dog
    dog_team = next((t for t, _ in valid if t != fav_team), None)
    return fav_team, dog_team


def build_game_record(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert a raw Odds API event into our combined.json record.

    Returns None if we can't find a usable bookmaker / odds.
    """
    sport_key = event.get("sport_key")
    home_team = event.get("home_team")
    away_team = event.get("away_team")
    commence_time = event.get("commence_time")

    if not home_team or not away_team or not commence_time:
        return None

    bookmakers = event.get("bookmakers", []) or []
    bookmaker = choose_bookmaker(bookmakers)
    if not bookmaker:
        # No odds / no bookmaker → skip
        return None

    book_key = bookmaker.get("key") or "unknown"

    # Pull markets
    spreads_market = get_market(bookmaker, "spreads")
    totals_market = get_market(bookmaker, "totals")
    h2h_market = get_market(bookmaker, "h2h")

    # First try to derive favorite/dog from spreads
    fav_team, dog_team, fav_spread, dog_spread, spread = parse_spreads(spreads_market)

    # Moneyline prices
    price_map = parse_h2h_prices(h2h_market)
    fav_price = None
    dog_price = None

    # If spreads didn't give us fav/dog, fall back to h2h
    if fav_team is None or dog_team is None:
        alt_fav, alt_dog = pick_favorite_from_h2h(price_map)
        fav_team = fav_team or alt_fav
        dog_team = dog_team or alt_dog

    # Attach prices if we have team names
    if fav_team and fav_team in price_map:
        fav_price = price_map[fav_team]
    if dog_team and dog_team in price_map:
        dog_price = price_map[dog_team]

    # Total (over/under)
    total = None
    if totals_market:
        tot_outcomes = totals_market.get("outcomes", []) or []
        # Any of the outcomes will have the total point (same for Over/Under)
        for o in tot_outcomes:
            pt = o.get("point")
            if isinstance(pt, (int, float)):
                total = float(pt)
                break

    # Build display strings
    if fav_team is not None and isinstance(fav_spread, (int, float)):
        fav_str = f"{fav_team} {format_spread_value(fav_spread)}"
    else:
        fav_str = fav_team

    if dog_team is not None and isinstance(dog_spread, (int, float)):
        dog_str = f"{dog_team} {format_spread_value(dog_spread)}"
    else:
        dog_str = dog_team

    # If we somehow still have no favorite, this event probably isn't useful
    if not fav_team and not dog_team and total is None:
        return None

    matchup = f"{away_team}@{home_team}"

    now_iso = utc_now().isoformat()

    record: Dict[str, Any] = {
        "sport_key": sport_key,
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "favorite": fav_str,
        "underdog": dog_str,
        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": spread,
        "total": total,
        "commence_time": commence_time,
        "book": book_key,
        "fetched_at": now_iso,
    }

    # Optional: include moneyline prices for future use (dashboard, Telegram, etc.)
    if fav_price is not None:
        record["fav_price"] = fav_price
    if dog_price is not None:
        record["dog_price"] = dog_price

    return record


def main() -> None:
    api_key = get_env_api_key()
    print("\n==============================")
    print("🔥 Fetching Odds from The Odds API")
    print("==============================\n")

    all_games: List[Dict[str, Any]] = []

    for sport in SPORTS:
        raw_events = fetch_sport(sport, api_key)
        for event in raw_events:
            game = build_game_record(event)
            if game is not None:
                all_games.append(game)

    # Sort by commence_time (ISO strings sort correctly)
    all_games.sort(key=lambda g: g.get("commence_time", ""))

    ts = utc_now()
    ts_str = ts.strftime("%Y%m%d_%H%M")

    combined = {
        "timestamp": ts_str,
        "data": all_games,
    }

    out_path = "combined.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    print(f"\n[✅] Saved {len(all_games)} games → {out_path}")
    print(f"[🕒] Timestamp: {ts_str}\n")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
fetch_odds_api.py

Pulls odds from The Odds API (https://the-odds-api.com/)
and writes a normalized combined.json that your dashboard
can safely use.

Key points:

- Favorite is ALWAYS the team with the MORE NEGATIVE spread ("point").
- Underdog is the team with the MORE POSITIVE spread.
- We do NOT flip spreads based on home/away.
- UFC only: filter mma events so that only UFC-branded events remain.
"""

import os
import json
import datetime
import requests
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

if not ODDS_API_KEY:
    raise SystemExit(
        "❌ ODDS_API_KEY not set. Run:\n\n"
        'export ODDS_API_KEY="YOUR_REAL_KEY_HERE"\n'
    )

BASE_URL = "https://api.the-odds-api.com/v4/sports"

# Sports to pull
SPORTS = [
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "icehockey_nhl",
    "mma_mixed_martial_arts",
]

# Only US books
REGIONS = "us"
# Markets we care about
MARKETS = "spreads,totals,h2h"
ODDS_FORMAT = "american"

OUTPUT_FILE = "combined.json"


# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------

def fetch_sport(sport_key: str) -> List[Dict[str, Any]]:
    """Fetch a single sport from The Odds API."""
    url = f"{BASE_URL}/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }

    print(f"[⏱️] Fetching {sport_key} ...")
    r = requests.get(url, params=params, timeout=15)
    if not r.ok:
        try:
            body = r.json()
        except Exception:
            body = r.text
        print(
            f"❌ API error for {sport_key}: {r.status_code} — {body}"
        )
        return []

    data = r.json()
    print(f"  → {sport_key}: {len(data)} events")
    return data


def pick_bookmaker(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Prefer DraftKings if present, otherwise first bookmaker."""
    books = event.get("bookmakers") or []
    if not books:
        return None

    # Prefer DraftKings or FanDuel if available
    preferred = None
    for b in books:
        key = (b.get("key") or "").lower()
        if key in ("draftkings", "fanduel"):
            preferred = b
            break

    return preferred or books[0]


def get_market(bookmaker: Dict[str, Any], market_key: str) -> Optional[Dict[str, Any]]:
    """Return a given market from bookmaker, e.g. 'spreads' or 'totals'."""
    for m in bookmaker.get("markets", []):
        if m.get("key") == market_key:
            return m
    return None


def resolve_spreads(
    spreads_market: Optional[Dict[str, Any]],
    home_team: str,
    away_team: str,
) -> Dict[str, Any]:
    """
    Given a spreads market, decide favorite/underdog.

    RULE:
      - Favorite is outcome with the MORE NEGATIVE point.
      - Underdog is outcome with the MORE POSITIVE point.
      - If both points are equal or missing → no favorite.
    """
    if not spreads_market:
        return {
            "favorite": None,
            "underdog": None,
            "fav_team": None,
            "dog_team": None,
            "fav_spread": None,
            "dog_spread": None,
            "spread": None,
        }

    outcomes = spreads_market.get("outcomes") or []
    if len(outcomes) < 2:
        return {
            "favorite": None,
            "underdog": None,
            "fav_team": None,
            "dog_team": None,
            "fav_spread": None,
            "dog_spread": None,
            "spread": None,
        }

    # Try to line up by team names when possible
    # Odds API outcome["name"] should match team names exactly.
    # If not, we still only care about "point" signs.
    cleaned = []
    for o in outcomes:
        name = o.get("name")
        point = o.get("point")
        if name is None or point is None:
            continue
        cleaned.append({"name": name, "point": float(point)})

    if len(cleaned) < 2:
        return {
            "favorite": None,
            "underdog": None,
            "fav_team": None,
            "dog_team": None,
            "fav_spread": None,
            "dog_spread": None,
            "spread": None,
        }

    o1, o2 = cleaned[0], cleaned[1]

    # If both points are exactly equal (e.g. 0 / 0) treat as pick'em
    if abs(o1["point"] - o2["point"]) < 1e-9:
        return {
            "favorite": None,
            "underdog": None,
            "fav_team": None,
            "dog_team": None,
            "fav_spread": 0.0,
            "dog_spread": 0.0,
            "spread": 0.0,
        }

    # Favorite: more negative "point"
    favorite_outcome = o1 if o1["point"] < o2["point"] else o2
    underdog_outcome = o2 if favorite_outcome is o1 else o1

    fav_name = favorite_outcome["name"]
    dog_name = underdog_outcome["name"]
    fav_point = favorite_outcome["point"]
    dog_point = underdog_outcome["point"]

    # Ensure the favorite ALWAYS has negative spread
    # If (for some weird feed) fav_point is positive, flip both.
    if fav_point > 0 and dog_point < 0:
        fav_point, dog_point = -dog_point, -fav_point
        fav_name, dog_name = dog_name, fav_name

    return {
        "favorite": f"{fav_name} {fav_point:+g}",
        "underdog": f"{dog_name} {dog_point:+g}",
        "fav_team": fav_name,
        "dog_team": dog_name,
        "fav_spread": fav_point,
        "dog_spread": dog_point,
        "spread": fav_point,
    }


def resolve_total(totals_market: Optional[Dict[str, Any]]) -> Optional[float]:
    """Extract the main total points from the totals market."""
    if not totals_market:
        return None
    outcomes = totals_market.get("outcomes") or []
    if not outcomes:
        return None

    # Totals should have Over/Under with a shared point.
    # Just grab the first defined "point".
    for o in outcomes:
        if o.get("point") is not None:
            try:
                return float(o["point"])
            except (TypeError, ValueError):
                continue
    return None


def should_keep_event(event: Dict[str, Any]) -> bool:
    """Filter events if needed (e.g., UFC only for MMA)."""
    sport_key = event.get("sport_key") or event.get("sport")
    home_team = event.get("home_team") or ""
    away_team = event.get("away_team") or ""

    if sport_key == "mma_mixed_martial_arts":
        # Keep only UFC-branded events: if home or away contains 'UFC'
        text = f"{home_team} {away_team}".upper()
        if "UFC" not in text:
            return False

    return True


# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------

def main() -> None:
    print("\n==============================")
    print("🔥 Fetching Odds from Odds-API.com")
    print("==============================\n")

    all_rows: List[Dict[str, Any]] = []

    for sport in SPORTS:
        raw_events = fetch_sport(sport)
        for ev in raw_events:
            # The Odds API returns:
            # {
            #   "id", "sport_key", "sport_title",
            #   "home_team", "away_team",
            #   "commence_time",
            #   "bookmakers": [...]
            # }
            ev_sport_key = ev.get("sport_key", sport)
            home = ev.get("home_team")
            away = ev.get("away_team")
            if not home or not away:
                # Skip weird/invalid events
                continue

            ev["sport_key"] = ev_sport_key
            if not should_keep_event(ev):
                continue

            bookmaker = pick_bookmaker(ev)
            if not bookmaker:
                continue

            spreads_market = get_market(bookmaker, "spreads")
            totals_market = get_market(bookmaker, "totals")

            spread_info = resolve_spreads(spreads_market, home, away)
            total_points = resolve_total(totals_market)

            row = {
                "sport_key": ev_sport_key,
                "matchup": f"{away}@{home}",
                "home_team": home,
                "away_team": away,
                "favorite": spread_info["favorite"],
                "underdog": spread_info["underdog"],
                "fav_team": spread_info["fav_team"],
                "dog_team": spread_info["dog_team"],
                "fav_spread": spread_info["fav_spread"],
                "dog_spread": spread_info["dog_spread"],
                "spread": spread_info["spread"],
                "total": total_points,
                "commence_time": ev.get("commence_time"),
                "book": bookmaker.get("key") or bookmaker.get("title"),
                "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
            }

            all_rows.append(row)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M")
    out = {
        "timestamp": ts,
        "data": all_rows,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n[✅] Saved {len(all_rows)} games → {OUTPUT_FILE}")
    print(f"[🕒] Timestamp: {ts}")


if __name__ == "__main__":
    main()

