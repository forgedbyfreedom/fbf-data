#!/usr/bin/env python3
"""
track_accuracy.py
Tracks prediction accuracy from LOCKED picks vs final scores.
Uses predictions_locked.json (picks frozen at game time).
Matches against completed games in combined.json.

Outputs: accuracy.json with per-sport and overall SU/ATS/O/U records.
"""

import json, os
from datetime import datetime, timezone, timedelta

OUTPUT = "accuracy.json"
COMBINED_FILE = "combined.json"
LOCKED_FILE = "predictions_locked.json"
ARCHIVE_FILE = "predictions_archive.json"


def safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except (ValueError, TypeError):
        return default


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


def main():
    # Load completed games
    try:
        with open(COMBINED_FILE) as f:
            combined = json.load(f)
    except Exception as e:
        print(f"[accuracy] Cannot load combined.json: {e}")
        return

    games = combined.get("data", [])

    # Build completed games map
    completed = {}
    for g in games:
        gid = str(g.get("id") or g.get("event_id") or "")
        if not gid:
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
        except Exception:
            pass

    if not all_preds:
        print("[accuracy] No locked picks found")
        # Write empty accuracy
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
    stats = {}
    for s in sports:
        stats[s] = {
            "SU": {"wins": 0, "losses": 0},
            "ATS": {"wins": 0, "losses": 0, "pushes": 0},
            "OU": {"wins": 0, "losses": 0, "pushes": 0},
        }

    graded = 0
    results_detail = []  # for historical chart data

    for pred in unique_preds:
        pid = str(pred.get("id") or "")
        if pid not in completed:
            continue

        final = completed[pid]
        sport = final["sport"]
        if sport not in stats:
            continue

        home_score = final["home_score"]
        away_score = final["away_score"]
        graded += 1

        picks = pred.get("picks") or {}
        odds = final.get("odds") or pred.get("odds") or {}

        game_date = final.get("date_utc") or pred.get("date_utc")
        result_entry = {
            "id": pid,
            "sport": sport,
            "date": game_date,
            "matchup": pred.get("matchup") or pred.get("shortName") or "",
        }

        # --- SU ---
        su_pick = picks.get("su_pick")
        if su_pick:
            home_team = pred.get("home_team") or {}
            away_team = pred.get("away_team") or {}
            home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
            away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)

            actual_winner = home_name if home_score > away_score else away_name
            if home_score == away_score:
                actual_winner = None  # tie

            if actual_winner:
                # Check if pick matches winner
                su_correct = (su_pick == actual_winner) or (
                    picks.get("su_pick_abbr") == (pred.get("home") if home_score > away_score else pred.get("away"))
                )
                if su_correct:
                    stats["ALL"]["SU"]["wins"] += 1
                    stats[sport]["SU"]["wins"] += 1
                    result_entry["su"] = "W"
                else:
                    stats["ALL"]["SU"]["losses"] += 1
                    stats[sport]["SU"]["losses"] += 1
                    result_entry["su"] = "L"

        # --- ATS ---
        ats_pick = picks.get("ats_pick")
        spread_line = safe_float(odds.get("spread"))
        if ats_pick and spread_line is not None:
            actual_margin = home_score - away_score

            home_team = pred.get("home_team") or {}
            home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)

            # Determine if the ATS pick was for home or away
            pick_is_home = (ats_pick == home_name) or (picks.get("ats_pick_abbr") == pred.get("home"))

            if pick_is_home:
                # Picked home to cover: home covers if margin > spread_line
                covered = actual_margin > spread_line
                push = abs(actual_margin - spread_line) < 0.01
            else:
                # Picked away to cover: away covers if margin < spread_line
                covered = actual_margin < spread_line
                push = abs(actual_margin - spread_line) < 0.01

            if push:
                stats["ALL"]["ATS"]["pushes"] += 1
                stats[sport]["ATS"]["pushes"] += 1
                result_entry["ats"] = "P"
            elif covered:
                stats["ALL"]["ATS"]["wins"] += 1
                stats[sport]["ATS"]["wins"] += 1
                result_entry["ats"] = "W"
            else:
                stats["ALL"]["ATS"]["losses"] += 1
                stats[sport]["ATS"]["losses"] += 1
                result_entry["ats"] = "L"

        # --- O/U ---
        ou_pick = picks.get("ou_pick")
        total_line = safe_float(odds.get("total"))
        if ou_pick and total_line is not None:
            actual_total = home_score + away_score
            push = abs(actual_total - total_line) < 0.01

            if push:
                stats["ALL"]["OU"]["pushes"] += 1
                stats[sport]["OU"]["pushes"] += 1
                result_entry["ou"] = "P"
            elif (ou_pick == "Over" and actual_total > total_line) or \
                 (ou_pick == "Under" and actual_total < total_line):
                stats["ALL"]["OU"]["wins"] += 1
                stats[sport]["OU"]["wins"] += 1
                result_entry["ou"] = "W"
            else:
                stats["ALL"]["OU"]["losses"] += 1
                stats[sport]["OU"]["losses"] += 1
                result_entry["ou"] = "L"

        results_detail.append(result_entry)

    # Build output
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "predictions_graded": graded,
        "sports": {},
        "results": results_detail[-200:],  # last 200 for chart
    }

    for s in sports:
        su = stats[s]["SU"]
        ats = stats[s]["ATS"]
        ou = stats[s]["OU"]

        su_total = su["wins"] + su["losses"]
        ats_total = ats["wins"] + ats["losses"]
        ou_total = ou["wins"] + ou["losses"]

        out["sports"][s] = {
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

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    all_su = stats["ALL"]["SU"]
    all_ats = stats["ALL"]["ATS"]
    all_ou = stats["ALL"]["OU"]
    su_t = all_su["wins"] + all_su["losses"]
    ats_t = all_ats["wins"] + all_ats["losses"]
    ou_t = all_ou["wins"] + all_ou["losses"]

    print(f"[accuracy] Graded {graded} picks")
    print(f"  SU:  {all_su['wins']}-{all_su['losses']} ({round(all_su['wins']/su_t*100,1) if su_t else 0}%)")
    print(f"  ATS: {all_ats['wins']}-{all_ats['losses']}-{all_ats['pushes']} ({round(all_ats['wins']/ats_t*100,1) if ats_t else 0}%)")
    print(f"  O/U: {all_ou['wins']}-{all_ou['losses']}-{all_ou['pushes']} ({round(all_ou['wins']/ou_t*100,1) if ou_t else 0}%)")


if __name__ == "__main__":
    main()
