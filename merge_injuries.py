#!/usr/bin/env python3
"""
merge_injuries.py
Merges injury data from injuries.json onto games in combined.json.
Adds home_injuries, away_injuries arrays and injury_count_home/away counts.
"""
import json, re

def normalize_team(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


# Common name mappings for team matching
TEAM_ALIASES = {
    "lal": "losangeleslakers",
    "lac": "laclippers",
    "gsw": "goldenstatewarriors",
    "okc": "oklahomacitythunder",
    "nyk": "newyorkknicks",
    "bkn": "brooklynnets",
    "nop": "neworleanspelicans",
    "sas": "sanantoniospurs",
    "por": "portlandtrailblazers",
}


def build_injury_index(injuries):
    """Build index: (sport, team_norm) -> list of injury rows."""
    index = {}
    for row in injuries:
        sport = (row.get("sport") or "").lower()
        team_norm = row.get("team_norm") or normalize_team(row.get("team", ""))
        if not team_norm:
            continue
        key = (sport, team_norm)
        index.setdefault(key, []).append(row)
    return index


def find_injuries_for_team(inj_index, sport, team_name, team_abbr=None):
    """Find injuries matching a team. Tries multiple matching strategies."""
    sport = sport.lower()
    team_norm = normalize_team(team_name)

    # Direct match
    result = inj_index.get((sport, team_norm), [])
    if result:
        return result

    # Try abbreviation-based lookup
    if team_abbr:
        abbr_norm = normalize_team(team_abbr)
        alias = TEAM_ALIASES.get(abbr_norm)
        if alias:
            result = inj_index.get((sport, alias), [])
            if result:
                return result

    # Fuzzy: check if team_norm is a substring of any index key
    for (s, tn), rows in inj_index.items():
        if s != sport:
            continue
        if team_norm in tn or tn in team_norm:
            return rows

    return []


def _recent_count(rows, hours=48):
    """Unavailable players whose injury was reported within `hours`."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    n = 0
    for r in rows:
        if not r.get("unavailable"):
            continue
        ts = r.get("reported_at")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        if when >= cutoff:
            n += 1
    return n


def main():
    try:
        with open("combined.json") as f:
            combined = json.load(f)
    except Exception as e:
        print(f"combined.json error: {e}")
        return

    try:
        with open("injuries.json") as f:
            inj_data = json.load(f)
    except Exception as e:
        print(f"injuries.json error: {e}")
        return

    games = combined.get("data") or combined.get("games") or []

    # Handle both old format (list) and new format ({injuries: [...]})
    if isinstance(inj_data, list):
        inj_rows = inj_data
    elif isinstance(inj_data, dict):
        inj_rows = inj_data.get("injuries", inj_data.get("data", []))
    else:
        inj_rows = []

    inj_index = build_injury_index(inj_rows)
    print(f"[merge_injuries] Loaded {len(inj_rows)} injury rows across {len(inj_index)} team/sport combos")

    merged_count = 0
    for g in games:
        sport = (g.get("sport") or "").lower()
        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}

        home_name = home_team.get("name") or home_team.get("abbr") or ""
        away_name = away_team.get("name") or away_team.get("abbr") or ""
        home_abbr = home_team.get("abbr") or ""
        away_abbr = away_team.get("abbr") or ""

        home_inj = find_injuries_for_team(inj_index, sport, home_name, home_abbr)
        away_inj = find_injuries_for_team(inj_index, sport, away_name, away_abbr)

        if home_inj or away_inj:
            merged_count += 1

        # Store simplified injury summaries (not full raw data to keep JSON small)
        g["home_injuries"] = [
            {"player": r.get("player", ""), "status": r.get("status", ""),
             "position": r.get("position", ""), "unavailable": r.get("unavailable", False),
             "reported_at": r.get("reported_at")}
            for r in home_inj
        ]
        g["away_injuries"] = [
            {"player": r.get("player", ""), "status": r.get("status", ""),
             "position": r.get("position", ""), "unavailable": r.get("unavailable", False),
             "reported_at": r.get("reported_at")}
            for r in away_inj
        ]
        # injury_count counts players who are actually UNAVAILABLE, not rows on
        # a page. More than half of ESPN's injury entries carry status "Active"
        # - a note about a player who is playing - so a raw row count measured
        # nothing. Questionable is tracked separately rather than folded in.
        g["injury_count_home"] = sum(1 for r in home_inj if r.get("unavailable"))
        g["injury_count_away"] = sum(1 for r in away_inj if r.get("unavailable"))
        g["injury_questionable_home"] = sum(1 for r in home_inj if not r.get("unavailable"))
        g["injury_questionable_away"] = sum(1 for r in away_inj if not r.get("unavailable"))

        # Late-breaking injuries: reported within 48 hours. This is the case
        # where the market may genuinely not have caught up, and it is the only
        # injury signal with a plausible edge - Vegas prices known injuries.
        # Computed and stored, deliberately NOT wired into the projection: no
        # forward test has shown it works yet. See MODEL_NOTES.md.
        g["injury_recent_home"] = _recent_count(home_inj)
        g["injury_recent_away"] = _recent_count(away_inj)

    combined["data"] = games
    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[merge_injuries] Merged injuries onto {merged_count}/{len(games)} games.")


if __name__ == "__main__":
    main()
