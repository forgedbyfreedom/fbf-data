#!/usr/bin/env python3
"""
referee_trends.py

Builds referee/crew trend profiles across:
NFL, NCAAF, NBA, NCAAB, NCAAW, MLB, NHL, UFC

Outputs:
  referees.json

What it tracks (per official + per crew):
- games_seen
- home_penalties / away_penalties
- home_penalty_bias_pct
- penalties_per_game
- avg_total_points
- over_rate / under_rate (if totals exist in odds history)
- ats_home_cover_rate / ats_away_cover_rate (if spreads exist in odds history)

Requirements:
  pip install requests
"""

import os, json, requests
from datetime import datetime, timezone
from collections import defaultdict

TIMEOUT = 12
OUTPUT = "referees.json"

# -------- ESPN Core API league roots --------
LEAGUES = {
    "americanfootball_nfl":   "football/leagues/nfl",
    "americanfootball_ncaaf": "football/leagues/college-football",
    "basketball_nba":         "basketball/leagues/nba",
    "basketball_ncaab":       "basketball/leagues/mens-college-basketball",
    "basketball_ncaaw":       "basketball/leagues/womens-college-basketball",
    "baseball_mlb":           "baseball/leagues/mlb",
    "icehockey_nhl":          "hockey/leagues/nhl",
    "mma_ufc":                "mma/leagues/ufc",
}

# Where you store odds snapshots over time (optional but enables ATS + OU trends)
ODDS_HISTORY_DIR = "odds_history"  # you can create this later

def get_json(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def load_odds_history():
    """
    Optional: load stored odds snapshots so we can compute ATS and O/U.
    Expected shape (per snapshot file):
      {"timestamp": "...", "data": [ {matchup, fav_team, dog_team, fav_spread, total, commence_time, ...}, ... ]}

    We index by normalized matchup + commence_time.
    """
    hist = {}
    if not os.path.isdir(ODDS_HISTORY_DIR):
        return hist

    for fn in os.listdir(ODDS_HISTORY_DIR):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(ODDS_HISTORY_DIR, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                for g in payload.get("data", []):
                    key = normalize_game_key(g)
                    if key:
                        hist[key] = g
        except Exception:
            continue
    return hist

def normalize_game_key(g):
    """
    Create a stable key from matchup + time.
    """
    matchup = (g.get("matchup") or "").strip().lower()
    t = (g.get("commence_time") or "").strip()
    if not matchup or not t:
        return None
    return f"{matchup}|{t}"

def extract_scores(event):
    """
    Return (home_team, away_team, home_score, away_score)
    """
    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c.get("homeAway") == "home")
        away = next(c for c in competitors if c.get("homeAway") == "away")
        home_team = home["team"]["displayName"]
        away_team = away["team"]["displayName"]
        home_score = float(home.get("score") or 0)
        away_score = float(away.get("score") or 0)
        return home_team, away_team, home_score, away_score
    except Exception:
        return None, None, None, None

def extract_officials(event):
    """
    ESPN Core API:
      competitions[0].officials -> list of refs/officials/judges

    Returns list of dicts:
      [{"id": "...", "name": "...", "role": "...", "crew": "..."}]
    """
    officials = []
    try:
        comp = event["competitions"][0]
        for o in comp.get("officials", []) or []:
            person = o.get("person") or {}
            oid = person.get("id") or o.get("id") or None
            name = person.get("fullName") or o.get("fullName") or o.get("displayName")
            role = o.get("position") or o.get("role") or "Official"
            crew = o.get("crew") or o.get("crewId") or None
            if name:
                officials.append({
                    "id": str(oid) if oid else name.lower().replace(" ", "_"),
                    "name": name,
                    "role": role,
                    "crew": str(crew) if crew else None,
                })
    except Exception:
        pass
    return officials

def extract_penalties(event):
    """
    Penalties are not standardized in every sport.
    For football/basketball/hockey/baseball:
      competitions[0].competitors[*].statistics
    We look for common penalty stats:
      "penalties", "penaltyYards", "fouls", "pim", etc.
    Returns:
      {"home": pen_count, "away": pen_count}
    """
    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        out = {"home": 0.0, "away": 0.0}

        for c in competitors:
            side = c.get("homeAway")
            stats = c.get("statistics") or []
            val = 0.0
            for s in stats:
                k = (s.get("name") or "").lower()
                if k in ("penalties", "fouls", "personalFouls", "pim"):
                    val += float(s.get("value") or 0)
            if side == "home":
                out["home"] += val
            elif side == "away":
                out["away"] += val

        return out
    except Exception:
        return {"home": 0.0, "away": 0.0}

def is_final(event):
    try:
        status = event.get("status", {}).get("type", {}).get("completed")
        return bool(status)
    except Exception:
        return False

def fetch_events_for_league(league_path, days=7):
    """
    Pull the 'events' collection and then each event details.
    ESPN returns items with $ref.
    """
    base = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
    events_index = get_json(base)
    if not events_index:
        return []

    items = events_index.get("items") or []
    out = []
    for it in items:
        ref = it.get("$ref")
        if not ref:
            continue
        ev = get_json(ref)
        if ev:
            out.append(ev)
    return out

def main():
    odds_hist = load_odds_history()

    # Aggregation buckets
    officials_stats = defaultdict(lambda: {
        "name": None,
        "roles": defaultdict(int),
        "games_seen": 0,
        "home_penalties": 0.0,
        "away_penalties": 0.0,
        "penalties_per_game": 0.0,
        "total_points_sum": 0.0,
        "totals_count": 0,
        "over_count": 0,
        "under_count": 0,
        "ats_count": 0,
        "home_cover_count": 0,
        "away_cover_count": 0,
        "crews": defaultdict(int),
        "sports": defaultdict(int),
        "last_seen": None,
    })

    crew_stats = defaultdict(lambda: {
        "crew_id": None,
        "games_seen": 0,
        "home_penalties": 0.0,
        "away_penalties": 0.0,
        "penalties_per_game": 0.0,
        "total_points_sum": 0.0,
        "totals_count": 0,
        "over_count": 0,
        "under_count": 0,
        "ats_count": 0,
        "home_cover_count": 0,
        "away_cover_count": 0,
        "last_seen": None,
        "sports": defaultdict(int),
    })

    # -------- Process each league --------
    for sport_key, league_path in LEAGUES.items():
        print(f"[⏱️] Fetching officials for {sport_key}...")
        events = fetch_events_for_league(league_path)

        for ev in events:
            # only completed games contribute to trends
            if not is_final(ev):
                continue

            home_team, away_team, home_score, away_score = extract_scores(ev)
            if home_team is None:
                continue
            total_points = (home_score + away_score)

            officials = extract_officials(ev)
            if not officials:
                continue

            penalties = extract_penalties(ev)

            # Build optional ATS / OU from odds history (if present)
            odds_key = normalize_game_key({
                "matchup": ev.get("name", "").replace(" at ", "@"),
                "commence_time": ev.get("date"),
            })
            odds = odds_hist.get(odds_key)

            total_line = odds.get("total") if odds else None
            spread = odds.get("fav_spread") if odds else None
            fav_team = odds.get("fav_team") if odds else None
            dog_team = odds.get("dog_team") if odds else None

            # Determine ATS outcome if we have spread + teams
            ats_home_cover = ats_away_cover = None
            if odds and spread is not None and fav_team and dog_team:
                fav_score = home_score if fav_team == home_team else away_score
                dog_score = away_score if dog_team == away_team else home_score
                margin = fav_score - dog_score
                fav_covers = margin > abs(float(spread))
                ats_home_cover = fav_covers if fav_team == home_team else (not fav_covers)
                ats_away_cover = not ats_home_cover

            # Determine OU outcome if total line exists
            is_over = is_under = None
            if total_line is not None:
                is_over = total_points > float(total_line)
                is_under = not is_over

            # Update official + crew aggregates
            for o in officials:
                oid = o["id"]
                st = officials_stats[oid]
                st["name"] = o["name"]
                st["roles"][o["role"]] += 1
                st["games_seen"] += 1
                st["home_penalties"] += penalties["home"]
                st["away_penalties"] += penalties["away"]
                st["total_points_sum"] += total_points
                st["totals_count"] += 1
                st["sports"][sport_key] += 1
                st["last_seen"] = ev.get("date")

                if o.get("crew"):
                    st["crews"][o["crew"]] += 1

                if is_over is not None:
                    st["over_count"] += int(is_over)
                    st["under_count"] += int(is_under)

                if ats_home_cover is not None:
                    st["ats_count"] += 1
                    st["home_cover_count"] += int(ats_home_cover)
                    st["away_cover_count"] += int(ats_away_cover)

                # Crew stats
                crew_id = o.get("crew")
                if crew_id:
                    cs = crew_stats[crew_id]
                    cs["crew_id"] = crew_id
                    cs["games_seen"] += 1
                    cs["home_penalties"] += penalties["home"]
                    cs["away_penalties"] += penalties["away"]
                    cs["total_points_sum"] += total_points
                    cs["totals_count"] += 1
                    cs["sports"][sport_key] += 1
                    cs["last_seen"] = ev.get("date")

                    if is_over is not None:
                        cs["over_count"] += int(is_over)
                        cs["under_count"] += int(is_under)

                    if ats_home_cover is not None:
                        cs["ats_count"] += 1
                        cs["home_cover_count"] += int(ats_home_cover)
                        cs["away_cover_count"] += int(ats_away_cover)

    # -------- Finalize computed metrics --------
    officials_out = []
    for oid, st in officials_stats.items():
        g = st["games_seen"] or 1
        hp = st["home_penalties"]
        ap = st["away_penalties"]
        totp = st["totals_count"] or 1
        ats = st["ats_count"] or 0

        officials_out.append({
            "id": oid,
            "name": st["name"],
            "primary_roles": dict(st["roles"]),
            "sports": dict(st["sports"]),
            "games_seen": st["games_seen"],
            "home_penalties": round(hp, 3),
            "away_penalties": round(ap, 3),
            "penalties_per_game": round((hp + ap) / g, 3),
            "home_penalty_bias_pct": round(((hp - ap) / max(hp + ap, 1)) * 100, 2),

            "avg_total_points": round(st["total_points_sum"] / totp, 3),
            "over_rate": round((st["over_count"] / totp) * 100, 2) if totp else None,
            "under_rate": round((st["under_count"] / totp) * 100, 2) if totp else None,

            "ats_samples": ats,
            "ats_home_cover_rate": round((st["home_cover_count"] / ats) * 100, 2) if ats else None,
            "ats_away_cover_rate": round((st["away_cover_count"] / ats) * 100, 2) if ats else None,

            "crews_seen": sorted(st["crews"].keys()),
            "last_seen": st["last_seen"],
        })

    crews_out = []
    for cid, cs in crew_stats.items():
        g = cs["games_seen"] or 1
        hp = cs["home_penalties"]
        ap = cs["away_penalties"]
        totp = cs["totals_count"] or 1
        ats = cs["ats_count"] or 0

        crews_out.append({
            "crew_id": cid,
            "sports": dict(cs["sports"]),
            "games_seen": cs["games_seen"],
            "home_penalties": round(hp, 3),
            "away_penalties": round(ap, 3),
            "penalties_per_game": round((hp + ap) / g, 3),
            "home_penalty_bias_pct": round(((hp - ap) / max(hp + ap, 1)) * 100, 2),

            "avg_total_points": round(cs["total_points_sum"] / totp, 3),
            "over_rate": round((cs["over_count"] / totp) * 100, 2) if totp else None,
            "under_rate": round((cs["under_count"] / totp) * 100, 2) if totp else None,

            "ats_samples": ats,
            "ats_home_cover_rate": round((cs["home_cover_count"] / ats) * 100, 2) if ats else None,
            "ats_away_cover_rate": round((cs["away_cover_count"] / ats) * 100, 2) if ats else None,

            "last_seen": cs["last_seen"],
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "source": "ESPN_CORE_API",
        "notes": "ATS/O-U trends require odds_history snapshots. Penalty + total tendencies always available when ESPN exposes officials.",
        "officials": sorted(officials_out, key=lambda x: x["games_seen"], reverse=True),
        "crews": sorted(crews_out, key=lambda x: x["games_seen"], reverse=True),
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[✅] Wrote {OUTPUT} with {len(officials_out)} officials and {len(crews_out)} crews.")

if __name__ == "__main__":
    main()
