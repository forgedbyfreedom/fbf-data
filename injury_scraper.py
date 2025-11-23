#!/usr/bin/env python3
"""
injury_scraper.py

ESPN Core API no longer exposes injuries (404), so we scrape public ESPN injury pages.

Outputs:
  injuries.json

Shape:
{
  "timestamp": "YYYYMMDD_HHMM",
  "source": "ESPN_WEB",
  "leagues": {
     "nfl": [ {team, player, position, status, description, updated, league} ],
     "nba": [ ... ],
     ...
  }
}

Requirements:
  pip install requests beautifulsoup4 lxml
"""

import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

TIMEOUT = 15
OUTPUT = "injuries.json"

# ESPN public injury pages (still live)
LEAGUE_PAGES = {
    "nfl":  "https://www.espn.com/nfl/injuries",
    "nba":  "https://www.espn.com/nba/injuries",
    "nhl":  "https://www.espn.com/nhl/injuries",
    "mlb":  "https://www.espn.com/mlb/injuries",
    # College pages exist but often lag; keep optional:
    "ncaaf": "https://www.espn.com/college-football/injuries",
    "ncaab": "https://www.espn.com/mens-college-basketball/injuries",
    "ncaaw": "https://www.espn.com/womens-college-basketball/injuries",
}

HEADERS = {
    "User-Agent": "fbf-data-bot/1.0 (+https://forgedbyfreedom.org)"
}

def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def clean_text(x):
    return re.sub(r"\s+", " ", (x or "").strip())

def parse_injury_page(league_key, html):
    """
    ESPN injuries page structure changes sometimes.
    Strategy:
      - Find all tables.
      - Detect team headers (h2/h3) preceding each table.
      - Parse rows by column labels where possible, else by position.
    """
    soup = BeautifulSoup(html, "lxml")
    injuries = []

    # ESPN uses a repeating pattern of team-name headers + tables
    # We walk through the DOM in order and track current team.
    current_team = None

    # All relevant blocks are usually in <section> or <article>
    body = soup.body or soup
    nodes = body.find_all(["h1", "h2", "h3", "table"], recursive=True)

    for node in nodes:
        if node.name in ("h2", "h3"):
            txt = clean_text(node.get_text())
            # Team headers are usually plain like "Chicago Bears"
            if txt and len(txt) < 50 and "injuries" not in txt.lower():
                current_team = txt

        if node.name == "table":
            # Parse header columns
            headers = [clean_text(th.get_text()).lower() for th in node.find_all("th")]
            rows = node.find_all("tr")

            for tr in rows[1:]:
                cols = [clean_text(td.get_text()) for td in tr.find_all("td")]
                if not cols or len(cols) < 2:
                    continue

                # Best-effort mapping depending on page
                rec = {
                    "league": league_key,
                    "team": current_team or "Unknown",
                    "player": None,
                    "position": None,
                    "status": None,
                    "description": None,
                    "updated": None,
                }

                if headers:
                    # Common ESPN columns:
                    # Player | POS | Status | Date | Injury / Comment
                    for i, h in enumerate(headers):
                        if i >= len(cols):
                            continue
                        v = cols[i]
                        if "player" in h:
                            rec["player"] = v
                        elif h in ("pos", "position"):
                            rec["position"] = v
                        elif "status" in h:
                            rec["status"] = v
                        elif "date" in h or "updated" in h:
                            rec["updated"] = v
                        elif "injury" in h or "comment" in h or "description" in h:
                            rec["description"] = v

                else:
                    # Fallback: assume common order
                    # [player, pos, status, date, description]
                    rec["player"] = cols[0]
                    if len(cols) > 1:
                        rec["position"] = cols[1]
                    if len(cols) > 2:
                        rec["status"] = cols[2]
                    if len(cols) > 3:
                        rec["updated"] = cols[3]
                    if len(cols) > 4:
                        rec["description"] = cols[4]

                if rec["player"]:
                    injuries.append(rec)

    # If ESPN changed structure so headers didn't capture,
    # try a backup scan for team blocks.
    if not injuries:
        for team_block in soup.select("section, article, div"):
            team_name = None
            h = team_block.find(["h2", "h3"])
            if h:
                htxt = clean_text(h.get_text())
                if htxt and len(htxt) < 50:
                    team_name = htxt

            tables = team_block.find_all("table")
            for t in tables:
                headers = [clean_text(th.get_text()).lower() for th in t.find_all("th")]
                rows = t.find_all("tr")
                for tr in rows[1:]:
                    cols = [clean_text(td.get_text()) for td in tr.find_all("td")]
                    if not cols or len(cols) < 2:
                        continue
                    rec = {
                        "league": league_key,
                        "team": team_name or "Unknown",
                        "player": cols[0],
                        "position": cols[1] if len(cols) > 1 else None,
                        "status": cols[2] if len(cols) > 2 else None,
                        "updated": cols[3] if len(cols) > 3 else None,
                        "description": cols[4] if len(cols) > 4 else None,
                    }
                    if rec["player"]:
                        injuries.append(rec)

    return injuries

def main():
    leagues_out = {}
    for league_key, url in LEAGUE_PAGES.items():
        try:
            print(f"[⏱️] Scraping {league_key.upper()} injuries...")
            html = get_html(url)
            injuries = parse_injury_page(league_key, html)
            leagues_out[league_key] = injuries
            print(f"[✅] {league_key.upper()} injuries: {len(injuries)} records")
            time.sleep(0.7)  # polite delay
        except Exception as e:
            print(f"[⚠️] Failed {league_key}: {e}")
            leagues_out[league_key] = []

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "source": "ESPN_WEB",
        "leagues": leagues_out,
        "notes": "ESPN Core API removed injuries endpoints in 2024–2025; scraped from public ESPN injuries pages."
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    total = sum(len(v) for v in leagues_out.values())
    print(f"[🏁] Wrote {OUTPUT} with {total} injuries total.")

if __name__ == "__main__":
    main()
