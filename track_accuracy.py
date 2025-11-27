#!/usr/bin/env python3
"""
track_accuracy.py
Evaluates ongoing accuracy for Straight Up (SU), ATS, and O/U based on
YOUR model picks (from predictions.json) and final scores from the ESPN Core API.

- Reads combined.json (games + odds + weather)
- Reads predictions.json (model outputs)
- Reconstructs the same picks logic used by index.html
- Only tracks games with game date AFTER 2025-11-26
- Only counts a category (SU / ATS / O/U) if a pick actually exists
- Logs overall + per-sport accuracy to performance_log.json
"""

import json
import os
import re
from datetime import datetime, date, timezone

import requests

OUTPUT = "performance_log.json"
CUTOFF_GAME_DATE = date(2025, 11, 26)  # only track games AFTER this date

# --- Helpers ---------------------------------------------------------------

def get_json(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  Failed {url}: {e}")
        return None


def safe_number(val):
    if isinstance(val, (int, float)) and not (val is None):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    return None


def clamp(v, min_v, max_v):
    return max(min_v, min(max_v, v))


def get_team_name(game, side):
    """
    Try to normalize team names from combined.json structure.
    side: "home" or "away"
    """
    key_team = f"{side}_team"
    t = game.get(key_team)

    # Could be a dict (with .name or .displayName)
    if isinstance(t, dict):
        return t.get("name") or t.get("displayName") or t.get("abbreviation") or ""

    # Could be a plain string
    if isinstance(t, str):
        return t

    # Fallback keys
    alt = game.get(side)
    if isinstance(alt, str):
        return alt

    return ""


def parse_game_date(game):
    """
    Extract a game date from combined.json record and return a datetime.date.
    Only use the date portion (YYYY-MM-DD).
    If parsing fails, return None.
    """
    date_str = (
        game.get("date_utc")
        or game.get("date_local")
        or game.get("commence_time")
        or ""
    )
    if not isinstance(date_str, str) or len(date_str) < 10:
        return None

    try:
        # Assume first 10 chars are "YYYY-MM-DD"
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return d
    except Exception:
        return None


def build_spread_info(game, pred):
    """
    Mirror the JS buildSpreadInfo logic.

    Returns:
      dict with {favorite_name, dog_name, line, home_name, away_name}
      or None if we can't resolve a real spread.
    """
    odds = (game.get("odds") or pred.get("odds") or {}) if pred else (game.get("odds") or {})
    details = odds.get("details") or ""

    home_name = get_team_name(game, "home") or (pred.get("home") if pred else None) or "Home"
    away_name = get_team_name(game, "away") or (pred.get("away") if pred else None) or "Away"

    spread_mag = safe_number(odds.get("spread"))
    favorite_name = None

    # Parse "<Team Name> -7.5" style from details
    m = re.search(r"([A-Za-z.&\s]+)\s*([+-]?\d+(\.\d+)?)", details)
    if m:
        team_token = m.group(1).strip()
        line_str = m.group(2)
        try:
            line_val = float(line_str)
        except ValueError:
            line_val = None

        if line_val is not None:
            spread_mag = abs(line_val)
            tok = team_token.upper()

            def matches(label: str) -> bool:
                if not label:
                    return False
                up = label.upper()
                return tok in up or up in tok

            if matches(home_name):
                favorite_name = home_name
            elif matches(away_name):
                favorite_name = away_name

    if not spread_mag or not favorite_name:
        return None

    dog_name = away_name if favorite_name == home_name else home_name

    return {
        "favorite_name": favorite_name,
        "dog_name": dog_name,
        "line": spread_mag,
        "home_name": home_name,
        "away_name": away_name,
    }


def compute_model_picks(game, pred):
    """
    Rebuild the same picks that the JS front-end makes, as closely as possible.

    Returns dict:
    {
      "sport": "ncaaf",
      "home_name": ...,
      "away_name": ...,
      "su_team": <name or None>,
      "su_conf": <float or None>,
      "ats_team": <name or None>,
      "ats_spread": <signed float or None>,  # e.g. -7.5 or +7.5
      "ats_conf": <float or None>,
      "total_pick": "Over"/"Under"/None,
      "total_line": <float or None>,
      "total_conf": <float or None>,
    }
    """
    sport_key = game.get("sport_key", "")
    sport = sport_key.split("_")[-1].lower() if sport_key else ""

    home_name = get_team_name(game, "home") or (pred.get("home") if pred else None) or "Home"
    away_name = get_team_name(game, "away") or (pred.get("away") if pred else None) or "Away"

    odds = (game.get("odds") or pred.get("odds") or {}) if pred else (game.get("odds") or {})
    total_line = safe_number(odds.get("total"))

    pred_core = (pred or {}).get("prediction", {}) if pred else {}
    proj_home = safe_number(pred_core.get("projected_home_score"))
    proj_away = safe_number(pred_core.get("projected_away_score"))
    win_prob_home = safe_number(pred_core.get("win_probability_home"))

    model_margin_home = safe_number((pred or {}).get("pred_margin")) if pred else None
    if model_margin_home is None:
        proj_spread = safe_number(pred_core.get("projected_spread"))
        if proj_spread is not None:
            model_margin_home = proj_spread
        elif proj_home is not None and proj_away is not None:
            model_margin_home = proj_home - proj_away

    model_total = safe_number((pred or {}).get("pred_total")) if pred else None
    if model_total is None:
        proj_total = safe_number(pred_core.get("projected_total"))
        if proj_total is not None:
            model_total = proj_total
        elif proj_home is not None and proj_away is not None:
            model_total = proj_home + proj_away

    # --- Straight Up ---
    su_team = None
    su_conf = None

    if win_prob_home is not None:
        if win_prob_home >= 0.5:
            su_team = home_name
            su_conf = round(win_prob_home * 100)
        else:
            su_team = away_name
            su_conf = round((1 - win_prob_home) * 100)
    elif model_margin_home is not None:
        su_team = home_name if model_margin_home >= 0 else away_name
        base = clamp(abs(model_margin_home) * 6.25, 5, 99)
        su_conf = round(base)

    # --- ATS ---
    spread_info = build_spread_info(game, pred) if pred else build_spread_info(game, None)
    ats_team = None
    ats_spread = None
    ats_conf = None
    ats_min_edge = 1.0

    if spread_info and model_margin_home is not None:
        fav_name = spread_info["favorite_name"]
        dog_name = spread_info["dog_name"]
        line = spread_info["line"]
        home_nm = spread_info["home_name"]
        away_nm = spread_info["away_name"]

        # predicted margin from FAVORITE perspective
        if fav_name == home_nm:
            pred_fav_margin = model_margin_home
        else:
            pred_fav_margin = -model_margin_home

        diff = pred_fav_margin - line
        edge_pts = abs(diff)

        if edge_pts >= ats_min_edge:
            covers_favorite = diff >= 0
            side_name = fav_name if covers_favorite else dog_name
            side_spread = -line if covers_favorite else +line

            raw_conf = clamp(edge_pts * 6.25, 5, 99)
            raw_conf = round(raw_conf)

            if raw_conf < 50:
                raw_conf = 100 - raw_conf
                # flip side if we invert confidence
                if covers_favorite:
                    side_name = dog_name
                    side_spread = +line
                else:
                    side_name = fav_name
                    side_spread = -line

            ats_team = side_name
            ats_spread = side_spread
            ats_conf = raw_conf

    # --- TOTAL (O/U) ---
    total_pick = None
    total_conf = None
    total_min_edge = 1.0

    if total_line is not None and model_total is not None:
        diff = model_total - total_line
        edge_pts = abs(diff)

        if edge_pts >= total_min_edge:
            total_pick = "Over" if diff > 0 else "Under"
            raw_conf = clamp(edge_pts * 6.25, 5, 99)
            total_conf = round(raw_conf)

    return {
        "sport": sport,
        "home_name": home_name,
        "away_name": away_name,
        "su_team": su_team,
        "su_conf": su_conf,
        "ats_team": ats_team,
        "ats_spread": ats_spread,
        "ats_conf": ats_conf,
        "total_pick": total_pick,
        "total_line": total_line,
        "total_conf": total_conf,
    }


def map_pick_to_side(team_label, competitors):
    """
    Map a team label (e.g. 'Ole Miss Rebels') to 'home' or 'away'
    using ESPN competitors block.
    Returns 'home', 'away', or None.
    """
    if not team_label:
        return None
    label = team_label.lower()

    for c in competitors:
        team = c.get("team") or {}
        name = (team.get("displayName") or team.get("shortDisplayName") or "").lower()
        if not name:
            continue
        if label in name or name in label:
            return c.get("homeAway")

    return None


# --- Main ------------------------------------------------------------------

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json not found.")
        return

    with open("combined.json", "r") as f:
        combined = json.load(f)
    odds_data = combined.get("data") or combined.get("games") or combined.get("combined") or []

    # Load predictions (for picks)
    preds_map = {}
    if os.path.exists("predictions.json"):
        with open("predictions.json", "r") as f:
            preds_json = json.load(f)
        preds_arr = preds_json.get("data") or preds_json.get("predictions") or []
        for p in preds_arr:
            pid = p.get("id")
            if pid is not None:
                preds_map[str(pid)] = p
    else:
        print("⚠️  predictions.json not found. SU/ATS/O/U picks may be missing.")

    # ESPN Core API league map
    league_map = {
        "nfl": "football/leagues/nfl",
        "ncaaf": "football/leagues/college-football",
        "nba": "basketball/leagues/nba",
        "ncaab": "basketball/leagues/mens-college-basketball",
        "nhl": "hockey/leagues/nhl",
        "mlb": "baseball/leagues/mlb",
    }

    # Group games by sport, skipping pre-cutoff dates
    games_by_sport = {}
    for g in odds_data:
        sport_key = g.get("sport_key", "")
        sport = sport_key.split("_")[-1].lower() if sport_key else ""
        if sport not in league_map:
            continue

        gdate = parse_game_date(g)
        if not gdate or gdate <= CUTOFF_GAME_DATE:
            continue

        games_by_sport.setdefault(sport, []).append(g)

    # Stats accumulators
    overall = {
        "games_checked": 0,  # number of games where we checked at least one pick
        "SU_games": 0,
        "SU_correct": 0,
        "ATS_games": 0,
        "ATS_correct": 0,
        "OU_games": 0,
        "OU_correct": 0,
    }

    by_sport = {}

    # For each sport, fetch events once and match games
    for sport, games in games_by_sport.items():
        league_path = league_map[sport]
        url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
        events_data = get_json(url)
        if not events_data or "items" not in events_data:
            print(f"⚠️  No events found for sport={sport}")
            continue

        # Preload all events for this league
        events = []
        for ev_ref in events_data["items"]:
            if not isinstance(ev_ref, dict) or "$ref" not in ev_ref:
                continue
            ev_url = ev_ref["$ref"]
            ev_data = get_json(ev_url)
            if ev_data:
                events.append(ev_data)

        # Sport-level accumulator
        sport_stats = {
            "games_checked": 0,
            "SU_games": 0,
            "SU_correct": 0,
            "ATS_games": 0,
            "ATS_correct": 0,
            "OU_games": 0,
            "OU_correct": 0,
        }

        for g in games:
            # Attach prediction for this game
            pred = preds_map.get(str(g.get("id")))
            picks = compute_model_picks(g, pred)

            # If no picks at all, skip entirely
            has_any_pick = bool(
                picks["su_team"] or picks["ats_team"] or picks["total_pick"]
            )
            if not has_any_pick:
                continue

            # Find matching ESPN event by team names
            home_name = get_team_name(g, "home")
            away_name = get_team_name(g, "away")

            event_match = None
            for ev in events:
                name = ev.get("name", "")
                if (home_name and home_name in name) or (away_name and away_name in name):
                    event_match = ev
                    break

            if not event_match:
                continue

            comps = (event_match.get("competitions") or [{}])[0].get("competitors") or []
            if len(comps) < 2:
                continue

            # Extract home/away scores
            home_score = 0.0
            away_score = 0.0
            for c in comps:
                score_val = safe_number(c.get("score", 0)) or 0.0
                if c.get("homeAway") == "home":
                    home_score = score_val
                elif c.get("homeAway") == "away":
                    away_score = score_val

            total_score = home_score + away_score

            # -- Evaluate SU correctness (only if we made a SU pick)
            if picks["su_team"]:
                su_side = map_pick_to_side(picks["su_team"], comps)
                if su_side:
                    sport_stats["SU_games"] += 1
                    overall["SU_games"] += 1

                    if home_score > away_score and su_side == "home":
                        sport_stats["SU_correct"] += 1
                        overall["SU_correct"] += 1
                    elif away_score > home_score and su_side == "away":
                        sport_stats["SU_correct"] += 1
                        overall["SU_correct"] += 1

            # -- Evaluate ATS correctness (only if we made an ATS pick)
            if picks["ats_team"] and picks["ats_spread"] is not None:
                ats_side = map_pick_to_side(picks["ats_team"], comps)
                if ats_side:
                    sport_stats["ATS_games"] += 1
                    overall["ATS_games"] += 1

                    margin = (
                        home_score - away_score
                        if ats_side == "home"
                        else away_score - home_score
                    )
                    # Bet wins if (margin + spread) > 0 (ignore pushes)
                    if margin + picks["ats_spread"] > 0:
                        sport_stats["ATS_correct"] += 1
                        overall["ATS_correct"] += 1

            # -- Evaluate O/U correctness (only if we made a total pick)
            if picks["total_pick"] and picks["total_line"] is not None:
                sport_stats["OU_games"] += 1
                overall["OU_games"] += 1

                if picks["total_pick"] == "Over" and total_score > picks["total_line"]:
                    sport_stats["OU_correct"] += 1
                    overall["OU_correct"] += 1
                elif picks["total_pick"] == "Under" and total_score < picks["total_line"]:
                    sport_stats["OU_correct"] += 1
                    overall["OU_correct"] += 1

            # Count this game as checked if at least one category was evaluated
            if (
                picks["su_team"]
                or (picks["ats_team"] and picks["ats_spread"] is not None)
                or (picks["total_pick"] and picks["total_line"] is not None)
            ):
                sport_stats["games_checked"] += 1
                overall["games_checked"] += 1

        by_sport[sport] = sport_stats

    def pct(correct, games):
        return round((correct / games * 100.0), 2) if games else 0.0

    accuracy = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cutoff_game_date": CUTOFF_GAME_DATE.isoformat(),
        "games_checked": overall["games_checked"],
        "SU_games": overall["SU_games"],
        "SU_correct": overall["SU_correct"],
        "SU_accuracy": pct(overall["SU_correct"], overall["SU_games"]),
        "ATS_games": overall["ATS_games"],
        "ATS_correct": overall["ATS_correct"],
        "ATS_accuracy": pct(overall["ATS_correct"], overall["ATS_games"]),
        "OU_games": overall["OU_games"],
        "OU_correct": overall["OU_correct"],
        "OU_accuracy": pct(overall["OU_correct"], overall["OU_games"]),
        "by_sport": {},
    }

    for sport, st in by_sport.items():
        accuracy["by_sport"][sport] = {
            "games_checked": st["games_checked"],
            "SU_games": st["SU_games"],
            "SU_correct": st["SU_correct"],
            "SU_accuracy": pct(st["SU_correct"], st["SU_games"]),
            "ATS_games": st["ATS_games"],
            "ATS_correct": st["ATS_correct"],
            "ATS_accuracy": pct(st["ATS_correct"], st["ATS_games"]),
            "OU_games": st["OU_games"],
            "OU_correct": st["OU_correct"],
            "OU_accuracy": pct(st["OU_correct"], st["OU_games"]),
        }

    print(f"[📊] Accuracy summary since {CUTOFF_GAME_DATE.isoformat()}:")
    print(json.dumps(accuracy, indent=2))

    log = []
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, "r") as f:
                log = json.load(f)
            if not isinstance(log, list):
                log = []
        except Exception:
            log = []

    log.append(accuracy)
    with open(OUTPUT, "w") as f:
        json.dump(log, f, indent=2)

    print(f"[💾] Logged accuracy → {OUTPUT}")


if __name__ == "__main__":
    print(f"[🏈] Tracking accuracy at {datetime.now(timezone.utc).isoformat()}...")
    main()
