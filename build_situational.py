#!/usr/bin/env python3
"""
build_situational.py
Detects situational betting spots for each upcoming game:

- Back-to-back (NBA/NHL): team playing 2nd game in 2 days
- Rest advantage: 3+ more rest days than opponent
- Revenge game: lost to this opponent recently (last 2 meetings)
- Divisional/rivalry: same division/conference games play tighter
- Travel fatigue: 3+ timezone changes in recent stretch
- Win/loss streak: 5+ game streaks affect psychology

Output: situational_data.json

Run AFTER: build_historical_results.py, build_h2h.py
Run BEFORE: merge_features.py
"""

import json, re, math
from datetime import datetime, timezone, timedelta
from collections import defaultdict

COMBINED = "combined.json"
HISTORICAL = "historical_results.json"
STADIUMS = "stadiums_master.json"
OUTPUT = "situational_data.json"

# Timezone offsets by US region (approximate from longitude)
# Used to detect cross-timezone travel
TZ_REGIONS = {
    "eastern": (-85, -67),
    "central": (-105, -85),
    "mountain": (-115, -105),
    "pacific": (-125, -115),
}

# NFL/NCAAF divisions for rivalry detection
# (We'll detect divisional matchups from historical frequency)


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def normalize(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_date(d):
    if not d:
        return None
    try:
        # Handle various formats
        for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                     "%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(d.replace("+00:00", "Z").replace("+0000", "Z"), fmt)
            except ValueError:
                continue
        # Fallback: just parse date portion
        return datetime.strptime(d[:10], "%Y-%m-%d")
    except Exception:
        return None


def get_tz_region(lon):
    """Get timezone region from longitude."""
    if lon is None:
        return None
    for region, (lo, hi) in TZ_REGIONS.items():
        if lo <= lon <= hi:
            return region
    return None


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])
    hist = load_json(HISTORICAL, {})
    hist_games = hist.get("data", [])
    stadiums = load_json(STADIUMS, {})

    # Build team location lookup from stadiums
    team_coords = {}
    for key, s in stadiums.items():
        lat = s.get("lat") or s.get("latitude")
        lon = s.get("lon") or s.get("longitude")
        team = s.get("team") or s.get("name")
        if lat and lon and team:
            try:
                team_coords[normalize(team)] = (float(lat), float(lon))
            except (ValueError, TypeError):
                pass

    # Build recent game history per team from historical data
    # team_history[norm_name] = [(date, opponent_norm, margin, is_home)]
    team_history = defaultdict(list)
    for g in hist_games:
        home = g.get("home_team", {})
        away = g.get("away_team", {})
        hs = home.get("score")
        aws = away.get("score")
        if hs is None or aws is None:
            continue

        date = parse_date(g.get("date_utc"))
        if not date:
            continue

        home_key = normalize(home.get("name", ""))
        away_key = normalize(away.get("name", ""))
        margin = float(hs) - float(aws)

        if home_key:
            team_history[home_key].append((date, away_key, margin, True))
        if away_key:
            team_history[away_key].append((date, home_key, -margin, False))

    # Sort each team's history by date
    for key in team_history:
        team_history[key].sort(key=lambda x: x[0])

    # Detect frequent matchups (divisional proxy)
    matchup_freq = defaultdict(int)
    for g in hist_games:
        sport = (g.get("sport") or "").lower()
        home_key = normalize(g.get("home_team", {}).get("name", ""))
        away_key = normalize(g.get("away_team", {}).get("name", ""))
        if home_key and away_key:
            pair = tuple(sorted([home_key, away_key]))
            matchup_freq[(sport, pair)] += 1

    # For each upcoming game, compute situational factors
    output = {}
    for g in games:
        game_id = str(g.get("id") or g.get("event_id") or "")
        if not game_id:
            continue

        sport = (g.get("sport") or "").lower()
        home_team = g.get("home_team", {})
        away_team = g.get("away_team", {})
        home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
        away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)
        home_key = normalize(home_name)
        away_key = normalize(away_name)
        game_date = parse_date(g.get("date_utc"))

        spots = {
            "home_b2b": False,
            "away_b2b": False,
            "home_streak": 0,  # positive = win streak, negative = loss streak
            "away_streak": 0,
            "revenge_home": False,  # home team lost last meeting
            "revenge_away": False,
            "divisional": False,
            "home_tz_changes": 0,
            "away_tz_changes": 0,
            "home_rest_days": None,
            "away_rest_days": None,
            "spot_score": 0,  # aggregate situational edge for home team
        }

        # --- Back-to-back detection ---
        if game_date:
            for team_key, prefix in [(home_key, "home"), (away_key, "away")]:
                hist_list = team_history.get(team_key, [])
                if hist_list:
                    last_game = hist_list[-1]
                    days_rest = (game_date - last_game[0]).days
                    spots[f"{prefix}_rest_days"] = days_rest
                    if days_rest <= 1 and sport in ("nba", "nhl"):
                        spots[f"{prefix}_b2b"] = True

        # --- Win/loss streaks ---
        for team_key, prefix in [(home_key, "home"), (away_key, "away")]:
            hist_list = team_history.get(team_key, [])
            if not hist_list:
                continue
            streak = 0
            for entry in reversed(hist_list):
                margin = entry[2]
                if streak == 0:
                    streak = 1 if margin > 0 else -1
                elif (streak > 0 and margin > 0):
                    streak += 1
                elif (streak < 0 and margin < 0):
                    streak -= 1
                else:
                    break
            spots[f"{prefix}_streak"] = streak

        # --- Revenge game ---
        # Check last 2 meetings between these teams
        home_hist = team_history.get(home_key, [])
        h2h_recent = [g for g in home_hist if g[1] == away_key][-2:]
        if h2h_recent:
            last_meeting = h2h_recent[-1]
            if last_meeting[2] < 0:  # home team lost last meeting
                spots["revenge_home"] = True
            elif last_meeting[2] > 0:
                spots["revenge_away"] = True

        # --- Divisional game (high frequency = likely same division) ---
        pair = tuple(sorted([home_key, away_key]))
        freq = matchup_freq.get((sport, pair), 0)
        if sport in ("nfl", "ncaaf") and freq >= 3:
            spots["divisional"] = True
        elif sport in ("nba", "nhl") and freq >= 6:
            spots["divisional"] = True
        elif sport == "mlb" and freq >= 10:
            spots["divisional"] = True

        # --- Timezone travel ---
        home_coords = team_coords.get(home_key)
        away_coords = team_coords.get(away_key)
        if home_coords and away_coords:
            home_tz = get_tz_region(home_coords[1])
            away_tz = get_tz_region(away_coords[1])
            if home_tz and away_tz and home_tz != away_tz:
                # Count timezone difference
                tz_order = ["pacific", "mountain", "central", "eastern"]
                if home_tz in tz_order and away_tz in tz_order:
                    tz_diff = abs(tz_order.index(home_tz) - tz_order.index(away_tz))
                    spots["away_tz_changes"] = tz_diff

        # --- Compute aggregate spot score (positive = favors home) ---
        score = 0

        # B2B: playing on back-to-back is ~2-3 point disadvantage
        if spots["away_b2b"] and not spots["home_b2b"]:
            score += 2.0
        elif spots["home_b2b"] and not spots["away_b2b"]:
            score -= 2.0

        # Streaks: long streaks regress. 5+ win streak = due for regression
        home_s = spots["home_streak"]
        away_s = spots["away_streak"]
        if home_s >= 5:
            score -= 0.5  # regression to mean
        elif home_s <= -5:
            score += 0.5
        if away_s >= 5:
            score += 0.5
        elif away_s <= -5:
            score -= 0.5

        # Revenge: slight motivation edge
        if spots["revenge_home"]:
            score += 0.5
        elif spots["revenge_away"]:
            score -= 0.5

        # Divisional: games play tighter (toward underdog)
        if spots["divisional"]:
            score *= 0.8  # reduce any existing edge — divisional games are unpredictable

        # Timezone: away team traveling across timezones
        tz_ch = spots["away_tz_changes"]
        if tz_ch >= 2:
            score += 1.0  # significant travel disadvantage for away team
        elif tz_ch >= 1:
            score += 0.3

        spots["spot_score"] = round(score, 2)

        output[game_id] = spots

    with open(OUTPUT, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "games_analyzed": len(output),
            "spots": output,
        }, f, indent=2)

    # Stats
    b2b = sum(1 for s in output.values() if s["home_b2b"] or s["away_b2b"])
    revenge = sum(1 for s in output.values() if s["revenge_home"] or s["revenge_away"])
    div = sum(1 for s in output.values() if s["divisional"])
    has_spot = sum(1 for s in output.values() if abs(s["spot_score"]) > 0.3)
    print(f"[situational] {len(output)} games: {b2b} B2B, {revenge} revenge, {div} divisional, {has_spot} with significant spot")


if __name__ == "__main__":
    main()
