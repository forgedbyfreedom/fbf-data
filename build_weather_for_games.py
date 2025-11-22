name: Auto Fetch & Publish ESPN Odds

on:
  schedule:
    - cron: "*/15 * * * *"
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
          pip install requests pandas numpy scikit-learn

      # -------------------------------------------------
      # Build all supporting data FIRST
      # -------------------------------------------------

      - name: Build FBS stadium list
        run: python3 build_fbs_stadiums.py

      - name: Build referee trends
        run: python3 referee_trends.py

      - name: Build injuries file
        run: python3 build_injuries.py

      - name: Build weather data
        run: python3 build_weather.py

      # -------------------------------------------------
      # Fetch ESPN odds + unify into combined.json
      # -------------------------------------------------
      - name: Fetch ESPN Odds
        run: python3 fetch_espn_all.py

      - name: Tag favorites and dogs
        run: python3 tag_favorites.py

      # -------------------------------------------------
      # Machine-learning predictions
      # -------------------------------------------------

      - name: Train ML models
        run: python3 train_model.py

      - name: Build predictions file
        run: python3 build_predictions.py

      # -------------------------------------------------
      # Commit and push
      # -------------------------------------------------
      - name: Commit and push updated data
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git pull --rebase origin main || true

          git add *.json
          git add predictions.json || true
          git add weather.json || true

          git commit -m "Auto update data $(date -u '+%Y-%m-%d %H:%M:%S UTC')" || echo "No changes"
          git push origin main || echo "Nothing to push"
