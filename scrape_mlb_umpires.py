#!/usr/bin/env python3
"""
scrape_mlb_umpires.py
Scrapes Covers.com for MLB umpire betting stats across multiple seasons.

For each home plate umpire, collects:
- Over/Under record and percentage
- Runs per game (scoring tendency)
- Strike percentage (zone tightness)
- Home runs per game

Output: mlb_ump_data.json
"""

import json, re, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTPUT = "mlb_ump_data.json"
BASE_URL = "https://www.covers.com/sport/baseball/mlb/statistics/umpires"
YEARS = list(range(2020, 2026))  # 6 seasons

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def safe_float(val):
    try:
        return float(str(val).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def parse_ou_record(record_str):
    """Parse '11-5' or '11-5-2' format into (over, under, push)."""
    parts = str(record_str).strip().split("-")
    try:
        over = int(parts[0])
        under = int(parts[1]) if len(parts) > 1 else 0
        push = int(parts[2]) if len(parts) > 2 else 0
        return over, under, push
    except (ValueError, IndexError):
        return 0, 0, 0


def fetch_ou_stats(year):
    """Fetch umpire over/under stats for a given year."""
    url = f"{BASE_URL}/overunder/{year}"
    print(f"  [fetch] O/U stats {year}: {url}")
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            print(f"    [warn] HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", id="MLB_RegularSeason")
        if not table:
            table = soup.find("table", class_="covers-CoversStats-table")
        if not table:
            print("    [warn] No table found")
            return []

        tbody = table.find("tbody")
        if not tbody:
            return []

        umpires = []
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            # Name is in the first cell, inside an <a> tag
            name_cell = cells[0]
            link = name_cell.find("a")
            name = link.get_text(strip=True) if link else name_cell.get_text(strip=True)
            # Clean up rank number prefix
            name = re.sub(r"^\d+\s*", "", name).strip()
            href = link.get("href", "") if link else ""

            ou_record = cells[1].get_text(strip=True)
            ou_pct = safe_float(cells[2].get_text(strip=True))
            runs_per_game = safe_float(cells[3].get_text(strip=True))
            strike_pct = safe_float(cells[4].get_text(strip=True))
            hr_per_game = safe_float(cells[5].get_text(strip=True))

            over, under, push = parse_ou_record(ou_record)
            total_games = over + under + push

            umpires.append({
                "name": name,
                "covers_id": href.split("/")[-1] if href else "",
                "games": total_games,
                "over": over,
                "under": under,
                "push": push,
                "over_pct": ou_pct,
                "runs_per_game": runs_per_game,
                "strike_pct": strike_pct,
                "hr_per_game": hr_per_game,
            })

        return umpires

    except Exception as e:
        print(f"    [error] {e}")
        return []


def main():
    all_umps = {}

    for year in YEARS:
        print(f"\n=== Season {year} ===")
        umps = fetch_ou_stats(year)
        print(f"  Found {len(umps)} umpires")
        time.sleep(1.5)  # respect rate limits

        for ump in umps:
            name = ump["name"]

            if name not in all_umps:
                all_umps[name] = {
                    "name": name,
                    "covers_id": ump["covers_id"],
                    "seasons": {},
                }

            all_umps[name]["seasons"][str(year)] = {
                "games": ump["games"],
                "over": ump["over"],
                "under": ump["under"],
                "push": ump["push"],
                "over_pct": ump["over_pct"],
                "runs_per_game": ump["runs_per_game"],
                "strike_pct": ump["strike_pct"],
                "hr_per_game": ump["hr_per_game"],
            }

    # Compute career aggregates
    for name, ump in all_umps.items():
        total_games = 0
        total_over = 0
        total_under = 0
        total_push = 0
        total_runs = 0
        total_hr = 0
        total_strike_pct_weighted = 0

        for yr, s in ump["seasons"].items():
            g = s.get("games") or 0
            total_games += g
            total_over += s.get("over") or 0
            total_under += s.get("under") or 0
            total_push += s.get("push") or 0
            if s.get("runs_per_game") and g > 0:
                total_runs += s["runs_per_game"] * g
            if s.get("hr_per_game") and g > 0:
                total_hr += s["hr_per_game"] * g
            if s.get("strike_pct") and g > 0:
                total_strike_pct_weighted += s["strike_pct"] * g

        ou_total = total_over + total_under
        ump["career"] = {
            "games": total_games,
            "over": total_over,
            "under": total_under,
            "push": total_push,
            "over_pct": round(total_over / ou_total * 100, 1) if ou_total else 50.0,
            "runs_per_game": round(total_runs / total_games, 2) if total_games else 0,
            "hr_per_game": round(total_hr / total_games, 2) if total_games else 0,
            "strike_pct": round(total_strike_pct_weighted / total_games, 1) if total_games else 0,
        }

        # Recent form (most recent 2 seasons)
        recent_years = sorted(ump["seasons"].keys(), reverse=True)[:2]
        recent_games = 0
        recent_over = 0
        recent_under = 0
        recent_runs = 0
        for yr in recent_years:
            s = ump["seasons"][yr]
            g = s.get("games") or 0
            recent_games += g
            recent_over += s.get("over") or 0
            recent_under += s.get("under") or 0
            if s.get("runs_per_game") and g > 0:
                recent_runs += s["runs_per_game"] * g

        recent_ou_total = recent_over + recent_under
        ump["recent"] = {
            "games": recent_games,
            "over_pct": round(recent_over / recent_ou_total * 100, 1) if recent_ou_total else 50.0,
            "runs_per_game": round(recent_runs / recent_games, 2) if recent_games else 0,
        }

    # Write output
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "covers.com",
        "years": YEARS,
        "umpire_count": len(all_umps),
        "umps": all_umps,
    }

    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[mlb_umpires] Wrote {OUTPUT}: {len(all_umps)} umpires across {len(YEARS)} seasons")


if __name__ == "__main__":
    main()
