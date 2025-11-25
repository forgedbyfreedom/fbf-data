#!/usr/bin/env python3
import json
import re
from pathlib import Path

COMBINED = Path("combined.json")
MASTER = Path("stadiums_master.json")
OUTFILE = Path("combined.json")   # overwrite combined with enriched version


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def normalize_name(name: str):
    if not name:
        return ""
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    n = n.replace("stadium", "").replace("field", "").replace("arena", "")
    n = n.replace("center", "").replace("coliseum", "").replace("dome", "")
    n = n.replace("the ", "")
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    return n.strip()


def find_master_match(venue, master):
    """Find the best stadium match by ID -> name -> normalized name."""
    vid = venue.get("id") or venue.get("venue_id")
    if vid and str(vid) in master:
        return master[str(vid)]

    vname = venue.get("name")
    if vname:
        norm = normalize_name(vname)
        # direct name matches
        for k, v in master.items():
            if normalize_name(v.get("name", "")) == norm:
                return v

    return None


def main():
    combined = load_json(COMBINED, {})
    master = load_json(MASTER, {})

    if not combined or "data" not in combined:
        print("❌ combined.json missing or empty")
        return

    updated = 0

    for game in combined["data"]:
        venue = game.get("venue")
        if not isinstance(venue, dict):
            continue

        match = find_master_match(venue, master)
        if not match:
            continue

        # Inject missing lat/lon
        if "lat" not in venue and "lat" in match:
            venue["lat"] = match["lat"]
            updated += 1

        if "lon" not in venue and "lon" in match:
            venue["lon"] = match["lon"]

    with open(OUTFILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Venues enriched with coordinates ({updated} venues updated).")


if __name__ == "__main__":
    main()
