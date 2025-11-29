#!/usr/bin/env python3
import json
import time
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

ODDSTRADER_SPORT_URLS = {
    "nfl": "https://www.oddstrader.com/nfl/injuries/",
    "ncaaf": "https://www.oddstrader.com/ncaa-college-football/injuries/",
    "nhl": "https://www.oddstrader.com/nhl/injuries/",
    "mlb": "https://www.oddstrader.com/mlb/injuries/",
    "ncaab": "https://www.oddstrader.com/ncaa-college-basketball/injuries/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ForgedByFreedomBot/1.0)"
}

def normalize_team(name: str) -> str:
    return (
        name.lower()
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace(",", "")
        .replace("'", "")
        .replace("  ", " ")
        .strip()
    )

def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def parse_injuries_for_sport(sport: str, url: str) -> List[Dict]:
    """
    Returns a list of rows like:
    {
      "sport": "ncaaf",
      "team": "Alabama Crimson Tide",
      "player": "CJ Allen",
      "position": "LB",
      "status": "Out",
      "injury": "Undisclosed",
      "est_return": "Dec 13, 2025",
      "raw": "CJ Allen (LB) Out Not Specified Undisclosed Dec 13, 2025"
    }
    """
    soup = fetch_page(url)
    rows = []

    # The page groups by team headers (#10 Alabama Crimson Tide) followed by rows
    current_team = None

    # This is intentionally loose: we walk the page and watch for headings
    # and “row” links that contain player info.
    for el in soup.find_all(["a", "h2", "h3", "div", "span"]):
        text = el.get_text(strip=True)
        if not text:
            continue

        # Team headers look like "#10 Alabama Crimson Tide" or "Alabama Crimson Tide"
        if "Crimson Tide" in text or "State" in text or "Tigers" in text or "Bulldogs" in text:
            # Heuristic: treat any line that starts with "#" or has a ranked team-style phrase as a header
            if "DATE" in text or "EST. RETURN" in text:
                continue
            if "(" in text and ")" not in text:
                # skip weird fragments
                pass

        # Stronger heuristic: “#10 Alabama Crimson Tide”
        if text.startswith("#") and " " in text and "DATE" not in text:
            # This is likely a team heading
            # Strip ranking (“#10 ”)
            team_name = text.split(" ", 1)[1]
            current_team = team_name
            continue

        # Injury lines look like:
        # "CJ Allen (LB) Out Not Specified Undisclosed Dec 13, 2025"
        if current_team and "(" in text and ")" in text and any(
            status in text for status in ["Out", "Questionable", "Probable", "OFS"]
        ):
            raw = text
            try:
                player_part, rest = raw.split(")", 1)
                player_name = player_part.split("(")[0].strip()
                position = player_part.split("(")[1].strip()

                parts = rest.split()
                # Very rough: status is first token of rest
                status = parts[0]

                # Try to find last 3 tokens as date
                if len(parts) >= 3:
                    est_return = " ".join(parts[-3:])
                else:
                    est_return = ""

                # Whatever is between status and date we treat as "injury info"
                injury_info = " ".join(parts[1:-3]) if len(parts) > 4 else ""

            except Exception:
                player_name = raw
                position = ""
                status = ""
                injury_info = ""
                est_return = ""

            rows.append(
                {
                    "sport": sport,
                    "team": current_team,
                    "team_norm": normalize_team(current_team),
                    "player": player_name,
                    "position": position,
                    "status": status,
                    "injury": injury_info,
                    "est_return": est_return,
                    "raw": raw,
                }
            )

    return rows

def main():
    all_rows = []
    for sport, url in ODDSTRADER_SPORT_URLS.items():
        try:
            sport_rows = parse_injuries_for_sport(sport, url)
            print(f"[injuries] {sport}: scraped {len(sport_rows)} rows from Oddstrader")
            all_rows.extend(sport_rows)
            time.sleep(1.5)  # be polite
        except Exception as e:
            print(f"[injuries] ERROR scraping {sport} from {url}: {e}")

    payload = {
        "source": "oddstrader",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(all_rows),
        "injuries": all_rows,
    }

    with open("injuries.json", "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[injuries] wrote injuries.json with {len(all_rows)} total injuries")

if __name__ == "__main__":
    main()
