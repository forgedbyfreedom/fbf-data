#!/usr/bin/env python3
"""
track_accuracy.py
Evaluates accuracy for Straight Up, ATS, and Over/Under picks
ONLY for games dated AFTER 2025-11-26.

Requires an up-to-date combined.json (your main game data feed).
Logs results to performance_log.json.

Tracks ONLY picks your system actually made (SU / ATS / O/U independently).
"""

import requests
import json
import os
from datetime import datetime, timezone

OUTPUT = "performance_log.json"
CUTOFF_DATE = datetime(2025, 11, 26, tzinfo=timezone.utc)  # Track from Nov 27 onward


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def get_json(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  Failed {url}: {e}")
        return None


def parse_game_date(raw):
    """Return datetime object from combined.json date."""
    dt = raw.get("date_utc") or raw.get("date_local")
    if not dt:
        return None

    try:
        if "T" in dt:
            return datetime.fromisoformat(dt.replace("Z", "+00:00"))
        return datetime.strptime(dt, "%Y-%m-%d %I:%M %p ET").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def extract_score(event):
    """Extract final scores from an ESPN Core event object."""
    try:
        competitors = event["competitions"][0]["competitors"]
        return {
            c["team"]["displayName"]: int(c.get("score", 0))
            for c in competitors if "team" in c
        }
    except Exception:
        return {}


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json not found.")
        return

    with open("combined.json") as f:
        combined = json.load(f)

    games = combined.get("data", [])

    results = []

    # Running totals (only for categories where picks exist)
    total_su = total_su_correct = 0
    total_ats = total_ats_correct = 0
    total_ou = total_ou_correct = 0

    # ESPN Core league map
    league_map = {
        "nfl": "football/leagues/nfl",
        "ncaaf": "football/leagues/college-football",
        "nba": "basketball/leagues/nba",
        "ncaab": "basketball/leagues/mens-college-basketball",
        "nhl": "hockey/leagues/nhl",
        "mlb": "baseball/leagues/mlb",
    }

    print("🔍 Checking final scores...")

    for g in games:
        # Must have a valid game date
        g_date = parse_game_date(g)
        if g_date is None or g_date <= CUTOFF_DATE:
            continue  # ❗ Ignore games before cutoff

        sport_key = g.get("sport", "").lower()
        if sport_key not in league_map:
            continue

        league_path = league_map[sport_key]

        # Pull ESPN events list
        url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
        events_data = get_json(url)
        if not events_data or "items" not in events_data:
            continue

        # Find matching game by team names
        home = g["home_team"]["name"]
        away = g["away_team"]["name"]

        event_match = None
        for ev_ref in events_data["items"]:
            if not isinstance(ev_ref, dict) or "$ref" not in ev_ref:
                continue

            event = get_json(ev_ref["$ref"])
            if not event:
                continue

            name = event.get("name", "")
            if home in name and away in name:
                event_match = event
                break

        if not event_match:
            continue

        scores = extract_score(event_match)
        if len(scores) < 2:
            continue

        # Identify favorite/dog
        fav = g.get("favorite_team")
        dog = g.get("dog_team")
        spread = float(g.get("fav_spread") or 0)
        total_line = g.get("total")

        fav_score = scores.get(fav, 0)
        dog_score = scores.get(dog, 0)
        total_score = fav_score + dog_score

        # -------------------------------------------------------
        # Straight Up (ONLY if we made an SU pick)
        # -------------------------------------------------------
        su_pick = g.get("pick_su_team")
        su_correct = None

        if su_pick:
            total_su += 1
            winner = fav if fav_score > dog_score else dog
            su_correct = (su_pick == winner)
            if su_correct:
                total_su_correct += 1

        # -------------------------------------------------------
        # ATS (ONLY if we made an ATS pick)
        # -------------------------------------------------------
        ats_pick = g.get("pick_ats_team")
        ats_pick_line = g.get("pick_ats_line")
        ats_correct = None

        if ats_pick and ats_pick_line is not None:
            total_ats += 1

            # Determine ATS winner using actual scores
            fav_margin = fav_score - dog_score
            covers_fav = fav_margin > spread
            ats_real_team = fav if covers_fav else dog

            ats_correct = (ats_pick == ats_real_team)
            if ats_correct:
                total_ats_correct += 1

        # -------------------------------------------------------
        # OVER/UNDER (ONLY if we made an O/U pick)
        # -------------------------------------------------------
        ou_pick = g.get("pick_total")
        ou_correct = None

        if ou_pick and total_line is not None:
            total_ou += 1
            if ou_pick == "Over":
                ou_correct = total_score > total_line
            else:
                ou_correct = total_score < total_line

            if ou_correct:
                total_ou_correct += 1

        # Save results entry
        results.append({
            "matchup": g.get("shortName"),
            "sport": sport_key,
            "date": g.get("date_local"),
            "favorite": fav,
            "spread": spread,
            "total_line": total_line,
            "fav_score": fav_score,
            "dog_score": dog_score,
            "total_score": total_score,
            "SU_pick": su_pick,
            "SU_correct": su_correct,
            "ATS_pick": ats_pick,
            "ATS_correct": ats_correct,
            "OU_pick": ou_pick,
            "OU_correct": ou_correct
        })

    # ------------------------------------------------------------
    # Compute final accuracy
    # ------------------------------------------------------------

    accuracy = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tracked_games": len(results),

        "SU_accuracy": round((total_su_correct / total_su * 100), 2) if total_su else None,
        "ATS_accuracy": round((total_ats_correct / total_ats * 100), 2) if total_ats else None,
        "OU_accuracy": round((total_ou_correct / total_ou * 100), 2) if total_ou else None,

        "raw": results
    }

    print("📊 Accuracy:", json.dumps(accuracy, indent=2))

    # Append to log
    log = []
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            log = json.load(f)

    log.append(accuracy)

    with open(OUTPUT, "w") as f:
        json.dump(log, f, indent=2)

    print(f"💾 Accuracy logged → {OUTPUT}")


# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    print(f"[🏈] Tracking accuracy at {datetime.now(timezone.utc).isoformat()}...")
    main()
