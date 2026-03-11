#!/usr/bin/env python3
"""
track_accuracy.py
Tracks prediction accuracy from LOCKED picks vs final scores.
Uses predictions_locked.json (picks frozen at game time).
Matches against completed games in combined.json.

For old picks without high_conf flags, re-simulates with current model
to get what the current model WOULD have picked.

Outputs: accuracy.json with per-sport and overall SU/ATS/O/U records,
         tracking both ALL picks and HIGH-CONFIDENCE picks separately.
"""

import json, os
from datetime import datetime, timezone, timedelta
from monte_carlo import simulate_and_pick, safe_float

OUTPUT = "accuracy.json"
COMBINED_FILE = "combined.json"
SCORES_FILE = "completed_scores.json"
LOCKED_FILE = "predictions_locked.json"
ARCHIVE_FILE = "predictions_archive.json"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        if default is None:
            print(f"[accuracy] Error loading {path}: {e}")
        return default


def make_stats_bucket():
    return {
        "SU": {"wins": 0, "losses": 0},
        "ATS": {"wins": 0, "losses": 0, "pushes": 0},
        "OU": {"wins": 0, "losses": 0, "pushes": 0},
    }


def grade_ats(picks, pred, odds, home_score, away_score):
    """Grade an ATS pick. Returns 'W', 'L', 'P', or None."""
    ats_pick = picks.get("ats_pick")
    spread_line = safe_float(odds.get("spread"))
    if not ats_pick or spread_line is None:
        return None

    actual_margin = home_score - away_score
    home_team = pred.get("home_team") or {}
    home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
    pick_is_home = (ats_pick == home_name) or (picks.get("ats_pick_abbr") == pred.get("home"))

    home_covered = actual_margin + spread_line > 0
    push = abs(actual_margin + spread_line) < 0.01

    if push:
        return "P"
    if pick_is_home:
        return "W" if home_covered else "L"
    else:
        return "W" if (not home_covered) else "L"


def grade_ou(picks, odds, home_score, away_score, sport=""):
    """Grade an O/U pick. Returns 'W', 'L', 'P', or None."""
    ou_pick = picks.get("ou_pick")
    total_line = safe_float(odds.get("total"))
    if not ou_pick or total_line is None or total_line < 0.5:
        return None  # Skip if no line or line is 0

    actual_total = home_score + away_score

    # Sanity check: reject scores that look like partials
    min_totals = {"NBA": 160, "NCAAB": 100, "NCAAW": 90, "NFL": 6, "NCAAF": 10}
    min_t = min_totals.get(sport.upper(), 0)
    if actual_total < min_t:
        return None  # Bad score data

    push = abs(actual_total - total_line) < 0.01

    if push:
        return "P"
    if (ou_pick == "Over" and actual_total > total_line) or \
       (ou_pick == "Under" and actual_total < total_line):
        return "W"
    return "L"


def update_stats(stats_dict, sport, category, result):
    """Update stats for both ALL and sport-specific buckets."""
    if result == "W":
        stats_dict["ALL"][category]["wins"] += 1
        stats_dict[sport][category]["wins"] += 1
    elif result == "L":
        stats_dict["ALL"][category]["losses"] += 1
        stats_dict[sport][category]["losses"] += 1
    elif result == "P":
        stats_dict["ALL"][category]["pushes"] += 1
        stats_dict[sport][category]["pushes"] += 1


def resim_picks(pred):
    """Re-simulate a game with the current model to get updated picks."""
    game = dict(pred)
    sport = (pred.get("sport") or "").lower()
    game["sport"] = sport
    if "odds" not in game or game["odds"] is None:
        game["odds"] = pred.get("odds") or {}
    try:
        result = simulate_and_pick(game, n_sims=5000)
        return result.get("picks", {})
    except Exception:
        return None


def main():
    # Load completed game scores from persistent file (primary source)
    scores_data = load_json(SCORES_FILE, {})
    completed = {}

    for gid, score in scores_data.get("scores", {}).items():
        completed[str(gid)] = {
            "home_score": score["home_score"],
            "away_score": score["away_score"],
            "sport": (score.get("sport") or "").upper(),
            "date_utc": score.get("date_utc"),
            "odds": score.get("odds") or {},
        }

    # Also check combined.json for newly completed games
    combined = load_json(COMBINED_FILE, {})
    games = combined.get("data", [])

    for g in games:
        gid = str(g.get("id") or g.get("event_id") or "")
        if not gid or gid in completed:
            continue
        home_score = safe_float(g.get("home_score"))
        away_score = safe_float(g.get("away_score"))
        if home_score is None or away_score is None:
            continue
        completed[gid] = {
            "home_score": home_score,
            "away_score": away_score,
            "sport": (g.get("sport") or "").upper(),
            "date_utc": g.get("date_utc"),
            "odds": g.get("odds") or {},
        }

    print(f"[accuracy] Found {len(completed)} completed games with scores")

    # Load locked picks (primary) + archive (fallback)
    all_preds = []
    for filepath in [LOCKED_FILE, ARCHIVE_FILE]:
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath) as f:
                data = json.load(f)
            preds = data.get("locked", data.get("predictions", []))
            all_preds.extend(preds)
            print(f"[accuracy] Loaded {len(preds)} predictions from {filepath}")
        except Exception as e:
            print(f"[accuracy] Error loading {filepath}: {e}")

    if not all_preds:
        print("[accuracy] No locked picks found")
        with open(OUTPUT, "w") as f:
            json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "sports": {}, "predictions_graded": 0}, f, indent=2)
        return

    # Deduplicate by ID
    seen_ids = set()
    unique_preds = []
    for p in all_preds:
        pid = str(p.get("id") or "")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique_preds.append(p)

    # All sports we track
    sports = ["ALL", "NFL", "NCAAF", "NBA", "NCAAB", "NCAAW", "NHL", "MLB", "UFC"]

    # Two stat trackers: all picks and high-confidence only
    stats_all = {s: make_stats_bucket() for s in sports}
    stats_high = {s: make_stats_bucket() for s in sports}

    graded = 0
    resimmed = 0
    results_detail = []

    for pred in unique_preds:
        pid = str(pred.get("id") or "")
        if pid not in completed:
            continue

        final = completed[pid]
        sport = final["sport"]
        if sport not in stats_all:
            continue

        home_score = final["home_score"]
        away_score = final["away_score"]

        # Skip games with obviously bad/partial scores
        total = home_score + away_score
        min_totals = {"NBA": 160, "NCAAB": 100, "NCAAW": 90, "NFL": 6, "NCAAF": 10}
        if total < min_totals.get(sport, 0):
            continue

        # Skip if score < 50% of total line (likely partial/in-progress score)
        game_odds = final.get("odds") or pred.get("odds") or {}
        total_line_check = safe_float(game_odds.get("total"))
        if total_line_check and total_line_check > 0 and total < total_line_check * 0.5:
            continue

        graded += 1

        original_picks = pred.get("picks") or {}
        odds = final.get("odds") or pred.get("odds") or {}
        is_new_model = original_picks.get("ats_high_conf") is not None

        # For old-model picks, re-simulate with current model for SU/ATS
        # but keep original O/U picks (re-sim has no features to shift totals)
        if not is_new_model:
            new_picks = resim_picks(pred)
            if new_picks:
                # Use re-simmed picks for SU/ATS but preserve original O/U
                picks = new_picks
                picks["ou_pick"] = original_picks.get("ou_pick")
                picks["ou_confidence"] = original_picks.get("ou_confidence", 50)
                picks["ou_high_conf"] = False  # old picks are never high-conf
                resimmed += 1
            else:
                picks = original_picks
        else:
            picks = original_picks

        game_date = final.get("date_utc") or pred.get("date_utc")
        result_entry = {
            "id": pid,
            "sport": sport,
            "date": game_date,
            "matchup": pred.get("matchup") or pred.get("shortName") or "",
        }

        # --- SU ---
        su_abbr = picks.get("su_pick_abbr")
        if su_abbr:
            home_abbr = pred.get("home") or ""
            if isinstance(pred.get("home_team"), dict):
                home_abbr = pred["home_team"].get("abbr", home_abbr)

            if home_score != away_score:
                winner_abbr = home_abbr if home_score > away_score else (
                    pred.get("away") or (pred.get("away_team", {}).get("abbr", "") if isinstance(pred.get("away_team"), dict) else "")
                )
                su_result = "W" if su_abbr == winner_abbr else "L"
                update_stats(stats_all, sport, "SU", su_result)
                update_stats(stats_high, sport, "SU", su_result)
                result_entry["su"] = su_result

        # --- ATS ---
        ats_result = grade_ats(picks, pred, odds, home_score, away_score)
        ats_is_high = picks.get("ats_high_conf", False)

        if ats_result:
            update_stats(stats_all, sport, "ATS", ats_result)
            if ats_is_high:
                update_stats(stats_high, sport, "ATS", ats_result)
            result_entry["ats"] = ats_result
            result_entry["ats_high_conf"] = ats_is_high

        # --- O/U ---
        ou_result = grade_ou(picks, odds, home_score, away_score, sport)
        ou_is_high = picks.get("ou_high_conf", False)

        if ou_result:
            update_stats(stats_all, sport, "OU", ou_result)
            if ou_is_high:
                update_stats(stats_high, sport, "OU", ou_result)
            result_entry["ou"] = ou_result
            result_entry["ou_high_conf"] = ou_is_high

        results_detail.append(result_entry)

    # Build output with both all and high-conf stats
    def build_sport_stats(st):
        out = {}
        for s in sports:
            su = st[s]["SU"]
            ats = st[s]["ATS"]
            ou = st[s]["OU"]
            su_total = su["wins"] + su["losses"]
            ats_total = ats["wins"] + ats["losses"]
            ou_total = ou["wins"] + ou["losses"]
            out[s] = {
                "SU_pct": round(su["wins"] / su_total * 100, 1) if su_total else 0,
                "SU_record": f"{su['wins']}-{su['losses']}",
                "SU_wins": su["wins"],
                "SU_total": su_total,
                "ATS_pct": round(ats["wins"] / ats_total * 100, 1) if ats_total else 0,
                "ATS_record": f"{ats['wins']}-{ats['losses']}-{ats['pushes']}",
                "ATS_wins": ats["wins"],
                "ATS_total": ats_total,
                "OU_pct": round(ou["wins"] / ou_total * 100, 1) if ou_total else 0,
                "OU_record": f"{ou['wins']}-{ou['losses']}-{ou['pushes']}",
                "OU_wins": ou["wins"],
                "OU_total": ou_total,
            }
        return out

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "predictions_graded": graded,
        "sports": build_sport_stats(stats_all),
        "high_confidence": build_sport_stats(stats_high),
        "results": results_detail[-200:],
    }

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    # Print summary
    def print_line(label, st):
        su = st["ALL"]["SU"]
        ats = st["ALL"]["ATS"]
        ou = st["ALL"]["OU"]
        su_t = su["wins"] + su["losses"]
        ats_t = ats["wins"] + ats["losses"]
        ou_t = ou["wins"] + ou["losses"]
        print(f"  {label}:")
        print(f"    SU:  {su['wins']}-{su['losses']} ({round(su['wins']/su_t*100,1) if su_t else 0}%)")
        print(f"    ATS: {ats['wins']}-{ats['losses']}-{ats['pushes']} ({round(ats['wins']/ats_t*100,1) if ats_t else 0}%) [{ats_t} graded]")
        print(f"    O/U: {ou['wins']}-{ou['losses']}-{ou['pushes']} ({round(ou['wins']/ou_t*100,1) if ou_t else 0}%) [{ou_t} graded]")

    print(f"[accuracy] Graded {graded} picks ({resimmed} re-simulated with current model)")
    print_line("ALL PICKS", stats_all)
    print_line("HIGH CONFIDENCE", stats_high)


if __name__ == "__main__":
    main()
