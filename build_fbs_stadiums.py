import json
import time
import requests
from typing import Dict, Any, Optional, List, Set

COMBINED_PATH = "combined.json"
OUT_PATH = "fbs_stadiums.json"

TEAM_API = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{}"
VENUE_API = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{}"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "fbf-data stadium-builder (contact@forgedbyfreedom.com)"
})

def load_json(path: str, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def safe_get(d: Dict[str, Any], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def fetch_json(url: str, retries: int = 3, backoff: float = 1.2) -> Optional[Dict[str, Any]]:
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(backoff * (i + 1))
    return None

def normalize_bool(x) -> Optional[bool]:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "yes", "1"):
            return True
        if s in ("false", "no", "0"):
            return False
    return None

def extract_team_ids(combined: Any) -> Set[str]:
    # combined.json format can be dict with "data" or already list
    games = combined.get("data") if isinstance(combined, dict) else combined
    if not isinstance(games, list):
        return set()

    team_ids = set()
    for g in games:
        if not isinstance(g, dict):
            continue
        if (g.get("sport") or "").lower() != "ncaaf":
            continue

        ht = g.get("home_team") or {}
        at = g.get("away_team") or {}
        hid = ht.get("id")
        aid = at.get("id")
        if hid: team_ids.add(str(hid))
        if aid: team_ids.add(str(aid))

    return team_ids

def build_stadium_entry(team_id: str) -> Optional[Dict[str, Any]]:
    team_payload = fetch_json(TEAM_API.format(team_id))
    if not team_payload:
        return None

    team = safe_get(team_payload, "team", default={}) or {}
    venue = team.get("venue") or {}

    venue_id = venue.get("id") or venue.get("$ref", "").rstrip("/").split("/")[-1]
    venue_name = venue.get("fullName") or venue.get("name")

    # address/location sometimes lives in team.venue.address OR venue.address
    address = venue.get("address") or {}
    city = address.get("city")
    state = address.get("state")

    lat = venue.get("latitude")
    lon = venue.get("longitude")

    indoor = normalize_bool(venue.get("indoor"))
    grass = normalize_bool(venue.get("grass"))

    # If lat/lon missing, try venue core API
    if venue_id and (lat is None or lon is None):
        v_payload = fetch_json(VENUE_API.format(venue_id))
        if v_payload:
            venue_name = venue_name or v_payload.get("fullName") or v_payload.get("name")

            addr2 = v_payload.get("address") or {}
            city = city or addr2.get("city")
            state = state or addr2.get("state")

            lat = lat or v_payload.get("latitude")
            lon = lon or v_payload.get("longitude")

            indoor = indoor if indoor is not None else normalize_bool(v_payload.get("indoor"))
            grass = grass if grass is not None else normalize_bool(v_payload.get("grass"))

    # still no coords? skip; weather pipeline will mark no_coords
    if lat is None or lon is None:
        return {
            "team_id": team_id,
            "team_name": team.get("displayName"),
            "team_abbr": team.get("abbreviation"),
            "stadium_id": venue_id,
            "stadium_name": venue_name,
            "city": city,
            "state": state,
            "lat": None,
            "lon": None,
            "indoor": indoor if indoor is not None else False,
            "grass": grass if grass is not None else True,
            "error": "no_coords"
        }

    return {
        "team_id": team_id,
        "team_name": team.get("displayName"),
        "team_abbr": team.get("abbreviation"),
        "stadium_id": venue_id,
        "stadium_name": venue_name,
        "city": city,
        "state": state,
        "lat": float(lat),
        "lon": float(lon),
        "indoor": indoor if indoor is not None else False,
        "grass": grass if grass is not None else True
    }

def main():
    combined = load_json(COMBINED_PATH, {})
    team_ids = extract_team_ids(combined)

    out_by_team: Dict[str, Any] = {}
    out_list: List[Any] = []

    if not team_ids:
        print("⚠️ No ncaaf teams found in combined.json. Stadium output will be empty.")
    else:
        print(f"🏟️ Building stadiums for {len(team_ids)} FBS teams from ESPN IDs...")

    for idx, tid in enumerate(sorted(team_ids), start=1):
        entry = build_stadium_entry(tid)
        if entry:
            out_by_team[tid] = entry
            out_list.append(entry)
        else:
            out_by_team[tid] = {"team_id": tid, "error": "team_fetch_failed"}

        # light rate limit to avoid ESPN throttling
        if idx % 10 == 0:
            time.sleep(0.6)
        else:
            time.sleep(0.15)

    payload = {
        "count": len(out_list),
        "by_team_id": out_by_team,
        "data": out_list
    }

    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUT_PATH} with {len(out_list)} stadiums.")

if __name__ == "__main__":
    main()
