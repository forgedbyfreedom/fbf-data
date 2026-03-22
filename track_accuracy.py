#!/usr/bin/env python3
"""
track_accuracy.py
Tracks prediction accuracy for the CURRENT model only.

Only grades picks made on or after MODEL_START_DATE with real Vegas odds.
Skips preseason, no-odds games, and any picks from older model versions.

Outputs: accuracy.json with per-sport and overall SU/ATS/O/U records,
         tracking both ALL picks and BEST BET (high-confidence) picks.
"""

import json, os
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────────────────
# Current model start date — only grade picks locked on or after this.
# Update this whenever the model is significantly changed.
MODEL_START_DATE = "2025-11-22"

# Per-sport override: some sports were recalibrated after the general start.
# v3 (2026-03-19): Full sport-specific modeling — TOTAL_STDEV recalibrated,
# O/U regression added, pace/ref weights dampened for NBA/NHL, indoor sports
# hardcoded to skip weather. Previous overrides no longer needed.
SPORT_START_OVERRIDE = {}

OUTPUT = "accuracy.json"
SCORES_FILE = "completed_scores.json"
COMBINED_FILE = "combined.json"
LOCKED_FILE = "predictions_locked.json"
ARCHIVE_FILE = "predictions_archive.json"

# Minimum realistic final-game totals (reject partial scores)
MIN_TOTAL = {
    "NBA": 160, "NCAAB": 100, "NCAAW": 90,
    "NFL": 6, "NCAAF": 10, "NHL": 1, "MLB": 1,
}

SPORTS = ["ALL", "NFL", "NCAAF", "NBA", "NCAAB", "NCAAW", "NHL", "MLB"]


def safe_float(x, default=None):
    if x is None:
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        if default is None:
            print(f"[accuracy] Error loading {path}: {e}")
        return default


def make_bucket():
    return {
        "SU": {"wins": 0, "losses": 0},
        "ATS": {"wins": 0, "losses": 0, "pushes": 0},
        "OU": {"wins": 0, "losses": 0, "pushes": 0},
    }


def update(stats, sport, cat, result):
    if result == "W":
        stats["ALL"][cat]["wins"] += 1
        stats[sport][cat]["wins"] += 1
    elif result == "L":
        stats["ALL"][cat]["losses"] += 1
        stats[sport][cat]["losses"] += 1
    elif result == "P":
        if "pushes" in stats["ALL"][cat]:
            stats["ALL"][cat]["pushes"] += 1
            stats[sport][cat]["pushes"] += 1


def grade_ats(picks, pred, odds, home_score, away_score):
    ats_pick = picks.get("ats_pick")
    spread = safe_float(odds.get("spread"))
    if not ats_pick or spread is None:
        return None

    margin = home_score - away_score
    home_team = pred.get("home_team") or {}
    home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
    pick_is_home = (ats_pick == home_name) or (picks.get("ats_pick_abbr") == pred.get("home"))

    val = margin + spread
    if abs(val) < 0.01:
        return "P"
    home_covered = val > 0
    if pick_is_home:
        return "W" if home_covered else "L"
    return "W" if not home_covered else "L"


def grade_ou(picks, odds, home_score, away_score, sport=""):
    ou_pick = picks.get("ou_pick")
    total_line = safe_float(odds.get("total"))
    if not ou_pick or total_line is None or total_line < 0.5:
        return None

    actual = home_score + away_score
    if actual < MIN_TOTAL.get(sport.upper(), 0):
        return None

    if abs(actual - total_line) < 0.01:
        return "P"
    if (ou_pick == "Over" and actual > total_line) or \
       (ou_pick == "Under" and actual < total_line):
        return "W"
    return "L"


def main():
    start_cutoff = datetime.fromisoformat(MODEL_START_DATE + "T00:00:00+00:00")

    # ── Load completed scores ───────────────────────────────────────
    completed = {}

    for gid, score in load_json(SCORES_FILE, {}).get("scores", {}).items():
        completed[str(gid)] = {
            "home_score": score["home_score"],
            "away_score": score["away_score"],
            "sport": (score.get("sport") or "").upper(),
            "date_utc": score.get("date_utc"),
            "odds": score.get("odds") or {},
        }

    for g in load_json(COMBINED_FILE, {}).get("data", []):
        gid = str(g.get("id") or g.get("event_id") or "")
        if not gid or gid in completed:
            continue
        hs = safe_float(g.get("home_score"))
        aws = safe_float(g.get("away_score"))
        if hs is None or aws is None:
            continue
        completed[gid] = {
            "home_score": hs, "away_score": aws,
            "sport": (g.get("sport") or "").upper(),
            "date_utc": g.get("date_utc"),
            "odds": g.get("odds") or {},
        }

    print(f"[accuracy] {len(completed)} completed games with scores")

    # ── Load locked predictions ─────────────────────────────────────
    all_preds = []
    for fp in [LOCKED_FILE, ARCHIVE_FILE]:
        if not os.path.exists(fp):
            continue
        try:
            data = load_json(fp, {})
            preds = data.get("locked", data.get("predictions", []))
            all_preds.extend(preds)
            print(f"[accuracy] {len(preds)} predictions from {fp}")
        except Exception as e:
            print(f"[accuracy] Error loading {fp}: {e}")

    if not all_preds:
        print("[accuracy] No predictions found")
        with open(OUTPUT, "w") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model_start": MODEL_START_DATE,
                "predictions_graded": 0, "sports": {}, "high_confidence": {},
            }, f, indent=2)
        return

    # Deduplicate
    seen = set()
    unique = []
    for p in all_preds:
        pid = str(p.get("id") or "")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)

    # ── Grade picks ─────────────────────────────────────────────────
    stats_all = {s: make_bucket() for s in SPORTS}
    stats_best = {s: make_bucket() for s in SPORTS}

    graded = 0
    skipped = {"old_model": 0, "no_odds": 0, "before_start": 0, "bad_score": 0}
    results = []

    for pred in unique:
        pid = str(pred.get("id") or "")
        if pid not in completed:
            continue

        picks = pred.get("picks") or {}

        # Skip old model picks (no high_conf flags)
        if picks.get("ats_high_conf") is None:
            skipped["old_model"] += 1
            continue

        # Skip picks locked before current model start date
        locked_at = pred.get("locked_at") or pred.get("date_utc") or ""
        try:
            lock_dt = datetime.fromisoformat(locked_at.replace("Z", "+00:00"))
            if lock_dt < start_cutoff:
                skipped["before_start"] += 1
                continue
        except Exception:
            skipped["before_start"] += 1
            continue

        final = completed[pid]
        sport = final["sport"]

        # Per-sport start override (e.g. NHL recalibrated later)
        sport_override = SPORT_START_OVERRIDE.get(sport)
        if sport_override:
            sport_cutoff = datetime.fromisoformat(sport_override + "T00:00:00+00:00")
            if lock_dt < sport_cutoff:
                skipped["before_start"] += 1
                continue
        if sport not in stats_all:
            continue

        odds = final.get("odds") or pred.get("odds") or {}

        # Skip no-odds / preseason
        if odds.get("spread") is None and odds.get("total") is None:
            skipped["no_odds"] += 1
            continue

        hs = final["home_score"]
        aws = final["away_score"]
        total = hs + aws

        # Skip partial / bad scores
        if total < MIN_TOTAL.get(sport, 0):
            skipped["bad_score"] += 1
            continue
        tl_check = safe_float(odds.get("total"))
        if tl_check and tl_check > 0 and total < tl_check * 0.5:
            skipped["bad_score"] += 1
            continue

        graded += 1
        game_date = final.get("date_utc") or pred.get("date_utc")
        entry = {
            "id": pid, "sport": sport, "date": game_date,
            "matchup": pred.get("matchup") or pred.get("shortName") or "",
        }

        # ── ATS ──
        ats_result = grade_ats(picks, pred, odds, hs, aws)
        ats_high = picks.get("ats_high_conf", False)
        if ats_result:
            update(stats_all, sport, "ATS", ats_result)
            if ats_high:
                update(stats_best, sport, "ATS", ats_result)
            entry["ats"] = ats_result
            entry["ats_best_bet"] = ats_high

        # ── O/U ──
        ou_result = grade_ou(picks, odds, hs, aws, sport)
        ou_high = picks.get("ou_high_conf", False)
        if ou_result:
            update(stats_all, sport, "OU", ou_result)
            if ou_high:
                update(stats_best, sport, "OU", ou_result)
            entry["ou"] = ou_result
            entry["ou_best_bet"] = ou_high

        # ── SU ──
        su_abbr = picks.get("su_pick_abbr")
        if su_abbr:
            home_abbr = pred.get("home") or ""
            if isinstance(pred.get("home_team"), dict):
                home_abbr = pred["home_team"].get("abbr", home_abbr)
            if hs != aws:
                away_abbr = pred.get("away") or ""
                if isinstance(pred.get("away_team"), dict):
                    away_abbr = pred["away_team"].get("abbr", "")
                winner = home_abbr if hs > aws else away_abbr
                su_result = "W" if su_abbr == winner else "L"
                update(stats_all, sport, "SU", su_result)
                if ats_high or ou_high:
                    update(stats_best, sport, "SU", su_result)
                entry["su"] = su_result

        results.append(entry)

    # ── Build output ────────────────────────────────────────────────
    def build_stats(st):
        out = {}
        for s in SPORTS:
            su = st[s]["SU"]
            ats = st[s]["ATS"]
            ou = st[s]["OU"]
            su_t = su["wins"] + su["losses"]
            ats_t = ats["wins"] + ats["losses"]
            ou_t = ou["wins"] + ou["losses"]
            out[s] = {
                "SU_pct": round(su["wins"] / su_t * 100, 1) if su_t else 0,
                "SU_record": f"{su['wins']}-{su['losses']}",
                "SU_total": su_t,
                "ATS_pct": round(ats["wins"] / ats_t * 100, 1) if ats_t else 0,
                "ATS_record": f"{ats['wins']}-{ats['losses']}-{ats['pushes']}",
                "ATS_total": ats_t,
                "OU_pct": round(ou["wins"] / ou_t * 100, 1) if ou_t else 0,
                "OU_record": f"{ou['wins']}-{ou['losses']}-{ou['pushes']}",
                "OU_total": ou_t,
            }
        return out

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_start": MODEL_START_DATE,
        "predictions_graded": graded,
        "sports": build_stats(stats_all),
        "high_confidence": build_stats(stats_best),
        "results": results[-200:],
    }

    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    # ── Print summary ───────────────────────────────────────────────
    skip_summary = ", ".join(f"{v} {k}" for k, v in skipped.items() if v)
    print(f"[accuracy] Graded {graded} picks (skipped: {skip_summary})")
    print(f"[accuracy] Model tracking since {MODEL_START_DATE}")

    for label, st in [("ALL PICKS", stats_all), ("BEST BETS", stats_best)]:
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


if __name__ == "__main__":
    main()
