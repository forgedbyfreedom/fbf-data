import json
import os


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def normalize_combined(combined):
    # combined.json can be {"timestamp":..., "count":..., "data":[...]}
    if isinstance(combined, dict) and "data" in combined:
        return combined["data"]
    if isinstance(combined, list):
        return combined
    return []


def venue_key(v):
    # stable venue id first, else fallback to slugged name
    if isinstance(v, dict):
        vid = v.get("id") or v.get("venue_id")
        if vid:
            return str(vid)
        nm = (v.get("name") or "").strip().lower()
        city = (v.get("city") or "").strip().lower()
        st = (v.get("state") or "").strip().lower()
        return f"{nm}|{city}|{st}"
    return None


def merge_venue(base, incoming):
    """
    Merge two venue dicts, preferring existing good data,
    but filling missing lat/lon/indoor/etc from incoming.
    """
    if not isinstance(base, dict):
        base = {}
    if not isinstance(incoming, dict):
        return base

    for k, v in incoming.items():
        if v is None:
            continue
        if k not in base or base.get(k) in (None, "", 0):
            base[k] = v

    # normalize types
    for kk in ("lat", "lon"):
        if kk in base and base[kk] is not None:
            try:
                base[kk] = float(base[kk])
            except Exception:
                base[kk] = None

    if "indoor" in base:
        base["indoor"] = bool(base["indoor"])

    return base


def main():
    combined = normalize_combined(load_json("combined.json", []))
    master = load_json("data/stadiums_master.json", {})
    if not isinstance(master, dict):
        master = {}

    fbs = {}
    outdoor = {}

    # 1) Pull venues from combined.json (ESPN data)
    for g in combined:
        if not isinstance(g, dict):
            continue

        sport = (g.get("sport") or "").lower()
        if sport not in ("ncaaf", "nfl"):  # FBS + NFL in one master
            continue

        v = g.get("venue") or {}
        if not isinstance(v, dict):
            continue

        key = venue_key(v)
        if not key:
            continue

        # Build minimal incoming venue from combined
        incoming = {
            "id": v.get("id") or v.get("venue_id"),
            "name": v.get("name"),
            "city": v.get("city"),
            "state": v.get("state"),
            "indoor": bool(v.get("indoor")),
            "grass": v.get("grass"),
            "lat": v.get("lat") or v.get("latitude"),
            "lon": v.get("lon") or v.get("longitude"),
            "source": "combined_espn"
        }

        # Merge with any existing master record
        existing = master.get(key, {})
        merged = merge_venue(existing, incoming)
        master[key] = merged

    # 2) Create fbs_stadiums from master
    for k, v in master.items():
        if not isinstance(v, dict):
            continue

        # keep only venues with usable identity
        if not v.get("name"):
            continue

        # fbs file should contain all FBS + NFL venues we saw
        fbs[k] = v

        # outdoor subset needs coords + not indoor
        if (not v.get("indoor")) and v.get("lat") and v.get("lon"):
            outdoor[k] = v

    save_json("data/stadiums_master.json", master)
    save_json("fbs_stadiums.json", fbs)
    save_json("stadiums_outdoor.json", outdoor)

    print(f"✅ Wrote fbs_stadiums.json with {len(fbs)} venues")
    print(f"✅ Wrote stadiums_outdoor.json with {len(outdoor)} outdoor venues")
    print("✅ stadiums_master.json updated")


if __name__ == "__main__":
    main()
