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

EVERYTHING HERE IS ON THE FAVORITE'S NUMBER (rewritten 2026-10-15)

Lines are quoted favorite vs underdog: ORE -24.5 / OKST +24.5. Every line in
this file is the favorite's number (negative = points laid), every margin is
the favorite's margin, and every side is "fav" / "dog" plus the team abbr.

The previous version graded against ESPN's raw `odds.spread` field, whose sign
depends on which team is at home, and compared it to snapshots that hold the
favorite's number. Whenever the favorite was on the road the two disagreed in
sign (ND -27.5 recorded as +27.5), which manufactured ~750 points of fake CLV.
Do not reintroduce a home/away spread anywhere in this file.

Locks built AFTER kickoff (every lock before the 2026-10-15 fix in
build_predictions.py) carry no bettable number, so they get no CLV and are not
graded against the lock line. The model's lean is still graded against the
last pre-kickoff line.

Output: line_study.json (games are never removed)
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


def to_fav_line(spread, snap_fav, fav_abbr):
    """A snapshot's number expressed as the line on OUR favorite."""
    if spread is None:
        return None
    spread = float(spread)
    if snap_fav and fav_abbr and snap_fav != fav_abbr:
        return -spread               # the other team was favored at that moment
    return spread


def side_covering(fav_margin, fav_line):
    """'fav', 'dog' or 'push' against a line on the favorite."""
    if fav_line is None:
        return None
    v = fav_margin + float(fav_line)
    return "push" if v == 0 else ("fav" if v > 0 else "dog")


def main():
    snaps = load(SNAPSHOTS, {})
    locked_raw = load(LOCKED, {})
    locked_list = locked_raw if isinstance(locked_raw, list) else locked_raw.get("locked", [])
    scores = (load(SCORES, {}) or {}).get("scores", {})
    study = load(OUTPUT, {})
    if not isinstance(study, dict):
        study = {}

    by_id = {}
    for p in locked_list:
        gid = str(p.get("id") or "")
        if gid and (p.get("sport") or "").lower() in FOOTBALL:
            by_id[gid] = p

    added = updated = 0
    for gid, pred in by_id.items():
        final = scores.get(gid)
        if not final:
            continue
        hs, aws = final.get("home_score"), final.get("away_score")
        kickoff = parse_ts(pred.get("date_utc"))
        fav = pred.get("fav_abbr")
        dog = pred.get("dog_abbr")
        lock_fav_line = pred.get("fav_spread")
        if hs is None or aws is None or kickoff is None or not fav or lock_fav_line is None:
            continue
        lock_fav_line = float(lock_fav_line)
        lock_odds = pred.get("odds") or {}

        fav_is_home = fav == pred.get("home")
        home_margin = float(hs) - float(aws)
        fav_margin = home_margin if fav_is_home else -home_margin

        locked_at = parse_ts(pred.get("locked_at"))
        bettable = (pred.get("lock_source") == "pre_kickoff"
                    and locked_at is not None and locked_at < kickoff)

        # pre-kickoff market, on our favorite's number
        series = []
        assumed = False
        for s in snaps.get(gid) or []:
            ts = parse_ts(s.get("timestamp"))
            if ts is None or ts >= kickoff or s.get("spread") is None:
                continue
            if not s.get("fav_abbr"):
                assumed = True        # legacy snapshot: favorite not recorded
            series.append((ts, to_fav_line(s["spread"], s.get("fav_abbr"), fav), s.get("total")))
        series.sort(key=lambda r: r[0])
        open_line = series[0][1] if series else None
        close_line = series[-1][1] if series else (lock_fav_line if bettable else None)
        close_total = series[-1][2] if series else (lock_odds.get("total") if bettable else None)
        close_ts = series[-1][0] if series else None

        # the model's opinion, relative to the line it was looking at
        proj = (pred.get("prediction") or {}).get("projected_spread")   # home minus away
        edge = lean = lean_abbr = None
        if proj is not None:
            proj_fav_margin = float(proj) if fav_is_home else -float(proj)
            edge = round(proj_fav_margin + lock_fav_line, 2)
            lean = "fav" if edge > 0 else ("dog" if edge < 0 else None)
            lean_abbr = {"fav": fav, "dog": dog}.get(lean)

        # ── TRUE CLV: the model's FIRST pre-kickoff opinion vs the close ──
        # (2026-10-29) The lock is the LAST run before kickoff, which on a
        # 6-hour cycle sits at the close - CLV measured from it was zero on
        # all 84 bettable locks, by construction. build_predictions.py now
        # stamps `early_lock`, the first run that saw a line, and CLV is the
        # move from that bettable number to the close, signed by the lean the
        # model held AT THAT TIME. Locks recorded before the early stamp
        # existed have no early_lock and keep clv_points = null.
        early = pred.get("early_lock") or {}
        early_line = to_fav_line(early.get("fav_spread"), early.get("fav_abbr"), fav)
        early_ts = parse_ts(early.get("captured_at"))
        early_edge = early_lean = None
        e_proj = early.get("projected_spread")               # home minus away
        if e_proj is not None and early_line is not None:
            e_fav_margin = float(e_proj) if fav_is_home else -float(e_proj)
            early_edge = round(e_fav_margin + early_line, 2)
            early_lean = "fav" if early_edge > 0 else ("dog" if early_edge < 0 else None)

        clv = None
        if (early_lean and early_line is not None and close_line is not None
                and early_ts is not None and early_ts < kickoff):
            move = close_line - early_line               # negative = favorite got pricier
            clv = round(-move if early_lean == "fav" else move, 2)

        picks = pred.get("picks") or {}
        pick_abbr = picks.get("ats_pick_abbr")
        pick_side = "fav" if pick_abbr == fav else ("dog" if pick_abbr == dog else None)
        cover_lock = side_covering(fav_margin, lock_fav_line) if bettable else None
        cover_close = side_covering(fav_margin, close_line)

        def res(side, cover):
            if not side or not cover:
                return None
            return "P" if cover == "push" else ("W" if side == cover else "L")

        lock_total = lock_odds.get("total")
        tp = float(hs) + float(aws)
        rec = {
            "id": gid,
            "sport": pred.get("sport"),
            "matchup": pred.get("shortName") or pred.get("matchup"),
            "kickoff_utc": pred.get("date_utc"),
            "locked_at": pred.get("locked_at"),
            "lock_source": pred.get("lock_source") or "post_kickoff_legacy",
            "bettable_lock": bettable,
            "fav": fav, "dog": dog, "fav_is_home": fav_is_home,
            "lock_fav_line": lock_fav_line if bettable else None,
            "open_fav_line": open_line,
            "close_fav_line": close_line,
            "close_seen_at": close_ts.isoformat() if close_ts else None,
            "snapshots_before_kickoff": len(series),
            "fav_identity_assumed": assumed,
            "home_score": hs, "away_score": aws,
            "fav_margin": fav_margin,
            "model_projected_fav_margin": None if proj is None else (float(proj) if fav_is_home else -float(proj)),
            "model_edge_pts": edge,
            "model_lean": lean, "model_lean_abbr": lean_abbr,
            "early_fav_line": early_line,
            "early_seen_at": early.get("captured_at"),
            "early_lean": early_lean,
            "early_edge_pts": early_edge,
            "early_lean_result_vs_close": res(early_lean, cover_close),
            "clv_points": clv,
            "cover_vs_lock": cover_lock,
            "cover_vs_close": cover_close,
            "lean_result_vs_lock": res(lean, cover_lock),
            "lean_result_vs_close": res(lean, cover_close),
            "ats_pick": pick_abbr, "ats_pick_side": pick_side,
            "ats_pick_line": picks.get("ats_spread"),
            "ats_pick_result_vs_close": res(pick_side, cover_close),
            "ou_pick": picks.get("ou_pick"),
            "lock_total": lock_total if bettable else None,
            "close_total": close_total,
            "total_points": tp,
            "total_result_vs_close": None if close_total is None else (
                "over" if tp > float(close_total) else ("under" if tp < float(close_total) else "push")),
            "wind_mph": (pred.get("weather") or {}).get("windSpeedMph"),
            "indoor": (pred.get("venue") or {}).get("indoor"),
            "model_projected_total": (pred.get("prediction") or {}).get("projected_total"),
        }
        if study.get(gid) != rec:
            if gid in study:
                updated += 1
            else:
                added += 1
            study[gid] = rec

    with open(OUTPUT, "w") as f:
        json.dump(study, f, indent=2, sort_keys=True)

    print(f"[line_study] {len(study)} games recorded ({added} new, {updated} updated) "
          f"- all lines on the favorite's number")
    rows = list(study.values())

    def tally(key):
        w = sum(1 for r in rows if r.get(key) == "W")
        l = sum(1 for r in rows if r.get(key) == "L")
        p = sum(1 for r in rows if r.get(key) == "P")
        return w, l, p

    w, l, p = tally("lean_result_vs_close")
    if w + l:
        print(f"[line_study] model lean ATS vs pre-kickoff close: {w}-{l}-{p} "
              f"({w/(w+l)*100:.1f}%)  [breakeven 52.4%]")
    clv = [r["clv_points"] for r in rows if r.get("clv_points") is not None]
    if clv:
        print(f"[line_study] CLV, first sighting vs close: mean {sum(clv)/len(clv):+.2f} pts over "
              f"{len(clv)} games | beat the close {sum(c > 0 for c in clv)}, "
              f"unmoved {sum(c == 0 for c in clv)}")
    else:
        print("[line_study] CLV: no early (first-sighting) locks graded yet")
    print("[line_study] NOTE: positive mean CLV sustained over 50+ games is the first "
          "real evidence of an edge.")


if __name__ == "__main__":
    main()
