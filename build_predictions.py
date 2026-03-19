#!/usr/bin/env python3
"""
build_predictions.py
Generates predictions.json from combined.json using:
1. Monte Carlo simulation (10K sims per game)
2. Rule-based model (predictions_model.py)
3. Optional ML ensemble (models/spread_model.pkl)

Outputs explicit SU, ATS, O/U picks for every game.
Locks picks at game time into predictions_locked.json.
"""
import json, os, pickle, math
from pathlib import Path
from datetime import datetime, timezone
from predictions_model import predict
from monte_carlo import simulate_and_pick

COMBINED = Path("combined.json")
OUTFILE = Path("predictions.json")
LOCKED_FILE = Path("predictions_locked.json")
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


def lock_picks(current_predictions, existing_locked):
    """
    Lock picks at game time. Once a game's start time has passed,
    the pick is final and cannot change.
    """
    now = datetime.now(timezone.utc)
    locked_by_id = {str(p.get("id")): p for p in existing_locked}
    new_locks = 0

    for pred in current_predictions:
        pid = str(pred.get("id") or "")
        if not pid:
            continue

        # Already locked? Keep the locked version
        if pid in locked_by_id:
            continue

        # Check if game has started
        date_utc = pred.get("date_utc")
        if not date_utc:
            continue

        try:
            game_time = datetime.fromisoformat(date_utc.replace("Z", "+00:00"))
        except Exception:
            continue

        if now >= game_time:
            # Game has started or passed - lock this pick
            locked_pred = dict(pred)
            locked_pred["locked_at"] = now.isoformat()
            locked_by_id[pid] = locked_pred
            new_locks += 1

    all_locked = list(locked_by_id.values())
    if new_locks > 0:
        print(f"[picks] Locked {new_locks} new picks ({len(all_locked)} total locked)")

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

    # Load ML models
    spread_model, total_model, feature_cols = load_ml_models()
    has_ml = spread_model is not None
    if has_ml:
        print(f"[ML] Loaded spread model with {len(feature_cols)} features")

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

        # 2. ML ensemble
        if has_ml and not p.get("error"):
            ml_margin, ml_total = ml_predict(g, spread_model, total_model, feature_cols)
            if ml_margin is not None:
                rule_margin = p["projected_spread"]
                ensemble_margin = 0.6 * rule_margin + 0.4 * ml_margin
                rule_total = p["projected_total"]
                ensemble_total = 0.6 * rule_total + 0.4 * ml_total if ml_total else rule_total

                home_score = max(3.0, ensemble_total / 2 + ensemble_margin / 2)
                away_score = max(3.0, ensemble_total / 2 - ensemble_margin / 2)

                p["projected_home_score"] = round(home_score, 1)
                p["projected_away_score"] = round(away_score, 1)
                p["projected_total"] = round(home_score + away_score, 1)
                p["projected_spread"] = round(home_score - away_score, 1)

                try:
                    p["win_probability_home"] = round(1 / (1 + math.exp(-(home_score - away_score) / 6)), 3)
                except OverflowError:
                    pass

                model_used = "ensemble"

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
            # Rule-based + ensemble prediction
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
    all_locked = lock_picks(output["predictions"], existing_locked)

    locked_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(all_locked),
        "locked": all_locked,
    }
    with open(LOCKED_FILE, "w") as f:
        json.dump(locked_payload, f, indent=2)

    # Summary
    ensemble_count = sum(1 for r in output["predictions"] if r.get("model_used") == "ensemble")
    picks_with_su = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("su_pick"))
    picks_with_ats = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ats_pick"))
    picks_with_ou = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ou_pick"))
    ats_high = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ats_high_conf"))
    ou_high = sum(1 for r in output["predictions"] if (r.get("picks") or {}).get("ou_high_conf"))

    print(f"[predictions] {output['count']} games | {ensemble_count} ensemble, {output['count'] - ensemble_count} rule-based")
    print(f"[picks] SU: {picks_with_su} | ATS: {picks_with_ats} ({ats_high} high-conf) | O/U: {picks_with_ou} ({ou_high} high-conf)")
    print(f"[locked] {len(all_locked)} total locked picks")


if __name__ == "__main__":
    main()
