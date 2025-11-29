#!/usr/bin/env python3
import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent

COMBINED_PATH = ROOT / "combined.json"
INJURIES_PATH = ROOT / "injuries.json"
PREDICTIONS_PATH = ROOT / "predictions.json"


def load_json(path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def coerce_injury_list_container(raw):
    """
    Try to coerce injuries.json into a list of records.
    Accepts shapes like:
      - [ {...}, {...} ]
      - { "injuries": [ ... ] }
      - { "data": [ ... ] }
      - { "games": [ ... ] }
    """
    if raw is None:
        return []

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        for key in ("injuries", "data", "games", "records"):
            if isinstance(raw.get(key), list):
                return raw[key]

    # Unknown / unsupported shape; fail soft
    return []


def normalize_player_obj(rec):
    """
    Normalize a single injury record into a small dict that
    your frontend can display consistently.
    """
    name = (
        rec.get("name")
        or rec.get("player")
        or rec.get("full_name")
        or rec.get("displayName")
        or rec.get("athlete")
        or rec.get("athlete_name")
    )
    status = (
        rec.get("status")
        or rec.get("injury_status")
        or rec.get("designation")
        or rec.get("detail_status")
    )
    position = rec.get("position") or rec.get("pos")
    body_part = rec.get("body_part") or rec.get("injury")
    note = rec.get("note") or rec.get("description") or rec.get("comment")

    obj = {}
    if name:
        obj["name"] = name
    if status:
        obj["status"] = status
    if position:
        obj["position"] = position
    if body_part:
        obj["body_part"] = body_part
    if note:
        obj["note"] = note

    return obj if obj else None


def side_from_record(rec):
    """
    Try to determine whether this injury record is home or away.
    Looks at common fields, falls back to None if unknown.
    """
    side = (
        rec.get("home_away")
        or rec.get("side")
        or rec.get("team_side")
        or rec.get("team_role")
    )
    if isinstance(side, str):
        s = side.lower()
        if s in ("home", "h"):
            return "home"
        if s in ("away", "a", "visitor", "road"):
            return "away"
    return None


def game_id_from_record(rec):
    """
    Extract a game/event id from an injury record in injuries.json.
    Tries multiple common field names.
    """
    for key in ("game_id", "event_id", "id", "espn_id"):
        if rec.get(key) is not None:
            return str(rec[key])
    return None


def merge_lists_dedup(base, extra):
    """
    Merge two lists of player injury dicts, deduplicating on (name, status).
    """
    if not base and not extra:
        return []

    base = base or []
    extra = extra or []

    seen = set()
    out = []

    def mark_and_add(item):
        if not isinstance(item, dict):
            return
        name = item.get("name")
        status = item.get("status")
        key = (name, status)
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    for lst in (base, extra):
        for it in lst:
            mark_and_add(it)

    return out


def build_injury_index_from_injuries_json(raw_records):
    """
    Build an index:
       game_id -> { "home": [playerObjs], "away": [playerObjs] }
    from injuries.json, supporting both:
      - game-level: { game_id: ..., home_injuries: [...], away_injuries: [...] }
      - player-level: { game_id: ..., home_away: "home"/"away", ... }
    """
    index = defaultdict(lambda: {"home": [], "away": []})

    for rec in raw_records:
        if not isinstance(rec, dict):
            continue

        gid = game_id_from_record(rec)
        if not gid:
            continue

        # Case 1: already summarized per game
        if isinstance(rec.get("home_injuries"), list) or isinstance(
            rec.get("away_injuries"), list
        ):
            home_list = rec.get("home_injuries") or rec.get("home") or []
            away_list = rec.get("away_injuries") or rec.get("away") or []

            home_norm = [normalize_player_obj(x) for x in home_list]
            away_norm = [normalize_player_obj(x) for x in away_list]

            index[gid]["home"].extend([x for x in home_norm if x])
            index[gid]["away"].extend([x for x in away_norm if x])
            continue

        # Case 2: single-player record with side
        side = side_from_record(rec)
        player_obj = normalize_player_obj(rec)
        if side and player_obj:
            index[gid][side].append(player_obj)

    return index


def build_injury_index_from_predictions(pred_json):
    """
    If you ever add injuries into predictions.json, we pull them too.
    Expected shapes per prediction row:
      - {..., "id": "401...", "injuries": { "home": [...], "away": [...] } }
      - or "home_injuries"/"away_injuries" top-level.
    Returns same index as above.
    """
    if pred_json is None:
        return {}

    records = pred_json.get("data") or pred_json.get("predictions") or []
    index = defaultdict(lambda: {"home": [], "away": []})

    for rec in records:
        if not isinstance(rec, dict):
            continue
        gid = rec.get("id") or rec.get("game_id") or rec.get("event_id")
        if gid is None:
            continue
        gid = str(gid)

        bucket = index[gid]

        inj_container = rec.get("injuries")
        if isinstance(inj_container, dict):
            home_list = inj_container.get("home") or inj_container.get("home_injuries")
            away_list = inj_container.get("away") or inj_container.get("away_injuries")
        else:
            home_list = rec.get("home_injuries")
            away_list = rec.get("away_injuries")

        for raw_list, side_key in ((home_list, "home"), (away_list, "away")):
            if not isinstance(raw_list, list):
                continue
            for x in raw_list:
                norm = normalize_player_obj(x) if isinstance(x, dict) else None
                if norm:
                    bucket[side_key].append(norm)

    return index


def main():
    combined = load_json(COMBINED_PATH)
    if combined is None:
        raise SystemExit(f"❌ {COMBINED_PATH} not found")

    # Extract games array from combined.json
    if isinstance(combined, dict):
        games = (
            combined.get("data")
            or combined.get("games")
            or combined.get("combined")
            or []
        )
    elif isinstance(combined, list):
        games = combined
    else:
        raise SystemExit("❌ combined.json has unexpected shape")

    if not isinstance(games, list):
        raise SystemExit("❌ combined.json: could not find games list")

    injuries_raw = coerce_injury_list_container(load_json(INJURIES_PATH))
    preds_json = load_json(PREDICTIONS_PATH)

    inj_idx_inj_file = build_injury_index_from_injuries_json(injuries_raw)
    inj_idx_preds = build_injury_index_from_predictions(preds_json)

    # Merge the two indexes: injuries.json wins, then predictions
    merged_index = defaultdict(lambda: {"home": [], "away": []})

    for gid, buckets in inj_idx_preds.items():
        merged_index[gid]["home"].extend(buckets["home"])
        merged_index[gid]["away"].extend(buckets["away"])

    for gid, buckets in inj_idx_inj_file.items():
        merged_index[gid]["home"].extend(buckets["home"])
        merged_index[gid]["away"].extend(buckets["away"])

    games_with_injuries = 0

    for game in games:
        if not isinstance(game, dict):
            continue

        gid = str(
            game.get("id")
            or game.get("game_id")
            or game.get("event_id")
            or game.get("uid")
            or ""
        )

        # existing injuries on combined.json (from ESPN or previous merges)
        existing_home = game.get("home_injuries") or []
        existing_away = game.get("away_injuries") or []

        # or nested under "injuries"
        if isinstance(game.get("injuries"), dict):
            existing_home += game["injuries"].get("home_injuries", []) or game[
                "injuries"
            ].get("home", [])
            existing_away += game["injuries"].get("away_injuries", []) or game[
                "injuries"
            ].get("away", [])

        # new injuries from merged index
        new_bucket = merged_index.get(gid, {"home": [], "away": []})
        new_home = new_bucket["home"]
        new_away = new_bucket["away"]

        final_home = merge_lists_dedup(existing_home, new_home)
        final_away = merge_lists_dedup(existing_away, new_away)

        total = len(final_home) + len(final_away)
        if total == 0:
            # still normalize counts to 0 so frontend logic is simpler
            game["home_injuries"] = []
            game["away_injuries"] = []
            game["injury_count_home"] = 0
            game["injury_count_away"] = 0
            game["injury_total"] = 0
            game["injuries"] = {
                "home_injuries": [],
                "away_injuries": [],
            }
            continue

        games_with_injuries += 1

        game["home_injuries"] = final_home
        game["away_injuries"] = final_away
        game["injury_count_home"] = len(final_home)
        game["injury_count_away"] = len(final_away)
        game["injury_total"] = total
        game["injuries"] = {
            "home_injuries": final_home,
            "away_injuries": final_away,
        }

    # Write back combined.json in the same shape it came in
    if isinstance(combined, dict):
        if "data" in combined and isinstance(combined["data"], list):
            combined["data"] = games
        elif "games" in combined and isinstance(combined["games"], list):
            combined["games"] = games
        elif "combined" in combined and isinstance(combined["combined"], list):
            combined["combined"] = games
        else:
            # fallback: just drop games into "data"
            combined["data"] = games
        out_obj = combined
    else:
        out_obj = games

    with COMBINED_PATH.open("w", encoding="utf-8") as f:
        json.dump(out_obj, f, indent=2, sort_keys=False)

    total_games = len(games)
    print(f"[✅] Hybrid injuries merged onto {games_with_injuries}/{total_games} games.")


if __name__ == "__main__":
    main()
