#!/usr/bin/env python3
import json
import re
from pathlib import Path

COMBINED = Path("combined.json")
MASTER = Path("stadiums_master.json")
OUTFILE = Path("combined.json")


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n


def find_match(venue, master):
    """Match by name normalization."""
    name = venue.get("name")
    if not name:
        return None

    key = normalize(name)
    return master.get(key)


def main():
    combined = load_json(COMBINED, {})
    master = load_json(MASTER, {})

    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    updated = 0

    for g in combined["data"]:
        venue = g.get("venue")
        if not isinstance(venue, dict):
            continue

        match = find_match(venue, master)
        if not match:
            continue

        # Inject coordinates
        if "lat" in match and venue.get("lat") is None:
            venue["lat"] = match["lat"]
            updated += 1

        if "lon" in match and venue.get("lon") is None:
            venue["lon"] = match["lon"]

    with open(OUTFILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"📌 Updated combined.json with coordinates for {updated} venues.")


if __name__ == "__main__":
    main()
