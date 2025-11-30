#!/usr/bin/env python3
import json
import asyncio
from playwright.async_api import async_playwright

SPORTS = {
    "nfl": "https://www.oddstrader.com/nfl/injuries/",
    "ncaaf": "https://www.oddstrader.com/ncaa-college-football/injuries/",
    "nba": "https://www.oddstrader.com/nba/injuries/",
    "ncaab": "https://www.oddstrader.com/ncaa-college-basketball/injuries/",
    "nhl": "https://www.oddstrader.com/nhl/injuries/",
}

async def scrape_injuries(playwright):
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()

    all_injuries = []

    for sport, url in SPORTS.items():
        print(f"\n🔍 Fetching {sport.upper()} injuries from Oddstrader…")

        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_selector("table", timeout=60000)

            # Extract rows dynamically rendered by JS
            rows = await page.query_selector_all("table tbody tr")

            if not rows:
                print(f"⚠️ No injury rows found for {sport}")
                continue

            for r in rows:
                cells = await r.query_selector_all("td")
                if len(cells) < 4:
                    continue

                player = (await cells[0].inner_text()).strip()
                team = (await cells[1].inner_text()).strip()
                status = (await cells[2].inner_text()).strip()
                detail = (await cells[3].inner_text()).strip()

                all_injuries.append({
                    "sport": sport,
                    "player": player,
                    "team": team,
                    "status": status,
                    "detail": detail,
                })

            print(f"✅ Found {len(rows)} rows for {sport}")

        except Exception as e:
            print(f"❌ Error scraping {sport}: {e}")

    await browser.close()
    return all_injuries


async def main():
    async with async_playwright() as playwright:
        injuries = await scrape_injuries(playwright)

        print(f"\n📦 Total injuries scraped: {len(injuries)}")

        with open("injuries.json", "w") as f:
            json.dump({"injuries": injuries}, f, indent=2)

        print("\n🎉 Saved injuries.json")

if __name__ == "__main__":
    asyncio.run(main())
