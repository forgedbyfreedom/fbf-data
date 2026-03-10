#!/usr/bin/env python3
"""
scrape_nfl_penalties.py
Scrapes NFLPenalties.com for per-referee penalty stats across multiple seasons.

For each referee crew chief, collects:
- Total games, penalties, yards, flags per season
- Per-game rates
- Home vs away penalty split (indicator of home bias)
- Key penalty type breakdown (PI, holding, roughing)

Output: nfl_ref_penalties.json
"""

import json, re, time, os
from datetime import datetime, timezone
from html.parser import HTMLParser
import requests

OUTPUT = "nfl_ref_penalties.json"
BASE_URL = "https://www.nflpenalties.com"
YEARS = list(range(2020, 2025))  # 5 seasons

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Key penalty types that impact game outcomes
KEY_PENALTIES = [
    "pass interference",
    "defensive pass interference",
    "offensive pass interference",
    "offensive holding",
    "defensive holding",
    "roughing the passer",
    "roughing the kicker",
    "unnecessary roughness",
    "illegal use of hands",
    "unsportsmanlike conduct",
    "face mask",
    "illegal contact",
    "neutral zone infraction",
    "encroachment",
    "false start",
    "illegal formation",
    "taunting",
]


class TableParser(HTMLParser):
    """Simple HTML table parser that extracts rows from <table class='footable'>."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_td = False
        self.in_th = False
        self.in_a = False
        self.current_row = []
        self.current_cell = ""
        self.current_href = ""
        self.rows = []
        self.headers = []
        self.header_row = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table" and "footable" in attrs_dict.get("class", ""):
            self.in_table = True
            self.depth = 0
        if not self.in_table:
            return
        if tag == "tbody":
            self.in_tbody = True
        if tag == "td":
            self.in_td = True
            self.current_cell = ""
            self.current_href = ""
        if tag == "th" and "headers" in attrs_dict.get("class", ""):
            self.in_th = True
            self.current_cell = ""
        if tag == "a" and self.in_td:
            self.in_a = True
            self.current_href = attrs_dict.get("href", "")
        if tag == "tr" and self.in_tbody:
            self.current_row = []

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag == "td":
            self.in_td = False
            self.current_row.append((self.current_cell.strip(), self.current_href))
        if tag == "th":
            if self.in_th:
                self.header_row.append(self.current_cell.strip())
            self.in_th = False
        if tag == "tr":
            if self.in_tbody and self.current_row:
                self.rows.append(self.current_row)
            if self.header_row and not self.headers:
                self.headers = list(self.header_row)
            self.header_row = []
        if tag == "a":
            self.in_a = False
        if tag == "tbody":
            self.in_tbody = False
        if tag == "table":
            self.in_table = False

    def handle_data(self, data):
        if self.in_td or self.in_a:
            self.current_cell += data
        if self.in_th:
            self.current_cell += data


def parse_table(html):
    """Parse HTML and return list of row dicts."""
    parser = TableParser()
    parser.feed(html)
    return parser.rows, parser.headers


def safe_float(val):
    try:
        return float(val.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def safe_int(val):
    try:
        return int(val.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_all_refs(year):
    """Fetch the all-referees summary page for a given year."""
    url = f"{BASE_URL}/all-referees.php?year={year}&view=total"
    print(f"  [fetch] All refs {year}: {url}")
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            print(f"    [warn] HTTP {r.status_code}")
            return []
        rows, headers = parse_table(r.text)
        refs = []
        for row in rows:
            if len(row) < 8:
                continue
            name_text, href = row[0]
            refs.append({
                "name": name_text.strip(),
                "slug": href.split("?")[0].replace("/referee/", "") if "/referee/" in href else "",
                "games": safe_int(row[1][0]),
                "total_count": safe_int(row[2][0]),
                "total_yards": safe_int(row[3][0]),
                "total_dismissed": safe_int(row[4][0]),
                "total_flags": safe_int(row[5][0]),
                "total_home": safe_int(row[6][0]),
                "total_away": safe_int(row[7][0]),
                "per_game_count": safe_float(row[8][0]) if len(row) > 8 else None,
                "per_game_yards": safe_float(row[9][0]) if len(row) > 9 else None,
            })
        return refs
    except Exception as e:
        print(f"    [error] {e}")
        return []


def fetch_ref_penalties(slug, year):
    """Fetch penalty type breakdown for a specific referee in a given year."""
    if not slug:
        return []
    url = f"{BASE_URL}/referee/{slug}?year={year}&view=penalty"
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            return []
        rows, headers = parse_table(r.text)
        penalties = []
        for row in rows:
            if len(row) < 6:
                continue
            pen_name = row[0][0].strip().lower()
            penalties.append({
                "penalty": pen_name,
                "count": safe_int(row[1][0]),
                "yards": safe_int(row[2][0]),
                "home": safe_int(row[3][0]),
                "away": safe_int(row[4][0]),
            })
        return penalties
    except Exception:
        return []


def main():
    all_refs = {}

    for year in YEARS:
        print(f"\n=== Season {year} ===")
        refs = fetch_all_refs(year)
        print(f"  Found {len(refs)} referees")
        time.sleep(1.0)

        for ref in refs:
            name = ref["name"]
            slug = ref["slug"]

            if name not in all_refs:
                all_refs[name] = {
                    "name": name,
                    "slug": slug,
                    "seasons": {},
                    "career_games": 0,
                    "career_penalties_per_game": 0,
                    "career_yards_per_game": 0,
                    "home_away_ratio": 1.0,
                    "key_penalties": {},
                }

            # Fetch penalty type breakdown for key refs
            penalties = []
            if ref["games"] and ref["games"] >= 10:
                print(f"    Fetching penalty types for {name} ({year})...")
                penalties = fetch_ref_penalties(slug, year)
                time.sleep(0.8)  # be nice to the server

            season_data = {
                "games": ref["games"],
                "total_count": ref["total_count"],
                "total_yards": ref["total_yards"],
                "total_flags": ref["total_flags"],
                "total_home": ref["total_home"],
                "total_away": ref["total_away"],
                "per_game_count": ref["per_game_count"],
                "per_game_yards": ref["per_game_yards"],
            }

            # Add key penalty breakdowns
            if penalties:
                key_pens = {}
                for p in penalties:
                    pen_name = p["penalty"]
                    if any(kp in pen_name for kp in KEY_PENALTIES):
                        key_pens[pen_name] = {
                            "count": p["count"],
                            "home": p["home"],
                            "away": p["away"],
                        }
                season_data["key_penalties"] = key_pens

            all_refs[name]["seasons"][str(year)] = season_data

    # Compute career aggregates
    for name, ref in all_refs.items():
        total_games = 0
        total_count = 0
        total_yards = 0
        total_home = 0
        total_away = 0
        agg_key_pens = {}

        for yr, s in ref["seasons"].items():
            g = s.get("games") or 0
            total_games += g
            total_count += s.get("total_count") or 0
            total_yards += s.get("total_yards") or 0
            total_home += s.get("total_home") or 0
            total_away += s.get("total_away") or 0

            for pen_name, pen_data in s.get("key_penalties", {}).items():
                if pen_name not in agg_key_pens:
                    agg_key_pens[pen_name] = {"count": 0, "home": 0, "away": 0}
                agg_key_pens[pen_name]["count"] += pen_data.get("count", 0)
                agg_key_pens[pen_name]["home"] += pen_data.get("home", 0)
                agg_key_pens[pen_name]["away"] += pen_data.get("away", 0)

        ref["career_games"] = total_games
        ref["career_penalties_per_game"] = round(total_count / total_games, 2) if total_games else 0
        ref["career_yards_per_game"] = round(total_yards / total_games, 2) if total_games else 0
        ref["home_away_ratio"] = round(total_home / total_away, 3) if total_away else 1.0
        ref["key_penalties"] = agg_key_pens

    # Write output
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "nflpenalties.com",
        "years": YEARS,
        "referee_count": len(all_refs),
        "refs": all_refs,
    }

    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[nfl_penalties] Wrote {OUTPUT}: {len(all_refs)} referees across {len(YEARS)} seasons")


if __name__ == "__main__":
    main()
