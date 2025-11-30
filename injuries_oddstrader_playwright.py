#!/usr/bin/env python3

import json
import asyncio
from playwright.async_api import async_playwright

SPORT_URLS = {
    "nfl": "https://www.oddstrader.com/nfl/injuries/",
    "ncaaf": "https://www.oddstrader.com/ncaa-college-football/injuries/",
    "nba": "https://www.oddstrader.com/nba/injuries/",
    "ncaab": "https://www.oddstrader.com/ncaa-college-basketball/injuries/",
    "nhl": "https://www.oddstrader.com/nhl/injuries/",
}

async def fetch_injuries(page, sport, url):
    print(f"🔍 Fetching injuries for {sport.upper()} …")

    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    injury_rows = await page.locator("div.injuries-table tbody tr").all()

    injuries = []
    for row in injury_rows:
        try:
            player = await row.locator("td:nth-child(1)").inner_text()
            position = await row.locator("td:nth-child(2)").inner_text()
            team = await row.locator("td:nth-child(3)").inner_text()
            status = await row.locator("td:nth-child(4)").inner_text()
            notes = await row.locator("td:nth-child(5)").inner_text()

            injuries.append({
                "sport": sport,
                "player": player.strip(),
                "position": position.strip(),
                "team": team.strip(),
                "status": status.strip(),
                "notes": notes.strip()
            })
        except:
            continue

    print(f"   → Found {len(injuries)} injuries")
    return injuries

async def main():
    all_injuries = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for sport, url in SPORT_URLS.items():
            rows = await fetch_injuries(page, sport, url)
            all_injuries.extend(rows)

        await browser.close()

    print(f"\n📦 Total injuries scraped: {len(all_injuries)}")

    with open("injuries.json", "w") as f:
        json.dump(all_injuries, f, indent=2)

    print("🎉 Saved injuries.json")

if __name__ == "__main__":
    asyncio.run(main())
