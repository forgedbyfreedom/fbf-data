#!/usr/bin/env python3
"""
build_predictions.py
Generates predictions.json from combined.json using:
1. Monte Carlo simulation (10K sims per game)
2. Rule-based model (predictions_model.py)
3. Monte Carlo simulation anchored on the market line

Outputs explicit SU, ATS, O/U picks for every game.
Locks each pick as it stood before kickoff into predictions_locked.json.
"""
import json, os, pickle, math
from pathlib import Path
from datetime import datetime, timezone
from predictions_model import predict
from monte_carlo import simulate_and_pick

COMBINED = Path("combined.json")
OUTFILE = Path("predictions.json")
LOCKED_FILE = Path("predictions_locked.json")
PRELOCK_FILE = Path("predictions_prelock.json")   # latest pre-kickoff version of each upcoming game
ARCHIVE = Path("predictions_archive.json")
SPREAD_MODEL = Path("models/spread_model.pkl")
TOTAL_MODEL = Path("models/total_model.pkl")
SCHEMA_PATH = Path("models/feature_schema.json")

N_SIMS = 10000


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def load_ml_models():
    if not SPREAD_MODEL.exists():
        return None, None, None
    try:
        with open(SPREAD_MODEL, "rb") as f:
            spread_model = pickle.load(f)
        total_model = None
        if TOTAL_MODEL.exists():
            with open(TOTAL_MODEL, "rb") as f:
                total_model = pickle.load(f)
        schema = load_json(SCHEMA_PATH, {})
        feature_cols = schema.get("feature_cols", [])
        return spread_model, total_model, feature_cols
    except Exception as e:
        print(f"[warn] Could not load ML models: {e}")
        return None, None, None


def ml_predict(game, spread_model, total_model, feature_cols):
    try:
        odds = game.get("odds") or {}
        sport = (game.get("sport") or "").lower()
        feature_map = {
            "spread": float(odds.get("spread", 0) or 0),
            "total": float(odds.get("total", 0) or 0),
            "is_nfl": int(sport == "nfl"),
            "is_ncaaf": int(sport == "ncaaf"),
            "is_nba": int(sport == "nba"),
            "is_ncaab": int(sport == "ncaab"),
            "is_ncaaw": int(sport == "ncaaw"),
            "is_nhl": int(sport == "nhl"),
            "is_mlb": int(sport == "mlb"),
            "is_ufc": int(sport == "ufc"),
        }
        X = [[feature_map.get(c, 0) for c in feature_cols]]
        ml_margin = spread_model.predict(X)[0]
        ml_total = total_model.predict(X)[0] if total_model else None
        return ml_margin, ml_total
    except Exception:
        return None, None


def lock_picks(current_predictions, existing_locked, prelock):
    """
    Freeze each game's pick as it stood BEFORE kickoff.

    FIXED 2026-10-15: this used to copy the first prediction built AFTER the
    game started. On a 6-hour cycle that is 0-12 hours past kickoff, so the
    "locked" line and pick were built on post-kickoff odds - a number nobody
    could have bet, and one that can already reflect the game in progress.
    Every football lock from the 2026 season had this problem.

    Now every run stores the latest pre-kickoff prediction for each upcoming
    game in `prelock`. When the game starts, that stored version is what gets
    locked, stamped with the time it was actually built. A post-kickoff copy is
    only used if no pre-kickoff version exists, and it is flagged as such so
    the grading can exclude it.
    """
    now = datetime.now(timezone.utc)
    locked_by_id = {str(p.get("id")): p for p in existing_locked}
    new_locks = fallbacks = 0

    for pred in current_predictions:
        pid = str(pred.get("id") or "")
        if not pid or pid in locked_by_id:
            continue
        date_utc = pred.get("date_utc")
        if not date_utc:
            continue
        try:
            game_time = datetime.fromisoformat(date_utc.replace("Z", "+00:00"))
        except Exception:
            continue

        if now < game_time:
            # Not started: remember this as the latest bettable version.
            snap = dict(pred)
            snap["captured_at"] = now.isoformat()
            # ── EARLY LOCK (2026-10-29) ──────────────────────────────
            # The lock above is the LAST pre-kickoff run, which on a 6-hour
            # cycle is effectively the closing line - so CLV measured from it
            # is zero by construction (84 of 84 graded locks matched the
            # close exactly). The CLV experiment needs the model's opinion at
            # the FIRST moment it saw a line, hours or days earlier. Keep
            # that first sighting alongside the lock and never overwrite it.
            prev = prelock.get(pid) or {}
            early = prev.get("early_lock")
            if not early and pred.get("fav_spread") is not None:
                early = {
                    "captured_at": now.isoformat(),
                    "fav_abbr": pred.get("fav_abbr"),
                    "fav_spread": pred.get("fav_spread"),
                    "total": (pred.get("odds") or {}).get("total"),
                    "projected_spread": (pred.get("prediction") or {}).get("projected_spread"),
                    "projected_total": (pred.get("prediction") or {}).get("projected_total"),
                }
            if early:
                snap["early_lock"] = early
            prelock[pid] = snap
            continue

        # Started: lock the last version built before kickoff.
        pre = prelock.pop(pid, None)
        if pre is not None:
            locked_pred = dict(pre)
            locked_pred["locked_at"] = pre.get("captured_at") or now.isoformat()
            locked_pred["lock_source"] = "pre_kickoff"
        else:
            locked_pred = dict(pred)
            locked_pred["locked_at"] = now.isoformat()
            locked_pred["lock_source"] = "post_kickoff_fallback"
            fallbacks += 1
        locked_pred.pop("captured_at", None)
        locked_pred["lock_recorded_at"] = now.isoformat()
        locked_by_id[pid] = locked_pred
        new_locks += 1

    # A game that has started but dropped out of the feed still gets locked
    # from its pre-kickoff version.
    for pid, pre in list(prelock.items()):
        if pid in locked_by_id:
            continue
        try:
            gt = datetime.fromisoformat(str(pre.get("date_utc")).replace("Z", "+00:00"))
        except Exception:
            continue
        if now >= gt:
            locked_pred = dict(pre)
            locked_pred["locked_at"] = pre.get("captured_at") or now.isoformat()
            locked_pred["lock_source"] = "pre_kickoff"
            locked_pred.pop("captured_at", None)
            locked_pred["lock_recorded_at"] = now.isoformat()
            locked_by_id[pid] = locked_pred
            new_locks += 1

    # Drop stale pre-locks (game locked elsewhere, postponed, or long gone).
    for pid in list(prelock):
        snap = prelock[pid]
        try:
            gt = datetime.fromisoformat(str(snap.get("date_utc")).replace("Z", "+00:00"))
        except Exception:
            gt = None
        if pid in locked_by_id or gt is None or (now - gt).total_seconds() > 3 * 86400:
            prelock.pop(pid, None)

    all_locked = list(locked_by_id.values())
    if new_locks > 0:
        print(f"[picks] Locked {new_locks} new picks ({fallbacks} post-kickoff fallbacks, "
              f"{len(all_locked)} total locked)")
    return all_locked


def archive_completed(current_predictions, combined_games):
    completed_ids = set()
    for g in combined_games:
        if g.get("home_score") is not None and g.get("away_score") is not None:
            gid = g.get("id") or g.get("event_id")
            if gid:
                completed_ids.add(str(gid))

    if not completed_ids or not current_predictions:
        return

    archive = load_json(ARCHIVE, {"predictions": []})
    existing_ids = {str(p.get("id")) for p in archive.get("predictions", [])}

    for p in current_predictions:
        pid = str(p.get("id") or "")
        if pid in completed_ids and pid not in existing_ids:
            archive["predictions"].append(p)

    if archive["predictions"]:
        with open(ARCHIVE, "w") as f:
            json.dump(archive, f, indent=2)


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])

    # Archive previous predictions before overwriting
    old_preds = load_json(OUTFILE, {}).get("predictions", [])
    if old_preds:
        archive_completed(old_preds, games)

    # (no ML model is loaded; see the note in the prediction loop below)

    output = {
        "timestamp": combined.get("timestamp"),
        "count": 0,
        "predictions": []
    }

    for g in games:
        # 1. Rule-based prediction
        try:
            p = predict(g)
        except Exception as e:
            p = {
                "error": str(e),
                "projected_home_score": 0,
                "projected_away_score": 0,
                "projected_total": 0,
                "projected_spread": 0,
                "win_probability_home": 0,
                "confidence": 0
            }

        model_used = "rule_based"

        # 2. ML ensemble - REMOVED 2026-09-02.
        #
        # The RandomForest that used to blend in here at 40% weight
        # (0.6 * rule + 0.4 * ml) was measured against 2,299 held-out games:
        #
        #     reading the closing line   MAE 9.25 points
        #     the RandomForest           MAE 10.46 points
        #     its ATS hit rate           51.4%  (breakeven 52.4%)
        #
        # It was worse than doing nothing, and it was structurally incapable
        # of being better: ml_predict() fed it only the market spread, the
        # market total and sport one-hot flags. None of the Elo, power
        # ratings, injury, weather, referee, rest, head-to-head, line-movement
        # or public-betting features this pipeline computes ever reached it.
        # It was a noisy photocopy of the line (correlation 0.867) being
        # blended into projections at 40% weight.
        #
        # A replacement was built and rejected on the evidence: predicting the
        # residual (margin + spread) from causal walk-forward features, trained
        # season-by-season and tested forward, returned 50.9% ATS pooled over
        # 2023-2025 - under breakeven, with the apparent 2023 edge decaying to
        # below 50% by 2025, the signature of overfitting rather than skill.
        # See MODEL_NOTES.md. Projections now come from the rule-based model
        # and the Monte Carlo layer, both of which anchor on the market line.
        # 3. Monte Carlo simulation (the big one)
        try:
            mc = simulate_and_pick(g, n_sims=N_SIMS)
        except Exception as e:
            mc = {
                "simulation": {},
                "picks": {
                    "su_pick": None, "su_pick_abbr": None, "su_confidence": None,
                    "ats_pick": None, "ats_pick_abbr": None, "ats_spread": None, "ats_confidence": None,
                    "ou_pick": None, "ou_line": None, "ou_confidence": None,
                },
                "expected_margin": 0, "expected_total": 0, "has_odds": False,
            }

        # ── DISPLAYED PROJECTION = WHAT THE PICK ENGINE ACTUALLY BELIEVES ──
        # predictions_model.predict() builds a margin from scratch out of the
        # ratings, and when a side has almost no game history those ratings go
        # haywire: on 2026-09-02 it projected Furman to beat Tennessee by 111
        # while the market had Tennessee -46.5. The Monte Carlo layer does not
        # have that failure mode because it starts from the market line and
        # applies a capped adjustment, so its expected values are the honest
        # thing to show. The board and the picks now agree by construction.
        if mc.get("has_odds") and mc.get("expected_margin") is not None:
            em = float(mc["expected_margin"])
            et = float(mc.get("expected_total") or 0.0)
            if et > 0:
                hs = max(0.0, et / 2.0 + em / 2.0)
                as_ = max(0.0, et / 2.0 - em / 2.0)
                p["projected_home_score"] = round(hs, 1)
                p["projected_away_score"] = round(as_, 1)
                p["projected_total"] = round(hs + as_, 1)
            p["projected_spread"] = round(em, 1)
            try:
                p["win_probability_home"] = round(1 / (1 + math.exp(-em / 9.0)), 3)
            except OverflowError:
                pass
            model_used = "market_anchored"

        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}

        result = {
            "id": g.get("id"),
            "sport": g.get("sport"),
            "matchup": g.get("name"),
            "shortName": g.get("shortName"),
            "date_utc": g.get("date_utc"),
            "date_local": g.get("date_local"),
            "home": home_team.get("abbr") if isinstance(home_team, dict) else home_team,
            "away": away_team.get("abbr") if isinstance(away_team, dict) else away_team,
            "home_team": home_team if isinstance(home_team, dict) else {"name": home_team},
            "away_team": away_team if isinstance(away_team, dict) else {"name": away_team},
            "odds": g.get("odds", {}),
            "venue": g.get("venue"),
            "weather": g.get("weather"),
            "risk": g.get("weatherRisk"),
            # Structured favorite/underdog
            "fav_team": g.get("fav_team"),
            "dog_team": g.get("dog_team"),
            "fav_abbr": g.get("fav_abbr"),
            "dog_abbr": g.get("dog_abbr"),
            "fav_spread": g.get("fav_spread"),
            "dog_spread": g.get("dog_spread"),
            # Injuries
            "injury_count_home": g.get("injury_count_home", 0),
            "injury_count_away": g.get("injury_count_away", 0),
            # Market-anchored projection (see note above)
            "prediction": p,
            "model_used": model_used,
            # Monte Carlo simulation results
            "simulation": mc.get("simulation", {}),
            # EXPLICIT PICKS (from Monte Carlo)
            "picks": mc.get("picks", {}),
        }

        # High confidence flag — BEST BET card highlight
        # Should be rare: 1-3 per day max across ALL sports.
        # Requires a dominant SU lean AND at least one high-conf ATS or O/U pick.
        picks_data = mc.get("picks") or {}
        has_ats_best = picks_data.get("ats_high_conf", False)
        has_ou_best = picks_data.get("ou_high_conf", False)
        su_conf = picks_data.get("su_confidence") or 0
        if su_conf >= 75 and (has_ats_best or has_ou_best):
            result["highlight"] = True

        output["predictions"].append(result)

    output["count"] = len(output["predictions"])

    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2)

    # Lock picks for games that have started
    existing_locked = load_json(LOCKED_FILE, {"locked": []}).get("locked", [])
    prelock = (load_json(PRELOCK_FILE, {}) or {}).get("games", {})
    all_locked = lock_picks(output["predictions"], existing_locked, prelock)
    with open(PRELOCK_FILE, "w") as f:
        json.dump({"timestamp": datetime.now(timezone.utc).isoformat(),
                   "count": len(prelock), "games": prelock}, f, indent=2)

    locked_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(all_locked),
        "locked": all_locked,
    }
    with open(LOCKED_FILE, "w") as f:
        json.dump(locked_payload, f, indent=2)

    # Summary
    suppressed = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ats_suppressed"))
    picks_with_su = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("su_pick"))
    picks_with_ats = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ats_pick"))
    picks_with_ou = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ou_pick"))
    ats_high = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ats_high_conf"))
    ou_high = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ou_high_conf"))

    print(f"[predictions] {output['count']} games | rule-based + monte carlo | {suppressed} ATS picks suppressed (line disagreement beyond cap)")
    print(f"[picks] SU: {picks_with_su} | ATS: {picks_with_ats} ({ats_high} high-conf) | O/U: {picks_with_ou} ({ou_high} high-conf)")
    print(f"[locked] {len(all_locked)} total locked picks")


if __name__ == "__main__":
    main()
