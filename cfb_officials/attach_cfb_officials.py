#!/usr/bin/env python3
"""
attach_cfb_officials.py
Fill the empty `officials` list on college rows of historical_results.json
from cfb_officials/cfb_officials.json, in the same shape ESPN gives NFL rows
([{"name", "position"}]), plus each side's penalties and penalty yards.

Matching: ESPN date_utc is UTC, box-score dates are local, so a night game is
one calendar day earlier in the box score. A box score matches when it is on
the UTC date or the day before AND has the same pair of final scores; ties on
both are broken by a team-name word in common. Idempotent - safe nightly.
"""
import json, os, re, collections, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(os.path.dirname(HERE), "historical_results.json")
OFF = os.path.join(HERE, "cfb_officials.json")
POS = {"referee": "Referee", "umpire": "Umpire", "linesman": "Down Judge",
       "lineJudge": "Line Judge", "backJudge": "Back Judge", "fieldJudge": "Field Judge",
       "sideJudge": "Side Judge", "centerJudge": "Center Judge"}


def main():
    if not os.path.exists(OFF):
        print("[attach_cfb_officials] no cfb_officials.json yet")
        return
    games = json.load(open(OFF))["games"]
    idx = collections.defaultdict(list)
    for g in games:
        idx[g["date_iso"]].append(g)
    hist = json.load(open(HIST))
    n_rows = n_hit = 0
    for h in hist["data"]:
        if h.get("sport") != "ncaaf":
            continue
        hs, aw = (h.get("home_team") or {}).get("score"), (h.get("away_team") or {}).get("score")
        if hs is None or aw is None or not h.get("date_utc"):
            continue
        n_rows += 1
        d = dt.date.fromisoformat(h["date_utc"][:10])
        cand = [o for dd in (d, d - dt.timedelta(days=1)) for o in idx.get(dd.isoformat(), [])
                if o.get("home_score") is not None and {o["home_score"], o["away_score"]} == {hs, aw}]
        if len(cand) > 1:
            names = ((h.get("home_team") or {}).get("name", "") + " " +
                     (h.get("away_team") or {}).get("name", "")).lower()
            cand = [o for o in cand
                    if any(w in names for w in re.findall(r"[a-z]{4,}", f"{o['home']} {o['away']}".lower()))] or cand
            cand = cand[:1] if len({o["referee"] for o in cand}) == 1 else []
        if len(cand) != 1:
            continue
        o = cand[0]
        flip = o["home_score"] != hs   # box score lists the sides the other way round
        h["officials"] = [{"name": n, "position": POS.get(r, r)} for r, n in (o.get("crew") or {}).items()]
        h["penalties"] = {
            "home": o["away_pen"] if flip else o["home_pen"],
            "home_yds": o["away_pen_yds"] if flip else o["home_pen_yds"],
            "away": o["home_pen"] if flip else o["away_pen"],
            "away_yds": o["home_pen_yds"] if flip else o["away_pen_yds"],
            "source": "official box score",
        }
        n_hit += 1
    json.dump(hist, open(HIST, "w"), indent=2)
    print(f"[attach_cfb_officials] crews attached to {n_hit} of {n_rows} completed college games")


if __name__ == "__main__":
    main()
