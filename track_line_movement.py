#!/usr/bin/env python3
"""
track_line_movement.py
Snapshots current spread/total for every game in combined.json.
Each run appends a timestamped snapshot to line_snapshots.json.
Computes line movement (opening → current) for use in predictions.

Output: line_movement.json  (per-game movement summary)
        line_snapshots.json (raw snapshot history)

Run AFTER: fetch_espn_all.py, tag_favorites.py
Run BEFORE: merge_features.py
"""

import json, os
from datetime import datetime, timezone

COMBINED = "combined.json"
SNAPSHOTS_FILE = "line_snapshots.json"
MOVEMENT_FILE = "line_movement.json"


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])
    if not games:
        print("[line_movement] No games in combined.json")
        return

    now = datetime.now(timezone.utc).isoformat()

    # Load existing snapshots
    snapshots = load_json(SNAPSHOTS_FILE, {})
    # snapshots structure: { game_id: [ { timestamp, spread, total, ml_home, ml_away } ] }

    new_snaps = 0
    for g in games:
        game_id = str(g.get("id") or g.get("event_id") or "")
        if not game_id:
            continue

        spread = g.get("spread")
        total = g.get("total")

        # Also check odds dict
        odds = g.get("odds", {})
        if spread is None and isinstance(odds, dict):
            spread = odds.get("spread")
        if total is None and isinstance(odds, dict):
            total = odds.get("total") or odds.get("overUnder")

        # Get moneylines if available
        ml_home = g.get("moneyline_home")
        ml_away = g.get("moneyline_away")

        # Skip games with no odds at all
        if spread is None and total is None and ml_home is None:
            continue

        snap = {
            "timestamp": now,
            "spread": spread,
            "total": total,
        }
        if ml_home is not None:
            snap["ml_home"] = ml_home
        if ml_away is not None:
            snap["ml_away"] = ml_away

        if game_id not in snapshots:
            snapshots[game_id] = []

        # Don't store duplicate if spread/total haven't changed since last snapshot
        existing = snapshots[game_id]
        if existing:
            last = existing[-1]
            if last.get("spread") == spread and last.get("total") == total:
                continue  # no change

        snapshots[game_id].append(snap)
        new_snaps += 1

    # Write snapshots
    with open(SNAPSHOTS_FILE, "w") as f:
        json.dump(snapshots, f, indent=2)

    # Compute line movement summary for each game
    movement = {}
    for game_id, snaps in snapshots.items():
        if len(snaps) < 1:
            continue

        opening = snaps[0]
        current = snaps[-1]
        num_moves = len(snaps) - 1

        open_spread = opening.get("spread")
        curr_spread = current.get("spread")
        open_total = opening.get("total")
        curr_total = current.get("total")

        spread_delta = None
        if open_spread is not None and curr_spread is not None:
            try:
                spread_delta = round(float(curr_spread) - float(open_spread), 1)
            except (ValueError, TypeError):
                pass

        total_delta = None
        if open_total is not None and curr_total is not None:
            try:
                total_delta = round(float(curr_total) - float(open_total), 1)
            except (ValueError, TypeError):
                pass

        # Classify spread movement direction
        spread_direction = "stable"
        if spread_delta is not None:
            if spread_delta < -0.5:
                spread_direction = "toward_favorite"  # line getting bigger (fav more favored)
            elif spread_delta > 0.5:
                spread_direction = "toward_underdog"  # line getting smaller
            # Note: "toward_favorite" means sharp money on fav

        # Classify total movement
        total_direction = "stable"
        if total_delta is not None:
            if total_delta > 0.5:
                total_direction = "up"  # total going up = market expects more scoring
            elif total_delta < -0.5:
                total_direction = "down"

        movement[game_id] = {
            "open_spread": open_spread,
            "current_spread": curr_spread,
            "spread_delta": spread_delta,
            "spread_direction": spread_direction,
            "spread_moves": num_moves,
            "open_total": open_total,
            "current_total": curr_total,
            "total_delta": total_delta,
            "total_direction": total_direction,
            "first_seen": opening.get("timestamp"),
            "last_updated": current.get("timestamp"),
        }

    with open(MOVEMENT_FILE, "w") as f:
        json.dump(movement, f, indent=2)

    has_movement = sum(1 for m in movement.values()
                       if (m.get("spread_delta") and m["spread_delta"] != 0)
                       or (m.get("total_delta") and m["total_delta"] != 0))

    print(f"[line_movement] {new_snaps} new snapshots, {len(movement)} games tracked, {has_movement} with movement")


if __name__ == "__main__":
    main()
