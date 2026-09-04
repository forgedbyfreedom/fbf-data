#!/usr/bin/env python3
"""
build_line_study.py
-------------------
Builds a permanent record of: the line we saw, the line the market closed at,
what the model thought at the time, and what actually happened.

WHY THIS EXISTS

Every accuracy test run against this repo's history compared the model to
ESPN's stored spread, which sits at or very near the CLOSING line. That is the
hardest benchmark in sports betting - it contains every injury report, weather
update and sharp bet placed right up to kickoff. Unsurprisingly nothing beat it.

But nobody can bet the closing line. The model runs on a 6-hour cycle and sees
a number hours or days earlier. Whether it beats THAT number is a completely
different question, and it is the one that decides whether this pipeline is
worth running.

CLOSING LINE VALUE

The measurement is CLV: did the number we saw beat where the market closed?
If we like a team at +7 and it closes +5, we captured 2 points of CLV. Positive
CLV is the single best predictor of long-run profitability in sports betting,
and it is far faster to measure than win rate - a few dozen games gives a
readable signal, where ATS results need several hundred.

CLV is computed for EVERY game the model had an opinion on, not only games
where a pick was published, so the sample builds as fast as the schedule allows.

Output: line_study.json (append-only; games are never removed)
"""

import json, os
from datetime import datetime, timezone

SNAPSHOTS = "line_snapshots.json"
LOCKED = "predictions_locked.json"
SCORES = "completed_scores.json"
COMBINED = "combined.json"
OUTPUT = "line_study.json"

FOOTBALL = {"nfl", "ncaaf"}


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    snaps = load(SNAPSHOTS, {})
    locked_raw = load(LOCKED, {})
    locked_list = locked_raw if isinstance(locked_raw, list) else locked_raw.get("locked", [])
    scores = (load(SCORES, {}) or {}).get("scores", {})
    study = load(OUTPUT, {})
    if not isinstance(study, dict):
        study = {}

    # newest lock per game id
    by_id = {}
    for p in locked_list:
        gid = str(p.get("id") or "")
        if not gid or (p.get("sport") or "").lower() not in FOOTBALL:
            continue
        prev = by_id.get(gid)
        # Keep the EARLIEST lock. That is the number we could actually have bet,
        # and the whole point of the study is comparing it to the close.
        if prev is None or str(p.get("locked_at") or "") < str(prev.get("locked_at") or ""):
            by_id[gid] = p

    added = updated = 0
    for gid, pred in by_id.items():
        final = scores.get(gid)
        if not final:
            continue  # not played yet; recorded once it completes

        hs, aws = final.get("home_score"), final.get("away_score")
        if hs is None or aws is None:
            continue

        kickoff = parse_ts(pred.get("date_utc"))
        lock_odds = pred.get("odds") or {}
        lock_spread = lock_odds.get("spread")
        if lock_spread is None or kickoff is None:
            continue

        # closing line = last snapshot strictly before kickoff
        series = snaps.get(gid) or []
        closing_spread = closing_total = None
        closing_ts = None
        n_snaps = 0
        for s in series:
            ts = parse_ts(s.get("timestamp"))
            if ts is None or ts >= kickoff:
                continue
            n_snaps += 1
            if closing_ts is None or ts > closing_ts:
                closing_ts, closing_spread, closing_total = ts, s.get("spread"), s.get("total")
        if closing_spread is None:
            closing_spread = lock_spread          # never saw it move
            closing_total = lock_odds.get("total")
            closing_ts = parse_ts(pred.get("locked_at"))

        margin = float(hs) - float(aws)
        proj = ((pred.get("prediction") or {}).get("projected_spread"))
        picks = pred.get("picks") or {}

        # Which side did the model lean, relative to the line it SAW?
        model_edge = None
        lean = None
        if proj is not None:
            model_edge = round(float(proj) - (-float(lock_spread)), 2)
            lean = "home" if model_edge > 0 else ("away" if model_edge < 0 else None)

        # CLV: did the number we saw beat where it closed, for the side we leaned?
        # Home side: lower (more negative) closing spread than ours = we got the
        # better number. Away side: the reverse.
        clv = None
        if lean:
            move = float(closing_spread) - float(lock_spread)
            clv = round(-move if lean == "home" else move, 2)

        rec = {
            "id": gid,
            "sport": pred.get("sport"),
            "matchup": pred.get("shortName") or pred.get("matchup"),
            "kickoff_utc": pred.get("date_utc"),
            "locked_at": pred.get("locked_at"),
            "lock_spread": lock_spread,
            "lock_total": lock_odds.get("total"),
            "closing_spread": closing_spread,
            "closing_total": closing_total,
            "closing_seen_at": closing_ts.isoformat() if closing_ts else None,
            "snapshots_before_kickoff": n_snaps,
            "home_score": hs, "away_score": aws, "margin": margin,
            "total_points": float(hs) + float(aws),
            "model_projected_spread": proj,
            "model_edge_vs_lock": model_edge,
            "model_lean": lean,
            "clv_points": clv,
            "ats_pick": picks.get("ats_pick_abbr"),
            "ou_pick": picks.get("ou_pick"),
            # graded both ways: against the number we saw, and against the close
            "cover_vs_lock": None if lean is None else (
                ("home" if margin + float(lock_spread) > 0 else "away")
                if margin + float(lock_spread) != 0 else "push"),
            "cover_vs_close": None if closing_spread is None else (
                ("home" if margin + float(closing_spread) > 0 else "away")
                if margin + float(closing_spread) != 0 else "push"),
        }
        if gid in study:
            if study[gid] != rec:
                study[gid] = rec; updated += 1
        else:
            study[gid] = rec; added += 1

    with open(OUTPUT, "w") as f:
        json.dump(study, f, indent=2, sort_keys=True)

    graded = [r for r in study.values() if r.get("clv_points") is not None]
    print(f"[line_study] {len(study)} games recorded ({added} new, {updated} updated)")
    if graded:
        avg = sum(r["clv_points"] for r in graded) / len(graded)
        beat = sum(1 for r in graded if r["clv_points"] > 0)
        push = sum(1 for r in graded if r["clv_points"] == 0)
        wins = sum(1 for r in graded if r["model_lean"] == r["cover_vs_lock"])
        losses = sum(1 for r in graded if r["cover_vs_lock"] not in (None, "push")
                     and r["model_lean"] != r["cover_vs_lock"])
        print(f"[line_study] CLV: mean {avg:+.2f} pts | beat the close {beat}/{len(graded)} "
              f"({beat/len(graded)*100:.0f}%), unmoved {push}")
        if wins + losses:
            print(f"[line_study] model lean ATS vs the number we saw: "
                  f"{wins}-{losses} ({wins/(wins+losses)*100:.1f}%)  [breakeven 52.4%]")
        print("[line_study] NOTE: a few dozen games is not a verdict. Positive mean CLV "
              "sustained over 50+ games is the first real evidence of an edge.")


if __name__ == "__main__":
    main()
