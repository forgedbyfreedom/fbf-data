#!/usr/bin/env python3
"""
fetch_referees.py

Fetches referee/umpire assignments for upcoming games from external sources
and merges them into combined.json so the prediction pipeline can use ref trends.

Sources:
  - MLB: statsapi.mlb.com (free JSON API, no auth)
  - NBA: official.nba.com/referee-assignments/ (HTML scrape)
  - NHL: scoutingtherefs.com (HTML scrape)
  - NFL: footballzebras.com (HTML scrape)

Runs AFTER fetch_espn_all.py and BEFORE merge_features.py in the pipeline.
"""

import json, os, re, requests, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

COMBINED_FILE = "combined.json"
NY_TZ = ZoneInfo("America/New_York")
TIMEOUT = 15
RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
}


def get(url, as_json=True):
    """Fetch URL with retries and backoff."""
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as ex:
            if attempt < RETRIES - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                print(f"[refs] GET failed: {url} -- {ex}")
                return None


def normalize_name(name):
    """Normalize team name for fuzzy matching."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def normalize_ref_name(name):
    """Normalize referee name for matching against trends."""
    if not name:
        return ""
    return name.strip()


# ─────────────────────────────────────────────
#  MLB — statsapi.mlb.com (best source, JSON)
# ─────────────────────────────────────────────
def fetch_mlb_officials(games):
    """Fetch MLB umpire assignments from the official Stats API."""
    mlb_games = [g for g in games if (g.get("sport") or "").lower() == "mlb"]
    if not mlb_games:
        return 0

    # Collect unique dates from MLB games
    dates = set()
    for g in mlb_games:
        dt = g.get("date_utc") or g.get("commence_time") or ""
        try:
            d = datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(NY_TZ).date()
            dates.add(d)
        except Exception:
            pass

    if not dates:
        return 0

    matched = 0
    for d in sorted(dates):
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={d.isoformat()}&hydrate=officials"
        data = get(url)
        if not data:
            continue

        for date_entry in data.get("dates", []):
            for api_game in date_entry.get("games", []):
                officials_list = []
                for off in api_game.get("officials", []):
                    name = off.get("official", {}).get("fullName", "")
                    role = off.get("officialType", "")
                    if name:
                        officials_list.append({"name": name, "role": role.lower()})

                if not officials_list:
                    continue

                # Match by team names
                away_api = (api_game.get("teams", {}).get("away", {})
                            .get("team", {}).get("name", ""))
                home_api = (api_game.get("teams", {}).get("home", {})
                            .get("team", {}).get("name", ""))

                away_n = normalize_name(away_api)
                home_n = normalize_name(home_api)

                for g in mlb_games:
                    if g.get("officials") and len(g["officials"]) > 0:
                        continue  # Already has officials

                    g_home = normalize_name(
                        g.get("home_team", {}).get("name", "") if isinstance(g.get("home_team"), dict)
                        else g.get("home_team", "")
                    )
                    g_away = normalize_name(
                        g.get("away_team", {}).get("name", "") if isinstance(g.get("away_team"), dict)
                        else g.get("away_team", "")
                    )
                    g_home_abbr = normalize_name(g.get("home", ""))
                    g_away_abbr = normalize_name(g.get("away", ""))

                    if ((home_n and (home_n in g_home or g_home in home_n or home_n in g_home_abbr)) and
                        (away_n and (away_n in g_away or g_away in away_n or away_n in g_away_abbr))):
                        g["officials"] = officials_list
                        matched += 1
                        break

    print(f"[refs] MLB: matched officials for {matched}/{len(mlb_games)} games")
    return matched


# ─────────────────────────────────────────────
#  NBA — cdn.nba.com boxscore API (free, no auth)
# ─────────────────────────────────────────────
def fetch_nba_officials(games):
    """Fetch NBA referee assignments from NBA CDN boxscore API.
    Officials populate on game day, often by tipoff time."""
    nba_games = [g for g in games if (g.get("sport") or "").lower() == "nba"]
    if not nba_games:
        return 0

    # Step 1: Get today's NBA scoreboard for game IDs
    scoreboard_url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
    sb = get(scoreboard_url)
    if not sb:
        print("[refs] NBA: could not fetch scoreboard")
        return 0

    nba_api_games = sb.get("scoreboard", {}).get("games", [])
    if not nba_api_games:
        print("[refs] NBA: no games on scoreboard today")
        return 0

    matched = 0
    for api_game in nba_api_games:
        game_id = api_game.get("gameId", "")
        if not game_id:
            continue

        # Try boxscore for officials
        box_url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
        box = get(box_url)
        if not box:
            continue

        officials_raw = box.get("game", {}).get("officials", [])
        if not officials_raw:
            continue

        role_map = {"OFFICIAL1": "crew chief", "OFFICIAL2": "referee", "OFFICIAL3": "umpire"}
        officials_list = [
            {"name": o.get("name", ""), "role": role_map.get(o.get("assignment", ""), "official")}
            for o in officials_raw if o.get("name")
        ]
        if not officials_list:
            continue

        # Match by team name
        api_home = normalize_name(api_game.get("homeTeam", {}).get("teamName", ""))
        api_away = normalize_name(api_game.get("awayTeam", {}).get("teamName", ""))

        for g in nba_games:
            if g.get("officials") and len(g["officials"]) > 0:
                continue

            g_home = normalize_name(
                g.get("home_team", {}).get("name", "") if isinstance(g.get("home_team"), dict)
                else g.get("home_team", "")
            )
            g_away = normalize_name(
                g.get("away_team", {}).get("name", "") if isinstance(g.get("away_team"), dict)
                else g.get("away_team", "")
            )

            # Match: API uses short names like "76ers", combined.json has full "Philadelphia 76ers"
            if api_home and api_away and g_home and g_away:
                if (api_home in g_home or g_home in api_home) and \
                   (api_away in g_away or g_away in api_away):
                    g["officials"] = officials_list
                    matched += 1
                    break

    print(f"[refs] NBA: matched officials for {matched}/{len(nba_games)} games")
    return matched


# ─────────────────────────────────────────────
#  NHL — scoutingtherefs.com (HTML scrape)
# ─────────────────────────────────────────────
def fetch_nhl_officials(games):
    """Fetch NHL referee assignments from scoutingtherefs.com."""
    nhl_games = [g for g in games if (g.get("sport") or "").lower() == "nhl"]
    if not nhl_games:
        return 0

    today = datetime.now(NY_TZ).date()

    # Step 1: Get post links from category page
    cat_url = "https://scoutingtherefs.com/category/tonights-officials/nhl-tonights-officials/"
    cat_html = get(cat_url, as_json=False)

    post_urls = []
    if cat_html:
        # Find links to daily referee assignment posts (current year)
        current_year = today.year
        links = re.findall(
            rf'href="(https?://scoutingtherefs\.com/{current_year}/\d{{2}}/\d+/[^"#]+)"',
            cat_html
        )
        # Deduplicate, take most recent 3 posts (covers today + yesterday + day before)
        seen = set()
        for link in links:
            if link not in seen and "referees-and-linespersons" in link:
                seen.add(link)
                post_urls.append(link)
            if len(post_urls) >= 3:
                break

    if not post_urls:
        print("[refs] NHL: no posts found on scoutingtherefs.com")
        return 0

    matched = 0
    for post_url in post_urls:
        html = get(post_url, as_json=False)
        if not html:
            continue

        # Parse: <strong>Team at Team</strong> blocks followed by official lines
        # Officials appear as "Name #number" or "#number Name" in <strong> tags
        strongs = re.findall(r'<strong[^>]*>(.*?)</strong>', html, re.DOTALL)

        current_matchup = None
        current_refs = []

        for raw in strongs:
            text = re.sub(r'<[^>]+>', '', raw).strip()
            text = text.replace("&#8211;", "–").replace("&#8217;", "'")

            if not text or len(text) < 3:
                continue

            # Check if this is a matchup line ("Team at Team")
            if re.search(r'\b(?:at|vs\.?)\b', text, re.IGNORECASE) and len(text) < 80 and '#' not in text:
                # Save previous matchup
                if current_matchup and current_refs:
                    if _match_nhl_refs(nhl_games, current_matchup, current_refs):
                        matched += 1
                current_matchup = text
                current_refs = []
            elif current_matchup and '#' in text:
                # Official line: "Name #27" or "#27 Name"
                name = re.sub(r'#\d+', '', text).strip()
                name = re.sub(r'\s+', ' ', name)
                if name and len(name) > 2 and 'supervisor' not in name.lower():
                    current_refs.append(name)

        # Handle last block
        if current_matchup and current_refs:
            if _match_nhl_refs(nhl_games, current_matchup, current_refs):
                matched += 1

    print(f"[refs] NHL: matched officials for {matched}/{len(nhl_games)} games")
    return matched


def _match_nhl_refs(nhl_games, matchup_text, ref_names):
    """Match parsed NHL refs to games by team name."""
    matchup_n = normalize_name(matchup_text)
    officials_list = [
        {"name": name, "role": "referee" if i < 2 else "linesman"}
        for i, name in enumerate(ref_names)
    ]

    for g in nhl_games:
        if g.get("officials") and len(g["officials"]) > 0:
            continue

        g_home = normalize_name(
            g.get("home_team", {}).get("name", "") if isinstance(g.get("home_team"), dict)
            else g.get("home_team", "")
        )
        g_away = normalize_name(
            g.get("away_team", {}).get("name", "") if isinstance(g.get("away_team"), dict)
            else g.get("away_team", "")
        )

        # Check last 5+ chars of team names in matchup
        if g_home and g_away:
            home_tail = g_home[-6:] if len(g_home) > 6 else g_home
            away_tail = g_away[-6:] if len(g_away) > 6 else g_away
            if home_tail in matchup_n and away_tail in matchup_n:
                g["officials"] = officials_list
                return True
    return False


# ─────────────────────────────────────────────
#  NFL — footballzebras.com (HTML scrape)
# ─────────────────────────────────────────────
def fetch_nfl_officials(games):
    """Fetch NFL referee assignments from footballzebras.com."""
    nfl_games = [g for g in games if (g.get("sport") or "").lower() == "nfl"]
    if not nfl_games:
        return 0

    today = datetime.now(NY_TZ).date()
    year = today.year if today.month >= 8 else today.year - 1

    # Determine current NFL week (rough estimate)
    # NFL season starts first Thursday after Labor Day (first Monday in Sept)
    # Regular season is weeks 1-18, then playoffs
    # Try the category page to find the latest assignment post
    url = f"https://www.footballzebras.com/category/assignments/"
    html = get(url, as_json=False)
    if not html:
        print("[refs] NFL: could not fetch footballzebras.com assignments page")
        return 0

    # Find the most recent assignments post link
    post_links = re.findall(
        r'href="(https?://www\.footballzebras\.com/\d{4}/\d{2}/[^"]*(?:referee|official|assignment)[^"]*)"',
        html, re.IGNORECASE
    )

    if not post_links:
        print("[refs] NFL: no assignment post links found")
        return 0

    # Fetch the most recent post
    post_html = get(post_links[0], as_json=False)
    if not post_html:
        return 0

    # Parse: typically table or list with game matchups and referee names
    # Format varies but often: "Team at Team — Referee Name"
    matched = 0
    lines = re.sub(r'<[^>]+>', '\n', post_html).split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Look for patterns like "Bears at Packers: Shawn Hochuli" or
        # "Bears at Packers — Shawn Hochuli" or similar
        m = re.match(
            r'(.+?)\s+(?:at|@|vs\.?)\s+(.+?)[\s:—–-]+([A-Z][a-z]+\s+[A-Z][a-z]+.*?)$',
            line
        )
        if not m:
            continue

        away_text = normalize_name(m.group(1))
        home_text = normalize_name(m.group(2))
        ref_name = m.group(3).strip().rstrip('.')

        if not ref_name or len(ref_name) < 4:
            continue

        officials_list = [{"name": ref_name, "role": "crew chief"}]

        for g in nfl_games:
            if g.get("officials") and len(g["officials"]) > 0:
                continue

            g_home = normalize_name(
                g.get("home_team", {}).get("name", "") if isinstance(g.get("home_team"), dict)
                else g.get("home_team", "")
            )
            g_away = normalize_name(
                g.get("away_team", {}).get("name", "") if isinstance(g.get("away_team"), dict)
                else g.get("away_team", "")
            )

            if g_home and g_away:
                home_tail = g_home[-6:] if len(g_home) > 6 else g_home
                away_tail = g_away[-6:] if len(g_away) > 6 else g_away
                if (home_tail in home_text or home_text in g_home) and \
                   (away_tail in away_text or away_text in g_away):
                    g["officials"] = officials_list
                    matched += 1
                    break

    print(f"[refs] NFL: matched officials for {matched}/{len(nfl_games)} games")
    return matched


# ─────────────────────────────────────────────
#  ESPN officials re-check (retry for games near tipoff)
# ─────────────────────────────────────────────
def retry_espn_officials(games):
    """Re-try ESPN officials endpoint for games starting within 6 hours.
    ESPN sometimes populates officials closer to game time."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=6)
    checked = 0
    found = 0

    for g in games:
        if g.get("officials") and len(g["officials"]) > 0:
            continue

        dt_str = g.get("date_utc") or g.get("commence_time") or ""
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if dt < now or dt > cutoff:
            continue

        event_id = str(g.get("id") or g.get("event_id") or "")
        sport = (g.get("sport") or "").lower()
        if not event_id or not sport:
            continue

        # Map sport to ESPN path
        sport_paths = {
            "nfl": "football/leagues/nfl",
            "ncaaf": "football/leagues/college-football",
            "nba": "basketball/leagues/nba",
            "ncaab": "basketball/leagues/mens-college-basketball",
            "ncaaw": "basketball/leagues/womens-college-basketball",
            "mlb": "baseball/leagues/mlb",
            "nhl": "hockey/leagues/nhl",
        }
        path = sport_paths.get(sport)
        if not path:
            continue

        url = (f"https://sports.core.api.espn.com/v2/sports/{path}"
               f"/events/{event_id}/competitions/{event_id}/officials")
        data = get(url)
        checked += 1

        if not data or "items" not in data:
            continue

        officials_list = []
        for item in data["items"]:
            if "$ref" in item and isinstance(item["$ref"], str):
                ref_data = get(item["$ref"])
                if ref_data:
                    name = ref_data.get("displayName") or ref_data.get("fullName") or ""
                    role = ref_data.get("position", {}).get("displayName", "") if isinstance(ref_data.get("position"), dict) else ""
                    if name:
                        officials_list.append({"name": name, "role": role.lower()})
            elif "displayName" in item:
                officials_list.append({
                    "name": item["displayName"],
                    "role": (item.get("position", {}).get("displayName", "")
                             if isinstance(item.get("position"), dict) else "").lower()
                })

        if officials_list:
            g["officials"] = officials_list
            found += 1

    if checked:
        print(f"[refs] ESPN re-check: found officials for {found}/{checked} games starting within 6h")
    return found


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    if not os.path.exists(COMBINED_FILE):
        print(f"[refs] {COMBINED_FILE} not found, skipping")
        return

    with open(COMBINED_FILE) as f:
        combined = json.load(f)

    games = combined.get("data", [])
    if not games:
        print("[refs] No games in combined.json")
        return

    # Count games missing officials
    missing = sum(1 for g in games if not g.get("officials") or len(g.get("officials", [])) == 0)
    print(f"[refs] {missing}/{len(games)} games missing officials")

    if missing == 0:
        print("[refs] All games have officials, nothing to do")
        return

    total_matched = 0

    # Fetch from each source
    total_matched += fetch_mlb_officials(games)
    total_matched += fetch_nba_officials(games)
    total_matched += fetch_nhl_officials(games)
    total_matched += fetch_nfl_officials(games)

    # Re-try ESPN for games starting soon
    total_matched += retry_espn_officials(games)

    # Save updated combined.json
    if total_matched > 0:
        combined["data"] = games
        with open(COMBINED_FILE, "w") as f:
            json.dump(combined, f, indent=2)
        print(f"[refs] Updated {COMBINED_FILE} with {total_matched} new official assignments")
    else:
        print(f"[refs] No new officials found from external sources")

    # Final count
    still_missing = sum(1 for g in games if not g.get("officials") or len(g.get("officials", [])) == 0)
    print(f"[refs] After fetch: {still_missing}/{len(games)} games still missing officials")


if __name__ == "__main__":
    main()
