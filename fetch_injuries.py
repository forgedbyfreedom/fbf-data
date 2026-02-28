#!/usr/bin/env python3
"""
fetch_injuries.py
Fetches injury data from ESPN public injury pages.
Fallback: Oddstrader scraper.
Output: injuries.json in standardized format.
"""

import json, re, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTFILE = "injuries.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ESPN public injury page URLs
ESPN_SPORT_URLS = {
    "nfl": "https://www.espn.com/nfl/injuries",
    "nba": "https://www.espn.com/nba/injuries",
    "nhl": "https://www.espn.com/nhl/injuries",
    "mlb": "https://www.espn.com/mlb/injuries",
    "ncaaf": "https://www.espn.com/college-football/injuries",
    "ncaab": "https://www.espn.com/mens-college-basketball/injuries",
    "ncaaw": "https://www.espn.com/womens-college-basketball/injuries",
}

# Oddstrader fallback URLs (no NCAAW or UFC available)
ODDSTRADER_SPORT_URLS = {
    "nfl": "https://www.oddstrader.com/nfl/injuries/",
    "nba": "https://www.oddstrader.com/nba/injuries/",
    "ncaaf": "https://www.oddstrader.com/ncaa-college-football/injuries/",
    "ncaab": "https://www.oddstrader.com/ncaa-college-basketball/injuries/",
    "nhl": "https://www.oddstrader.com/nhl/injuries/",
    "mlb": "https://www.oddstrader.com/mlb/injuries/",
}


def normalize_team(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def fetch_espn_injuries_for_sport(sport, url):
    """Scrape ESPN public injury page for a sport."""
    rows = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  [ESPN] {sport}: HTTP {resp.status_code}")
            return rows

        soup = BeautifulSoup(resp.text, "html.parser")

        # ESPN injury pages use various table structures
        # Look for team sections and injury tables
        current_team = None

        # Try finding team headers and injury rows
        # ESPN uses <div class="Table__Title"> or similar for team names
        # and <tr> rows for individual injuries

        # Strategy 1: Look for structured table data
        tables = soup.find_all("table")
        for table in tables:
            # Check for team name in preceding elements
            prev = table.find_previous(["h2", "h3", "div", "span"])
            if prev:
                team_text = prev.get_text(strip=True)
                # Filter out non-team text
                if team_text and len(team_text) > 2 and len(team_text) < 60:
                    if not any(skip in team_text.lower() for skip in ["injury", "report", "status", "player", "date"]):
                        current_team = team_text

            if not current_team:
                continue

            trs = table.find_all("tr")
            for tr in trs:
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue

                # Try to extract player name, position, status, injury
                texts = [td.get_text(strip=True) for td in tds]
                if not texts[0] or texts[0].lower() in ("name", "player", ""):
                    continue

                player = texts[0] if len(texts) > 0 else ""
                position = ""
                status = ""
                injury_desc = ""

                # Different ESPN layouts have different column orders
                if len(texts) >= 4:
                    position = texts[1]
                    status = texts[2] if texts[2] else texts[3]
                    injury_desc = texts[3] if len(texts) > 3 else ""
                elif len(texts) >= 3:
                    status = texts[1]
                    injury_desc = texts[2]
                elif len(texts) >= 2:
                    status = texts[1]

                if player and current_team:
                    rows.append({
                        "sport": sport,
                        "team": current_team,
                        "team_norm": normalize_team(current_team),
                        "player": player,
                        "position": position,
                        "status": status,
                        "injury": injury_desc,
                    })

        # Strategy 2: Look for Responsive Table wrappers (newer ESPN layout)
        if not rows:
            wrappers = soup.find_all("div", class_=re.compile(r"ResponsiveTable|injuries"))
            for wrapper in wrappers:
                # Team name
                title = wrapper.find(class_=re.compile(r"Table__Title|TeamHeader"))
                if title:
                    current_team = title.get_text(strip=True)

                # Also check for team links with logos
                team_link = wrapper.find("a", class_=re.compile(r"AnchorLink|TeamLink"))
                if team_link and not current_team:
                    current_team = team_link.get_text(strip=True)

                if not current_team:
                    continue

                trs = wrapper.find_all("tr")
                for tr in trs:
                    tds = tr.find_all("td")
                    if len(tds) < 2:
                        continue
                    texts = [td.get_text(strip=True) for td in tds]
                    if not texts[0] or texts[0].lower() in ("name", "player", ""):
                        continue

                    rows.append({
                        "sport": sport,
                        "team": current_team,
                        "team_norm": normalize_team(current_team),
                        "player": texts[0],
                        "position": texts[1] if len(texts) > 1 else "",
                        "status": texts[2] if len(texts) > 2 else "",
                        "injury": texts[3] if len(texts) > 3 else "",
                    })

        # Strategy 3: JSON-LD or embedded data
        if not rows:
            scripts = soup.find_all("script", type="application/json")
            for script in scripts:
                try:
                    data = json.loads(script.string or "")
                    # Walk through looking for injury-like structures
                    if isinstance(data, dict):
                        for key in ("injuries", "injuryData", "page"):
                            if key in data:
                                # Found embedded data
                                pass
                except Exception:
                    pass

    except requests.exceptions.RequestException as e:
        print(f"  [ESPN] {sport}: Request failed: {e}")
    except Exception as e:
        print(f"  [ESPN] {sport}: Parse error: {e}")

    return rows


def fetch_oddstrader_injuries_for_sport(sport, url):
    """Fallback: scrape Oddstrader injury pages."""
    rows = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return rows

        soup = BeautifulSoup(resp.text, "html.parser")
        current_team = None

        for el in soup.find_all(["a", "h2", "h3", "div", "span"]):
            text = el.get_text(strip=True)
            if not text:
                continue

            # Team headers like "#10 Alabama Crimson Tide"
            if text.startswith("#") and " " in text and "DATE" not in text:
                current_team = text.split(" ", 1)[1]
                continue

            # Also detect plain team names (no ranking)
            if el.name in ("h2", "h3") and len(text) > 3 and len(text) < 50:
                if not any(skip in text.lower() for skip in ["injury", "report", "date", "est"]):
                    current_team = text
                    continue

            # Injury lines: "Player (POS) Status Injury Info"
            if current_team and "(" in text and ")" in text and any(
                st in text for st in ["Out", "Questionable", "Probable", "Doubtful", "OFS", "Day-To-Day", "IR"]
            ):
                try:
                    player_part, rest = text.split(")", 1)
                    player_name = player_part.split("(")[0].strip()
                    position = player_part.split("(")[1].strip()
                    parts = rest.split()
                    status = parts[0] if parts else ""
                    injury_info = " ".join(parts[1:]) if len(parts) > 1 else ""
                except Exception:
                    player_name = text
                    position = ""
                    status = ""
                    injury_info = ""

                rows.append({
                    "sport": sport,
                    "team": current_team,
                    "team_norm": normalize_team(current_team),
                    "player": player_name,
                    "position": position,
                    "status": status,
                    "injury": injury_info,
                })
    except Exception as e:
        print(f"  [Oddstrader] {sport}: Error: {e}")

    return rows


def main():
    all_injuries = []
    source = "espn_web"

    # Try ESPN first
    print("[injuries] Trying ESPN public injury pages...")
    for sport, url in ESPN_SPORT_URLS.items():
        rows = fetch_espn_injuries_for_sport(sport, url)
        print(f"  [ESPN] {sport}: {len(rows)} injuries")
        all_injuries.extend(rows)
        time.sleep(1.0)

    # If ESPN yielded nothing, try Oddstrader
    if len(all_injuries) == 0:
        print("[injuries] ESPN returned 0 injuries, trying Oddstrader fallback...")
        source = "oddstrader"
        for sport, url in ODDSTRADER_SPORT_URLS.items():
            try:
                rows = fetch_oddstrader_injuries_for_sport(sport, url)
                print(f"  [Oddstrader] {sport}: {len(rows)} injuries")
                all_injuries.extend(rows)
                time.sleep(1.5)
            except Exception as e:
                print(f"  [Oddstrader] {sport}: FAILED: {e}")

    # Deduplicate by (sport, team_norm, player)
    seen = set()
    deduped = []
    for row in all_injuries:
        key = (row.get("sport"), row.get("team_norm"), normalize_team(row.get("player", "")))
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    # Validate: skip entries without team
    deduped = [r for r in deduped if r.get("team")]

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "count": len(deduped),
        "injuries": deduped,
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    # Summary by sport
    sport_counts = {}
    for r in deduped:
        s = r.get("sport", "unknown")
        sport_counts[s] = sport_counts.get(s, 0) + 1

    print(f"[injuries] Wrote {OUTFILE}: {len(deduped)} total injuries from {source}")
    for s, c in sorted(sport_counts.items()):
        print(f"  {s}: {c}")

    if len(deduped) == 0:
        print("[injuries] WARNING: 0 injuries found from all sources")


if __name__ == "__main__":
    main()
