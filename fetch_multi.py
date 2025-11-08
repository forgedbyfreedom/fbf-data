#!/usr/bin/env python3
"""
fetch_multi.py – writes per-sport & metadata JSONs that your publisher pushes live.
Safe scaffold: replaces with real API calls later.
"""

import json, os, datetime

BASE_DIR = "/Users/weero/fbf_fetcher"

def utcnow():
    return datetime.datetime.utcnow().isoformat() + "Z"

def write_json(filename: str, payload):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {filename}")

# ----------------- SAMPLE DATA (replace with real fetches later) -----------------

def fetch_nfl():
    return {
        "timestamp": utcnow(),
        "sport": "NFL",
        "games": [
            {"matchup": "Giants@Eagles", "commence_time": "2025-11-09T18:00:00Z", "spread": -7.5, "total": 44.5, "book": "CONS"},
            {"matchup": "Packers@Bears", "commence_time": "2025-11-09T18:00:00Z", "spread": 2.5, "total": 41.0, "book": "CONS"},
        ]
    }

def fetch_weather():
    return {
        "timestamp": utcnow(),
        "weather": [
            {"game": "Giants@Eagles", "venue": "Lincoln Financial Field", "forecast_time_utc": "2025-11-09T17:00:00Z", "temp_f": 70, "wind_mph": 4, "precip_prob": 5, "notes": "Clear"},
            {"game": "Packers@Bears", "venue": "Soldier Field", "forecast_time_utc": "2025-11-09T17:00:00Z", "temp_f": 55, "wind_mph": 10, "precip_prob": 15, "notes": "Cloudy"},
        ]
    }

def fetch_referees():
    return {
        "timestamp": utcnow(),
        "referees": [
            {"league": "NFL", "game_id": "NYG@PHI_2025-11-09", "crew_chief": "John Hussey", "crew": ["Hussey","A Smith","B Kelly","C Young"], "avg_penalties": 11.3, "ou_bias": "under"},
            {"league": "NFL", "game_id": "GB@CHI_2025-11-09",  "crew_chief": "Shawn Hochuli", "crew": ["Hochuli","D Jones","E Reid","F Lee"], "avg_penalties": 13.1, "ou_bias": "over"},
        ]
    }

def fetch_injuries():
    return {
        "timestamp": utcnow(),
        "injuries": [
            {"league": "NFL", "team": "MIN", "player": "J. Jefferson", "status": "Q", "expected_snaps_delta": -0.10, "updated": utcnow()},
            {"league": "NFL", "team": "NYJ", "player": "A. Rodgers",  "status": "IR", "expected_snaps_delta": -1.00, "updated": utcnow()},
        ]
    }

def fetch_power_ratings():
    return {
        "timestamp": utcnow(),
        "power_ratings": [
            {"league": "NCAAF", "team": "Georgia",  "elo": 2015},
            {"league": "NCAAF", "team": "Alabama",  "elo": 1998},
            {"league": "NFL",   "team": "Eagles",   "elo": 1705},
            {"league": "NFL",   "team": "Chiefs",   "elo": 1720},
        ]
    }

# ----------------- MAIN -----------------

def main():
    # Per-sport examples (add more later as *_latest.json files)
    nfl = fetch_nfl()
    write_json("nfl_latest.json", nfl)

    # Metadata feeds
    write_json("weather.json",        fetch_weather())
    write_json("referees.json",       fetch_referees())
    write_json("injuries.json",       fetch_injuries())
    write_json("power_ratings.json",  fetch_power_ratings())

    # If you want a combined_latest.json from these pieces too, you can merge here later.

if __name__ == "__main__":
    main()

