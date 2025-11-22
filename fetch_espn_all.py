name: Auto Fetch & Publish ESPN Odds

on:
  schedule:
    - cron: "*/15 * * * *"  # every 15 minutes
  workflow_dispatch:

jobs:
  fetch-and-publish:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run ESPN Odds Fetcher (league files)
        run: python3 fetch_espn_all.py

      - name: Rebuild combined.json from league files
        run: python3 build_combined_from_leagues.py

      - name: Commit and push updated data
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"

          git pull --rebase origin main || true

          git add combined.json *.json
          git commit -m "Auto update data $(date -u '+%Y-%m-%d %H:%M:%S UTC')" || echo "No changes"
          git push origin main || echo "Nothing to push"
