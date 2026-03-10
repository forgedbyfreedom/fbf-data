#!/usr/bin/env python3
"""
scrape_ufc_odds.py
Scrapes BestFightOdds.com for upcoming UFC bout moneylines and round totals.

For each bout, collects:
- Fighter moneylines (consensus across sportsbooks)
- Over/Under 2.5 rounds line
- Number of sportsbooks with odds

Output: ufc_odds.json
This data is merged onto UFC bouts in combined.json by merge_ufc_odds.py.
"""

import json, re, time, unicodedata
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTPUT = "ufc_odds.json"
BASE_URL = "https://www.bestfightodds.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalize(name):
    """Normalize fighter name for matching (strips accents)."""
    s = unicodedata.normalize("NFD", (name or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s)


def extract_odds_from_row(odds_row):
    """Extract consensus moneyline from an odds table row."""
    cells = odds_row.find_all("td")
    all_odds = []
    for cell in cells:
        spans = cell.find_all("span")
        for s in spans:
            t = s.get_text(strip=True)
            if re.match(r"^[+-]\d+$", t):
                all_odds.append(int(t))
                break
    if all_odds:
        return round(sum(all_odds) / len(all_odds)), len(all_odds)
    return None, 0


def ml_to_implied_prob(ml):
    """Convert American moneyline to implied probability."""
    if ml is None:
        return None
    if ml > 0:
        return 100 / (ml + 100)
    else:
        return abs(ml) / (abs(ml) + 100)


def ml_to_decimal(ml):
    """Convert American moneyline to decimal odds."""
    if ml is None:
        return None
    if ml > 0:
        return round(ml / 100 + 1, 3)
    else:
        return round(100 / abs(ml) + 1, 3)


def fetch_upcoming_events():
    """Get list of upcoming UFC event URLs from BFO homepage."""
    print("[ufc_odds] Fetching upcoming events...")
    try:
        r = SESSION.get(BASE_URL, timeout=20)
        if r.status_code != 200:
            print(f"  [warn] HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)
        events = []
        seen = set()
        for a in links:
            href = a.get("href", "")
            if "/events/ufc" in href and href not in seen:
                seen.add(href)
                events.append({
                    "href": href,
                    "name": a.get_text(strip=True),
                })
        return events
    except Exception as e:
        print(f"  [error] {e}")
        return []


def fetch_event_bouts(event_path, event_name):
    """Scrape bouts and odds from a specific event page."""
    url = f"{BASE_URL}{event_path}"
    print(f"  [fetch] {event_name}: {url}")
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            print(f"    [warn] HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")
        if len(tables) < 2:
            print(f"    [warn] Expected 2 tables, found {len(tables)}")
            return []

        name_rows = tables[0].find_all("tr")
        odds_rows = tables[1].find_all("tr")

        if len(name_rows) != len(odds_rows):
            print(f"    [warn] Row mismatch: names={len(name_rows)} odds={len(odds_rows)}")
            return []

        # Pass 1: extract fighters and prop data
        fighters = []
        props = {}  # keyed by bout index
        bout_idx = -1

        for i in range(len(name_rows)):
            name_row = name_rows[i]
            odds_row = odds_rows[i]
            row_class = name_row.get("class") or []
            name_text = name_row.get_text(strip=True)
            if not name_text:
                continue

            is_prop = "pr" in row_class

            if is_prop:
                # Extract round over/under props
                if name_text.startswith("Over 2½") or name_text.startswith("Over 2.5"):
                    ml, _ = extract_odds_from_row(odds_row)
                    if ml is not None:
                        props.setdefault(bout_idx, {})["over_2_5"] = ml
                elif name_text.startswith("Under 2½") or name_text.startswith("Under 2.5"):
                    ml, _ = extract_odds_from_row(odds_row)
                    if ml is not None:
                        props.setdefault(bout_idx, {})["under_2_5"] = ml
                elif name_text.startswith("Over 1½") or name_text.startswith("Over 1.5"):
                    ml, _ = extract_odds_from_row(odds_row)
                    if ml is not None:
                        props.setdefault(bout_idx, {})["over_1_5"] = ml
                elif name_text.startswith("Under 1½") or name_text.startswith("Under 1.5"):
                    ml, _ = extract_odds_from_row(odds_row)
                    if ml is not None:
                        props.setdefault(bout_idx, {})["under_1_5"] = ml
                continue

            # Fighter row
            links = name_row.find_all("a")
            name = links[0].get_text(strip=True) if links else name_text
            ml, books = extract_odds_from_row(odds_row)

            fighters.append({"name": name, "ml": ml, "books": books})
            if len(fighters) % 2 == 1:
                bout_idx += 1

        # Pass 2: pair fighters into bouts
        bouts = []
        for i in range(0, len(fighters), 2):
            if i + 1 >= len(fighters):
                break
            f1 = fighters[i]
            f2 = fighters[i + 1]

            # Skip bouts with no odds from any book
            if f1["ml"] is None and f2["ml"] is None:
                continue

            bout = {
                "fighter1": f1["name"],
                "fighter1_ml": f1["ml"],
                "fighter1_prob": round(ml_to_implied_prob(f1["ml"]) * 100, 1) if f1["ml"] else None,
                "fighter1_decimal": ml_to_decimal(f1["ml"]),
                "fighter1_books": f1["books"],
                "fighter2": f2["name"],
                "fighter2_ml": f2["ml"],
                "fighter2_prob": round(ml_to_implied_prob(f2["ml"]) * 100, 1) if f2["ml"] else None,
                "fighter2_decimal": ml_to_decimal(f2["ml"]),
                "fighter2_books": f2["books"],
                "event": event_name,
            }

            b_idx = i // 2
            if b_idx in props:
                bout.update(props[b_idx])

            bouts.append(bout)

        return bouts

    except Exception as e:
        print(f"    [error] {e}")
        return []


def main():
    events = fetch_upcoming_events()
    print(f"[ufc_odds] Found {len(events)} upcoming UFC events")

    all_bouts = []
    for ev in events:
        bouts = fetch_event_bouts(ev["href"], ev["name"])
        print(f"    {len(bouts)} bouts with odds")
        all_bouts.extend(bouts)
        time.sleep(1.5)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bestfightodds.com",
        "event_count": len(events),
        "bout_count": len(all_bouts),
        "bouts": all_bouts,
    }

    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[ufc_odds] Wrote {OUTPUT}: {len(all_bouts)} bouts across {len(events)} events")


if __name__ == "__main__":
    main()
