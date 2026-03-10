#!/usr/bin/env python3
"""
scrape_public_betting.py
Scrapes public betting consensus percentages from Covers.com.

For each game, captures:
- Team 1 vs Team 2
- Public bet % on each side (spread consensus)
- Number of picks on each side
- Spread line

The "fade the public" signal: when 70%+ of public is on one side
but the line hasn't moved, sharp money is likely on the other side.

Output: public_betting.json

Run AFTER: fetch_espn_all.py
Run BEFORE: merge_features.py
"""

import json, re, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTPUT = "public_betting.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Covers.com sport slugs
SPORTS = {
    "nba": "nba",
    "nhl": "nhl",
    "mlb": "mlb",
    "ncaab": "ncaab",
    "ncaaf": "ncaaf",
    "nfl": "nfl",
}

# Covers team abbreviation → ESPN abbreviation mapping (common mismatches)
ABBR_MAP = {
    # NBA
    "bk": "BKN", "bkn": "BKN", "gs": "GSW", "gsw": "GSW", "no": "NOP", "nop": "NOP",
    "ny": "NYK", "nyk": "NYK", "sa": "SAS", "sas": "SAS", "uta": "UTA", "utah": "UTA",
    "okc": "OKC", "por": "POR", "lac": "LAC", "lal": "LAL", "min": "MIN", "mem": "MEM",
    "det": "DET", "chi": "CHI", "cle": "CLE", "bos": "BOS", "phi": "PHI", "mil": "MIL",
    "atl": "ATL", "mia": "MIA", "was": "WSH", "wsh": "WSH", "ind": "IND", "cha": "CHA",
    "orl": "ORL", "tor": "TOR", "den": "DEN", "phx": "PHX", "sac": "SAC", "dal": "DAL",
    "hou": "HOU",
    # NHL
    "van": "VAN", "wpg": "WPG", "edm": "EDM", "cgy": "CGY", "sea": "SEA",
    "vgs": "VGK", "vgk": "VGK", "col": "COL", "ari": "ARI", "ana": "ANA",
    "nsh": "NSH", "stl": "STL", "cbj": "CBJ", "car": "CAR", "fla": "FLA",
    "tb": "TBL", "tbl": "TBL", "pit": "PIT", "nj": "NJD", "njd": "NJD",
    "nyi": "NYI", "nyr": "NYR", "buf": "BUF", "ott": "OTT", "mtl": "MTL",
    # NFL
    "kc": "KC", "gb": "GB", "ne": "NE", "sf": "SF", "tb": "TB", "bal": "BAL",
    "cin": "CIN", "jax": "JAX", "ten": "TEN", "lar": "LAR", "lv": "LV",
    # MLB
    "chc": "CHC", "chw": "CWS", "cws": "CWS", "sd": "SD", "sdp": "SD",
    "tex": "TEX", "ari": "ARI", "az": "ARI",
}


def normalize_abbr(abbr):
    """Normalize a Covers abbreviation to ESPN format."""
    a = (abbr or "").lower().strip()
    return ABBR_MAP.get(a, abbr.upper().strip())


def scrape_sport(sport_key):
    """Scrape consensus picks for a sport from Covers.com."""
    covers_slug = SPORTS.get(sport_key, sport_key)
    url = f"https://contests.covers.com/consensus/topconsensus/{covers_slug}/overall"

    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            print(f"  [warn] HTTP {r.status_code} for {sport_key}")
            return []
    except Exception as e:
        print(f"  [error] {sport_key}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    games = []

    # Each game is a <tr> containing team blocks and consensus data
    rows = soup.find_all("tr")
    for row in rows:
        # Find team blocks
        team1_el = row.find(class_="covers-CoversConsensus-table--teamBlock")
        team2_el = row.find(class_="covers-CoversConsensus-table--teamBlock2")
        if not team1_el or not team2_el:
            continue

        # Extract team names/abbreviations
        team1_link = team1_el.find("a")
        team2_link = team2_el.find("a")
        team1_abbr = team1_link.get_text(strip=True) if team1_link else ""
        team2_abbr = team2_link.get_text(strip=True) if team2_link else ""
        team1_title = team1_link.get("title", "") if team1_link else ""
        team2_title = team2_link.get("title", "") if team2_link else ""

        # Extract consensus percentages
        pct_spans = row.find_all(class_=re.compile("consensusTable--(high|low)"))
        if len(pct_spans) < 2:
            continue

        pct1_text = pct_spans[0].get_text(strip=True).replace("%", "")
        pct2_text = pct_spans[1].get_text(strip=True).replace("%", "")

        try:
            pct1 = int(pct1_text)
            pct2 = int(pct2_text)
        except ValueError:
            continue

        # Extract spread line and pick counts from remaining <td>s
        tds = row.find_all("td")
        spread_text = ""
        picks = []
        for td in tds:
            text = td.get_text(strip=True)
            # Look for spread pattern (e.g., "+13-13" or "+3.5-3.5")
            if re.match(r"^[+-]?\d", text) and not re.match(r"^\d{2,3}%", text):
                # Could be spread or pick count
                nums = re.findall(r"[+-]?\d+\.?\d*", text)
                if len(nums) == 2:
                    try:
                        n1 = float(nums[0])
                        n2 = float(nums[1])
                        if abs(n1) == abs(n2) and abs(n1) < 50:
                            spread_text = nums[0]
                        elif n1 > 50 or n2 > 50:
                            picks = [int(float(nums[0])), int(float(nums[1]))]
                    except ValueError:
                        pass

        # Determine which team the public favors
        public_side = "team1" if pct1 > pct2 else "team2"
        public_pct = max(pct1, pct2)

        # Fade signal: strong public lean (70%+) suggests contrarian value
        fade_signal = 0
        if public_pct >= 80:
            fade_signal = 3  # very strong fade signal
        elif public_pct >= 70:
            fade_signal = 2  # strong fade
        elif public_pct >= 65:
            fade_signal = 1  # mild fade

        game_data = {
            "sport": sport_key,
            "team1_abbr": normalize_abbr(team1_abbr),
            "team2_abbr": normalize_abbr(team2_abbr),
            "team1_name": team1_title,
            "team2_name": team2_title,
            "team1_pct": pct1,
            "team2_pct": pct2,
            "public_side": normalize_abbr(team1_abbr) if public_side == "team1" else normalize_abbr(team2_abbr),
            "public_pct": public_pct,
            "fade_signal": fade_signal,
            "picks_team1": picks[0] if picks else None,
            "picks_team2": picks[1] if picks else None,
        }
        if spread_text:
            game_data["spread"] = spread_text

        games.append(game_data)

    return games


def main():
    all_games = []

    for sport_key in SPORTS:
        print(f"  [fetch] {sport_key} consensus...")
        games = scrape_sport(sport_key)
        all_games.extend(games)
        print(f"    {len(games)} games with consensus data")
        time.sleep(1.0)  # polite delay

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "covers.com",
        "game_count": len(all_games),
        "games": all_games,
    }

    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    # Stats
    strong_fades = sum(1 for g in all_games if g["fade_signal"] >= 2)
    print(f"\n[public_betting] {len(all_games)} games, {strong_fades} strong fade signals (70%+)")


if __name__ == "__main__":
    main()
