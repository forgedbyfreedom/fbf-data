#!/usr/bin/env python3
"""
fetch_odds_api.py

Use The Odds API to pull real betting lines for multiple sports
and write a unified combined.json that your dashboard can consume.

Relies on:
  - requests

Sports covered:
  - NFL
  - NCAAF
  - NBA
  - NCAAB
  - NHL
  - MLB
  - MMA (UFC / mixed martial arts)
"""

import requests
import json
import datetime
import sys
import os

# 🔑 Your Odds API key (user-provided)
API_KEY = "81738482789b292518dbffbb53dd5b8c"

# 📚 Sports we care about (The Odds API sport keys)
SPORT_KEYS = {
    "americanfootball_nfl": "NFL Football",
    "americanfootball_ncaaf": "NCAA Football",
    "basketball_nba": "NBA Basketball",
    "basketball_ncaab": "NCAA Men's Basketball",
    "icehockey_nhl": "NHL Hockey",
    "baseball_mlb": "MLB Baseball",
    "mma_mixed_martial_arts": "UFC / MMA",
}

# 🎯 We’ll take US books and spreads/totals markets
REGIONS = "us"
MARKETS = "spreads,totals"

# 🏦 Preferred book (reputable), with graceful fallback
PREFERRED_BOOK = "draftkings"

OUT_FILE = "combined.json"


def fetch_sport(sport_key: str):
    """
    Call The Odds API for a single sport and return the JSON list of events.
    """
    url = (
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
        f"?apiKey={API_KEY}"
        f"&regions={REGIONS}"
        f"&markets={MARKETS}"
        f"&oddsFormat=american"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print(f"  → {sport_key}: {len(data)} events")
        return data
    except Exception as e:
        print(f"❌ Failed fetching {sport_key}: {e}")
        return []


def choose_bookmaker(bookmakers):
    """
    Try to choose our preferred bookmaker; fall back to first available.
    """
    if not bookmakers:
        return None
    for bm in bookmakers:
        if bm.get("key") == PREFERRED_BOOK:
            return bm
    return bookmakers[0]


def extract_from_book(game, sport_key: str):
    """
    From one game object + chosen bookmaker, extract:

      - home_team, away_team
      - favorite, underdog, fav_spread, dog_spread
      - total (points only)
    """
    home = game.get("home_team")
    away = game.get("away_team")
    commence = game.get("commence_time")

    bookmakers = game.get("bookmakers") or []
    bm = choose_bookmaker(bookmakers)
    if not bm:
        # No lines at all; return schedule-only record
        return {
            "sport_key": sport_key,
            "matchup": f"{away}@{home}",
            "home_team": home,
            "away_team": away,
            "favorite": None,
            "underdog": None,
            "fav_team": None,
            "dog_team": None,
            "fav_spread": None,
            "dog_spread": None,
            "spread": None,
            "total": None,
            "commence_time": commence,
            "book": None,
            "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    markets = bm.get("markets") or []

    fav_team = dog_team = None
    fav_spread = dog_spread = None
    total_points = None

    # Parse spreads & totals
    for market in markets:
        key = market.get("key")
        outcomes = market.get("outcomes") or []

        # 🧮 Spread market: determine favorite by most negative spread
        if key == "spreads":
            home_point = away_point = None
            for o in outcomes:
                name = o.get("name")
                pt = o.get("point")
                if name == home:
                    home_point = pt
                elif name == away:
                    away_point = pt

            if home_point is not None and away_point is not None:
                # More negative = stronger favorite
                if home_point < away_point:
                    fav_team, fav_spread = home, home_point
                    dog_team, dog_spread = away, away_point
                elif away_point < home_point:
                    fav_team, fav_spread = away, away_point
                    dog_team, dog_spread = home, home_point
                else:
                    # Perfect pick'em: no favorite
                    fav_team = dog_team = None
                    fav_spread = dog_spread = None

        # 🎯 Totals market: we only care about the points, not the price
        if key == "totals":
            for o in outcomes:
                if o.get("name") == "Over":
                    total_points = o.get("point")

    # Compose string forms
    if fav_team is not None and fav_spread is not None:
        fav_str = f"{fav_team} {fav_spread:+g}"
    else:
        fav_str = None

    if dog_team is not None and dog_spread is not None:
        dog_str = f"{dog_team} {dog_spread:+g}"
    else:
        dog_str = None

    # For convenience, keep a generic spread = favorite spread
    spread = fav_spread

    return {
        "sport_key": sport_key,
        "matchup": f"{away}@{home}",
        "home_team": home,
        "away_team": away,
        "favorite": fav_str,
        "underdog": dog_str,
        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": spread,
        "total": total_points,
        "commence_time": commence,
        "book": bm.get("key"),
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def main():
    print("\n==============================")
    print("🔥 Fetching Odds from The Odds API")
    print("==============================\n")

    all_games = []
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M")

    for sport_key in SPORT_KEYS.keys():
        print(f"[⏱️] Fetching {sport_key} ...")
        raw_events = fetch_sport(sport_key)

        for game in raw_events:
            cleaned = extract_from_book(game, sport_key)
            all_games.append(cleaned)

    payload = {
        "timestamp": ts,
        "data": all_games,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[✅] Saved {len(all_games)} games → {OUT_FILE}")
    print(f"[🕒] Timestamp: {ts}\n")


if __name__ == "__main__":
    main()

