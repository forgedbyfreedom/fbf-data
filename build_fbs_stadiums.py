import json, time, requests

COMBINED_PATH = "combined.json"
STADIUMS_MASTER_PATH = "stadiums_master.json"     # all venues keyed by venue_id
STADIUMS_BY_TEAM_PATH = "fbs_stadiums.json"       # home team_id -> venue dict (FBS + NFL)
STADIUMS_OUTDOOR_PATH = "stadiums_outdoor.json"   # only outdoor venues with coords

ESPN_VENUE_ENDPOINTS = {
    "ncaaf": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/venues/{vid}",
    "nfl":   "https://site.api.espn.com/apis/site/v2/sports/football/nfl/venues/{vid}",
}

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def safe_get(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default

def fetch_venue_from_espn(sport, venue_id):
    url_tpl = ESPN_VENUE_ENDPOINTS.get(sport)
    if not url_tpl or not venue_id:
        return None

    url = url_tpl.format(vid=venue_id)
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()

        venue = safe_get(data, "venue", {})
        address = safe_get(venue, "address", {}) or {}
        geo = safe_get(venue, "geo", {}) or {}

        lat = geo.get("latitude")
        lon = geo.get("longitude")

        return {
            "id": str(venue_id),
            "name": venue.get("fullName") or venue.get("name"),
            "city": address.get("city"),
            "state": address.get("state"),
            "lat": lat,
            "lon": lon,
            "indoor": bool(venue.get("indoor") or venue.get("roof") == "dome"),
            "grass": (venue.get("surface") or "").lower() in ["grass", "natural grass"],
            "source": "espn"
        }
    except:
        return None

def normalize_venue(g, sport):
    """
    Try to produce a full venue dict:
    1) Use g["venue"] if it already has lat/lon (some ESPN feeds include geo)
    2) Else fetch venue info from ESPN venue endpoint using venue id
    """
    v = safe_get(g, "venue", {})
    if isinstance(v, dict):
        lat = v.get("lat") or v.get("latitude")
        lon = v.get("lon") or v.get("longitude")

        if lat and lon:
            return {
                "id": str(v.get("id") or v.get("venue_id") or ""),
                "name": v.get("name"),
                "city": v.get("city"),
                "state": v.get("state"),
                "lat": float(lat),
                "lon": float(lon),
                "indoor": bool(v.get("indoor")),
                "grass": bool(v.get("grass")),
                "source": "combined"
            }

    # fetch from ESPN if possible
    venue_id = None
    if isinstance(v, dict):
        venue_id = v.get("id") or v.get("venue_id")
    venue_id = venue_id or g.get("venue_id")

    if venue_id:
        fetched = fetch_venue_from_espn(sport, venue_id)
        if fetched:
            return fetched

    return None

def main():
    combined = load_json(COMBINED_PATH, [])
    if isinstance(combined, dict) and "data" in combined:
        games = combined["data"]
    else:
        games = combined

    stadiums_master = {}
    stadiums_by_team = {}

    seen_requests = 0

    for g in games:
        if not isinstance(g, dict):
            continue

        sport = (g.get("sport") or "").lower()

        # We only build stadium tables for FBS + NFL
        if sport not in ["ncaaf", "nfl"]:
            continue

        home = safe_get(g, "home_team", {}) or {}
        home_id = str(home.get("id") or "")

        if not home_id:
            continue

        venue = normalize_venue(g, sport)

        if venue:
            vid = venue.get("id") or f"{sport}_{home_id}"

            stadiums_master[str(vid)] = venue
            stadiums_by_team[home_id] = venue

            # Be nice to ESPN endpoint
            if venue.get("source") == "espn":
                seen_requests += 1
                if seen_requests % 10 == 0:
                    time.sleep(0.6)

    # Filter outdoor venues with coords (NO crash even if garbage types exist)
    outdoor = {}
    for tid, v in stadiums_by_team.items():
        if not isinstance(v, dict):
            continue
        if v.get("indoor"):
            continue
        if not v.get("lat") or not v.get("lon"):
            continue
        outdoor[tid] = v

    with open(STADIUMS_MASTER_PATH, "w") as f:
        json.dump(stadiums_master, f, indent=2)

    with open(STADIUMS_BY_TEAM_PATH, "w") as f:
        json.dump(stadiums_by_team, f, indent=2)

    with open(STADIUMS_OUTDOOR_PATH, "w") as f:
        json.dump(outdoor, f, indent=2)

    print(f"[✅] stadiums_master.json built: {len(stadiums_master)} venues")
    print(f"[✅] fbs_stadiums.json built: {len(stadiums_by_team)} teams (FBS + NFL)")
    print(f"[✅] stadiums_outdoor.json built: {len(outdoor)} outdoor teams")

if __name__ == "__main__":
    main()
