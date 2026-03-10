#!/usr/bin/env python3
"""
backtest_live.py
Re-simulates all locked predictions with the CURRENT model and grades
against actual final scores. Shows what the new model WOULD have picked
for every completed game, compared to what the old model actually picked.
"""

import json
from monte_carlo import simulate_and_pick, safe_float

SCORES_FILE = "completed_scores.json"
LOCKED_FILE = "predictions_locked.json"
ARCHIVE_FILE = "predictions_archive.json"


def main():
    # Load final scores
    with open(SCORES_FILE) as f:
        scores_data = json.load(f)
    completed = {}
    for gid, score in scores_data.get("scores", {}).items():
        completed[str(gid)] = score

    # Load locked predictions (these have the full game data we need)
    all_preds = []
    for filepath in [LOCKED_FILE, ARCHIVE_FILE]:
        try:
            with open(filepath) as f:
                data = json.load(f)
            preds = data.get("locked", data.get("predictions", []))
            all_preds.extend(preds)
        except Exception:
            pass

    # Deduplicate
    seen = set()
    unique = []
    for p in all_preds:
        pid = str(p.get("id", ""))
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)

    print(f"[backtest_live] {len(completed)} completed scores, {len(unique)} predictions")

    sports = ["ALL", "NFL", "NCAAF", "NBA", "NCAAB", "NCAAW", "NHL", "MLB", "UFC"]

    # Stats for OLD model and NEW model
    old = {s: {"su_w": 0, "su_l": 0, "ats_w": 0, "ats_l": 0, "ou_w": 0, "ou_l": 0} for s in sports}
    new = {s: {"su_w": 0, "su_l": 0, "ats_w": 0, "ats_l": 0, "ats_skip": 0, "ou_w": 0, "ou_l": 0, "ou_skip": 0} for s in sports}

    graded = 0
    details = []

    for pred in unique:
        pid = str(pred.get("id", ""))
        if pid not in completed:
            continue

        final = completed[pid]
        sport = (final.get("sport") or pred.get("sport") or "").upper()
        if sport not in old:
            continue

        home_score = safe_float(final.get("home_score"), None)
        away_score = safe_float(final.get("away_score"), None)
        if home_score is None or away_score is None:
            continue

        graded += 1
        actual_margin = home_score - away_score
        actual_total = home_score + away_score

        odds = final.get("odds") or pred.get("odds") or {}
        spread = safe_float(odds.get("spread"), None)
        total = safe_float(odds.get("total"), None)

        home_team = pred.get("home_team") or {}
        away_team = pred.get("away_team") or {}
        home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
        away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)
        home_abbr = home_team.get("abbr", pred.get("home", "")) if isinstance(home_team, dict) else str(pred.get("home", ""))
        away_abbr = away_team.get("abbr", pred.get("away", "")) if isinstance(away_team, dict) else str(pred.get("away", ""))

        # ── OLD MODEL GRADING (from locked picks) ──
        old_picks = pred.get("picks") or {}

        # Old SU
        old_su = old_picks.get("su_pick_abbr")
        if old_su:
            if home_score != away_score:
                winner = home_abbr if home_score > away_score else away_abbr
                if old_su == winner:
                    old["ALL"]["su_w"] += 1; old[sport]["su_w"] += 1
                else:
                    old["ALL"]["su_l"] += 1; old[sport]["su_l"] += 1

        # Old ATS
        old_ats_abbr = old_picks.get("ats_pick_abbr")
        if old_ats_abbr and spread is not None:
            pick_home = (old_ats_abbr == home_abbr)
            home_covered = actual_margin + spread > 0
            push = abs(actual_margin + spread) < 0.01
            if not push:
                covered = home_covered if pick_home else not home_covered
                if covered:
                    old["ALL"]["ats_w"] += 1; old[sport]["ats_w"] += 1
                else:
                    old["ALL"]["ats_l"] += 1; old[sport]["ats_l"] += 1

        # Old O/U
        old_ou = old_picks.get("ou_pick")
        if old_ou and total is not None:
            push = abs(actual_total - total) < 0.01
            if not push:
                if (old_ou == "Over" and actual_total > total) or \
                   (old_ou == "Under" and actual_total < total):
                    old["ALL"]["ou_w"] += 1; old[sport]["ou_w"] += 1
                else:
                    old["ALL"]["ou_l"] += 1; old[sport]["ou_l"] += 1

        # ── NEW MODEL: re-simulate with current model ──
        game = dict(pred)  # use full game data from locked prediction
        game["sport"] = sport.lower()
        # Make sure odds are set
        if "odds" not in game or game["odds"] is None:
            game["odds"] = odds

        try:
            result = simulate_and_pick(game, n_sims=5000)
        except Exception as e:
            continue

        new_picks = result.get("picks", {})

        detail = {
            "matchup": pred.get("shortName") or pred.get("matchup", ""),
            "sport": sport,
            "date": final.get("date_utc", pred.get("date_utc", "")),
            "score": f"{home_score:.0f}-{away_score:.0f}",
        }

        # New SU
        new_su = new_picks.get("su_pick_abbr")
        if new_su:
            if home_score != away_score:
                winner = home_abbr if home_score > away_score else away_abbr
                if new_su == winner:
                    new["ALL"]["su_w"] += 1; new[sport]["su_w"] += 1
                    detail["new_su"] = "W"
                else:
                    new["ALL"]["su_l"] += 1; new[sport]["su_l"] += 1
                    detail["new_su"] = "L"

        # New ATS
        if new_picks.get("ats_no_play"):
            new["ALL"]["ats_skip"] += 1; new[sport]["ats_skip"] += 1
            detail["new_ats"] = "SKIP"
        elif spread is not None:
            new_ats_abbr = new_picks.get("ats_pick_abbr")
            pick_home = (new_ats_abbr == home_abbr)
            home_covered = actual_margin + spread > 0
            push = abs(actual_margin + spread) < 0.01
            if not push:
                covered = home_covered if pick_home else not home_covered
                if covered:
                    new["ALL"]["ats_w"] += 1; new[sport]["ats_w"] += 1
                    detail["new_ats"] = "W"
                else:
                    new["ALL"]["ats_l"] += 1; new[sport]["ats_l"] += 1
                    detail["new_ats"] = "L"

        # New O/U
        if new_picks.get("ou_no_play"):
            new["ALL"]["ou_skip"] += 1; new[sport]["ou_skip"] += 1
            detail["new_ou"] = "SKIP"
        elif total is not None:
            new_ou = new_picks.get("ou_pick")
            push = abs(actual_total - total) < 0.01
            if not push:
                if (new_ou == "Over" and actual_total > total) or \
                   (new_ou == "Under" and actual_total < total):
                    new["ALL"]["ou_w"] += 1; new[sport]["ou_w"] += 1
                    detail["new_ou"] = "W"
                else:
                    new["ALL"]["ou_l"] += 1; new[sport]["ou_l"] += 1
                    detail["new_ou"] = "L"

        detail["new_ats_conf"] = new_picks.get("ats_confidence")
        detail["new_ou_conf"] = new_picks.get("ou_confidence")
        details.append(detail)

    # ── PRINT COMPARISON ──
    def pct(w, l):
        t = w + l
        return f"{w/(t)*100:.1f}%" if t else "—"

    def record(w, l):
        return f"{w}-{l}"

    print(f"\n{'':8s} │ {'OLD MODEL SU':15s} │ {'NEW MODEL SU':15s} │ {'OLD ATS':15s} │ {'NEW ATS':22s} │ {'OLD O/U':15s} │ {'NEW O/U':22s}")
    print("─" * 130)

    for s in sports:
        o, n = old[s], new[s]

        o_su = f"{record(o['su_w'], o['su_l']):8s} {pct(o['su_w'], o['su_l']):>5s}"
        n_su = f"{record(n['su_w'], n['su_l']):8s} {pct(n['su_w'], n['su_l']):>5s}"

        o_ats = f"{record(o['ats_w'], o['ats_l']):8s} {pct(o['ats_w'], o['ats_l']):>5s}"
        n_ats_t = n['ats_w'] + n['ats_l']
        n_ats = f"{record(n['ats_w'], n['ats_l']):8s} {pct(n['ats_w'], n['ats_l']):>5s} sk:{n['ats_skip']}"

        o_ou = f"{record(o['ou_w'], o['ou_l']):8s} {pct(o['ou_w'], o['ou_l']):>5s}"
        n_ou = f"{record(n['ou_w'], n['ou_l']):8s} {pct(n['ou_w'], n['ou_l']):>5s} sk:{n['ou_skip']}"

        print(f"{s:8s} │ {o_su:15s} │ {n_su:15s} │ {o_ats:15s} │ {n_ats:22s} │ {o_ou:15s} │ {n_ou:22s}")

    # Save detailed results
    with open("backtest_live_results.json", "w") as f:
        json.dump({
            "graded": graded,
            "old_model": {s: old[s] for s in sports},
            "new_model": {s: new[s] for s in sports},
            "details": details,
        }, f, indent=2)

    print(f"\n[backtest_live] {graded} games graded. Details saved to backtest_live_results.json")


if __name__ == "__main__":
    main()
