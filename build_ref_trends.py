#!/usr/bin/env python3
"""
build_ref_trends.py
Creates enriched referee trend statistics from historical_results.json.

For each referee with 10+ games, calculates:
- home_win_pct: % of games where home team won
- over_pct: % of games that went over the total
- fav_cover_pct: % of games where favorite covered the spread
- avg_total: mean total points in games officiated
- avg_margin: mean margin of victory (absolute)
- total_stdev: standard deviation of totals (consistency)
- recent_over_pct: over % in last 20 games (recent form)
- recent_home_win_pct: home win % in last 20 games
- by_sport: sport-specific breakdowns

Output: referee_trends.json
"""

import json, re, os, math
from datetime import datetime, timezone

HISTORICAL_FILE = "historical_results.json"
COMBINED_FILE = "combined.json"
OUTPUT = "referee_trends.json"
MIN_GAMES = 10
RECENT_WINDOW = 20  # last N games for recent form


def normalize_name(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def stdev(values):
    """Calculate population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)  # sample stdev
    return math.sqrt(variance)


def main():
    # Load historical results (which now include officials)
    games = []
    for filepath in [HISTORICAL_FILE, COMBINED_FILE]:
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            for g in data.get("data", []):
                officials = g.get("officials") or []
                if not officials:
                    continue
                # Need scores for stats
                home = g.get("home_team") or {}
                away = g.get("away_team") or {}
                home_score = home.get("score") if isinstance(home, dict) else g.get("home_score")
                away_score = away.get("score") if isinstance(away, dict) else g.get("away_score")
                if home_score is None or away_score is None:
                    continue
                games.append({
                    "officials": officials,
                    "home_score": float(home_score),
                    "away_score": float(away_score),
                    "spread": g.get("spread"),
                    "total": g.get("total"),
                    "favorite": g.get("favorite"),
                    "ats_result": g.get("ats_result"),
                    "ou_result": g.get("ou_result"),
                    "home_abbr": home.get("abbr") if isinstance(home, dict) else "",
                    "away_abbr": away.get("abbr") if isinstance(away, dict) else "",
                    "sport": (g.get("sport") or "").lower(),
                    "date_utc": g.get("date_utc") or "",
                })
        except Exception as e:
            print(f"[ref_trends] Error loading {filepath}: {e}")

    if not games:
        print("[ref_trends] No games with officials found, writing empty trends")
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "historical_results.json",
            "refs": {},
        }
        with open(OUTPUT, "w") as f:
            json.dump(out, f, indent=2)
        return

    # Sort games by date for recent form calculation
    games.sort(key=lambda g: g.get("date_utc") or "")

    # Accumulate stats per referee
    # Each ref tracks: overall stats + per-sport stats + ordered game list for recent form
    ref_stats = {}

    for g in games:
        officials = g["officials"]
        home_score = g["home_score"]
        away_score = g["away_score"]
        home_won = home_score > away_score
        total_pts = home_score + away_score
        margin = abs(home_score - away_score)
        game_total = g.get("total")
        ats_result = g.get("ats_result", "")
        ou_result = g.get("ou_result", "")
        sport = g.get("sport", "")

        # Determine over/under from result or calculate
        if ou_result:
            went_over = ou_result == "over"
            went_under = ou_result == "under"
        elif game_total is not None:
            try:
                went_over = total_pts > float(game_total)
                went_under = total_pts < float(game_total)
            except (ValueError, TypeError):
                went_over = False
                went_under = False
        else:
            went_over = False
            went_under = False

        # Determine if favorite covered and by how much
        fav_covered = "_covers" in (ats_result or "")
        fav_failed = "_fails" in (ats_result or "")

        # Calculate cover margin (how much did fav cover/fail by)
        fav_cover_margin = None
        spread = g.get("spread")
        favorite = g.get("favorite")
        if spread is not None and favorite:
            try:
                spread_val = float(spread)
                home_abbr = g.get("home_abbr", "")
                away_abbr = g.get("away_abbr", "")
                fav_is_home = (favorite == home_abbr)
                if fav_is_home or favorite == away_abbr:
                    game_margin = home_score - away_score
                    fav_margin = game_margin if fav_is_home else -game_margin
                    fav_cover_margin = fav_margin - spread_val  # positive = covered by this much
            except (ValueError, TypeError):
                pass

        game_entry = {
            "home_won": home_won,
            "went_over": went_over,
            "went_under": went_under,
            "total_pts": total_pts,
            "margin": margin,
            "fav_covered": fav_covered,
            "fav_failed": fav_failed,
            "fav_cover_margin": fav_cover_margin,
            "sport": sport,
            "date_utc": g.get("date_utc", ""),
        }

        for o in officials:
            if isinstance(o, dict):
                name = o.get("name") or o.get("fullName") or o.get("displayName")
            elif isinstance(o, str):
                name = o
            else:
                continue

            if not name:
                continue

            norm = normalize_name(name)
            if norm not in ref_stats:
                ref_stats[norm] = {
                    "name": name,
                    "games_list": [],
                    "by_sport": {},
                }

            ref_stats[norm]["games_list"].append(game_entry)

            # Track by sport
            if sport:
                if sport not in ref_stats[norm]["by_sport"]:
                    ref_stats[norm]["by_sport"][sport] = []
                ref_stats[norm]["by_sport"][sport].append(game_entry)

    def compute_ref_metrics(game_list):
        """Compute metrics from a list of game entries."""
        total_games = len(game_list)
        if total_games == 0:
            return None

        home_wins = sum(1 for g in game_list if g["home_won"])
        overs = sum(1 for g in game_list if g["went_over"])
        unders = sum(1 for g in game_list if g["went_under"])
        fav_covers = sum(1 for g in game_list if g["fav_covered"])
        fav_fails = sum(1 for g in game_list if g["fav_failed"])

        ou_total = overs + unders
        ats_total = fav_covers + fav_fails

        totals = [g["total_pts"] for g in game_list]
        margins = [g["margin"] for g in game_list]
        cover_margins = [g["fav_cover_margin"] for g in game_list if g["fav_cover_margin"] is not None]

        return {
            "games": total_games,
            "home_win_pct": round(home_wins / total_games * 100, 1),
            "over_pct": round(overs / ou_total * 100, 1) if ou_total else 50.0,
            "fav_cover_pct": round(fav_covers / ats_total * 100, 1) if ats_total else 50.0,
            "avg_total": round(sum(totals) / len(totals), 1) if totals else 0.0,
            "avg_margin": round(sum(margins) / len(margins), 1) if margins else 0.0,
            "total_stdev": round(stdev(totals), 1) if len(totals) >= 2 else 0.0,
            "fav_cover_margin_avg": round(sum(cover_margins) / len(cover_margins), 1) if cover_margins else 0.0,
        }

    # Compute percentages, filter to MIN_GAMES
    refs_output = {}
    for norm, s in ref_stats.items():
        game_list = s["games_list"]
        if len(game_list) < MIN_GAMES:
            continue

        metrics = compute_ref_metrics(game_list)
        if not metrics:
            continue

        # Recent form (last RECENT_WINDOW games)
        recent_games = game_list[-RECENT_WINDOW:]
        recent_metrics = compute_ref_metrics(recent_games)

        entry = {
            "name": s["name"],
            **metrics,
            "recent_over_pct": recent_metrics["over_pct"] if recent_metrics else metrics["over_pct"],
            "recent_home_win_pct": recent_metrics["home_win_pct"] if recent_metrics else metrics["home_win_pct"],
        }

        # By-sport breakdown (only include sports with 5+ games)
        by_sport = {}
        for sport_key, sport_games in s["by_sport"].items():
            if len(sport_games) >= 5:
                sport_metrics = compute_ref_metrics(sport_games)
                if sport_metrics:
                    by_sport[sport_key] = {
                        "games": sport_metrics["games"],
                        "over_pct": sport_metrics["over_pct"],
                        "home_win_pct": sport_metrics["home_win_pct"],
                        "avg_total": sport_metrics["avg_total"],
                        "fav_cover_pct": sport_metrics["fav_cover_pct"],
                    }

        if by_sport:
            entry["by_sport"] = by_sport

        refs_output[s["name"]] = entry

    # Enrich with external data sources (NFL penalties, MLB umpire stats)
    enriched = enrich_with_external_data(refs_output)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "historical_results.json + combined.json + external",
        "refs": enriched,
    }

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"[ref_trends] Wrote {OUTPUT}: {len(enriched)} referees with {MIN_GAMES}+ games (from {len(ref_stats)} total)")


def enrich_with_external_data(refs_output):
    """Merge in NFL penalty data and MLB umpire data from scraped files."""

    # --- NFL Referee Penalty Data ---
    nfl_pen_file = "nfl_ref_penalties.json"
    if os.path.exists(nfl_pen_file):
        try:
            with open(nfl_pen_file) as f:
                nfl_data = json.load(f)
            nfl_refs = nfl_data.get("refs", {})
            merged_nfl = 0

            for ref_name, ref_entry in refs_output.items():
                norm_ref = normalize_name(ref_name)
                # Try to match by name
                match = None
                for nfl_name, nfl_ref in nfl_refs.items():
                    if normalize_name(nfl_name) == norm_ref:
                        match = nfl_ref
                        break

                if match:
                    ref_entry["penalties_per_game"] = match.get("career_penalties_per_game", 0)
                    ref_entry["penalty_yards_per_game"] = match.get("career_yards_per_game", 0)
                    ref_entry["home_away_penalty_ratio"] = match.get("home_away_ratio", 1.0)
                    # Key penalty breakdowns
                    key_pens = match.get("key_penalties", {})
                    if key_pens:
                        ref_entry["key_penalties"] = key_pens
                    merged_nfl += 1

            print(f"[ref_trends] Enriched {merged_nfl} refs with NFL penalty data")
        except Exception as e:
            print(f"[ref_trends] Error loading NFL penalties: {e}")

    # --- MLB Umpire Data ---
    mlb_ump_file = "mlb_ump_data.json"
    if os.path.exists(mlb_ump_file):
        try:
            with open(mlb_ump_file) as f:
                mlb_data = json.load(f)
            mlb_umps = mlb_data.get("umps", {})
            merged_mlb = 0

            for ref_name, ref_entry in refs_output.items():
                norm_ref = normalize_name(ref_name)
                match = None
                for ump_name, ump_data in mlb_umps.items():
                    if normalize_name(ump_name) == norm_ref:
                        match = ump_data
                        break

                if match:
                    career = match.get("career", {})
                    recent = match.get("recent", {})
                    ref_entry["ump_runs_per_game"] = career.get("runs_per_game", 0)
                    ref_entry["ump_strike_pct"] = career.get("strike_pct", 0)
                    ref_entry["ump_hr_per_game"] = career.get("hr_per_game", 0)
                    ref_entry["ump_career_over_pct"] = career.get("over_pct", 50.0)
                    ref_entry["ump_recent_over_pct"] = recent.get("over_pct", 50.0)
                    ref_entry["ump_recent_runs_per_game"] = recent.get("runs_per_game", 0)
                    merged_mlb += 1

            # Also add MLB umpires not already in refs_output (from ESPN historical)
            added_mlb = 0
            for ump_name, ump_data in mlb_umps.items():
                norm = normalize_name(ump_name)
                # Check if already exists
                exists = False
                for existing_name in refs_output:
                    if normalize_name(existing_name) == norm:
                        exists = True
                        break
                if exists:
                    continue

                career = ump_data.get("career", {})
                recent = ump_data.get("recent", {})
                games = career.get("games", 0)
                if games < 10:
                    continue

                refs_output[ump_name] = {
                    "name": ump_name,
                    "games": games,
                    "home_win_pct": 50.0,  # not available from covers.com
                    "over_pct": career.get("over_pct", 50.0),
                    "fav_cover_pct": 50.0,  # not available from covers.com
                    "avg_total": 0,
                    "avg_margin": 0,
                    "total_stdev": 0,
                    "recent_over_pct": recent.get("over_pct", 50.0),
                    "recent_home_win_pct": 50.0,
                    "ump_runs_per_game": career.get("runs_per_game", 0),
                    "ump_strike_pct": career.get("strike_pct", 0),
                    "ump_hr_per_game": career.get("hr_per_game", 0),
                    "ump_career_over_pct": career.get("over_pct", 50.0),
                    "ump_recent_over_pct": recent.get("over_pct", 50.0),
                    "ump_recent_runs_per_game": recent.get("runs_per_game", 0),
                }
                added_mlb += 1

            print(f"[ref_trends] Enriched {merged_mlb} refs with MLB ump data, added {added_mlb} new MLB umpires")
        except Exception as e:
            print(f"[ref_trends] Error loading MLB ump data: {e}")

    return refs_output


if __name__ == "__main__":
    main()
