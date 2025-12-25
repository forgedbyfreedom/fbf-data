# FBF Data Repository

This repository consolidates all sports gaming files and resources for the Forged By Freedom project. It provides automated data pipelines for fetching, processing, and serving sports betting data across multiple leagues.

## Overview

This repository serves as the central data hub for sports gaming analytics, predictions, and odds tracking. All files are related to sports gaming functionality including:
- Real-time odds and game data from ESPN
- Weather data for outdoor games
- Injury reports and tracking
- ML-based predictions
- Historical performance tracking
- Stadium and venue information

## Repository Organization

### Core Data Fetching Scripts (Active - Used in Workflows)

These scripts are actively used in GitHub Actions workflows and are critical to the system:

- **fetch_espn_all.py** - Main ESPN API integration; fetches odds, scores, and game data for all leagues (NFL, NCAAF, NBA, NCAAB, MLB, NHL, UFC)
- **fetch_weather.py** - Retrieves weather forecasts for outdoor stadium games
- **fetch_injuries.py** - Fetches injury reports for all leagues
- **tag_favorites.py** - Tags favorite teams and applies custom logic for highlighting

### Data Processing Scripts (Active)

- **build_predictions.py** - Generates predictions using the ML model or fallback logic
- **build_fbs_stadiums.py** - Builds and maintains FBS (college football) stadium database
- **build_venues_from_combined.py** - Extracts venue data from combined game data
- **build_historical_results.py** - Processes historical game results for analysis
- **merge_weather.py** - Merges weather data with game information
- **merge_injuries.py** - Merges injury data into the combined dataset
- **weather_risk1.py** - Calculates weather risk scores for games
- **train_model.py** - Trains the ML prediction model on historical data

### Supporting Modules (Active - Imported by Other Scripts)

- **predictions_model.py** - ML model implementation (imported by build_predictions.py)

### Legacy/Backup Scripts (Not Currently Used in Workflows)

These files are not actively used in automated workflows but may have historical value or serve as backups:

- **build_historical.py** - Earlier version of historical data builder (superseded by build_historical_results.py)
- **build_ref_trends.py** - Builds referee trend data (feature not currently active)
- **feature_engineering.py** - Feature engineering utilities (may be used for manual analysis)
- **fetch_injuries_oddstrader.py** - Alternative injury data source from OddsTrader
- **injuries_oddstrader_playwright.py** - Playwright-based scraper for OddsTrader injuries
- **injury_scraper.py** - Generic injury scraping utilities
- **prediction_fallback.py** - Fallback prediction logic (backup system)
- **referee_trends.py** - Referee trend analysis (feature not currently active)
- **track_accuracy.py** - Accuracy tracking for predictions (not currently automated)
- **gpu_backend.py** - GPU acceleration support (optional performance enhancement)
- **sync_all_to_pinecone.py** - Syncs transcript data to Pinecone vector database (optional feature)

**Retention Rationale**: These files are kept as they may contain useful logic for future features or serve as fallback systems. They represent significant development work and could be reactivated if needed.

### Web Interface Files

- **index.html** - Main web interface for displaying odds, predictions, and game data
- **app.js** - JavaScript application logic for the web interface
- **styles.css** - Styling for the web interface
- **CNAME** - Custom domain configuration for GitHub Pages

### Data Files (JSON)

#### League-Specific Latest Data
- **nfl_latest.json** - Current NFL games and odds
- **ncaaf_latest.json** - Current college football games and odds
- **nba_latest.json** - Current NBA games and odds
- **ncaab_latest.json** - Current college basketball games and odds
- **mlb_latest.json** - Current MLB games and odds
- **nhl_latest.json** - Current NHL games and odds
- **arts_latest.json** - Current UFC/MMA events and odds

#### Combined and Processed Data
- **combined.json** - Unified dataset combining all leagues with venue and odds data
- **predictions.json** - ML-generated predictions for upcoming games
- **predictions_fallback.json** - Fallback predictions (backup system)
- **weather_merged.json** - Game data merged with weather information
- **weather.json** - Processed weather data
- **weather_raw.json** - Raw weather API responses
- **weather_risk1.json** - Weather risk scores

#### Reference Data
- **stadiums_master.json** - Comprehensive stadium database
- **stadiums_outdoor.json** - Outdoor stadiums only (for weather tracking)
- **fbs_stadiums.json** - FBS college football stadiums
- **data/stadiums_master.json** - Backup/alternative stadium data location
- **historical.json** - Historical performance summaries
- **historical_results.json** - Historical game results
- **injuries.json** - Current injury reports
- **ref_trends.json** - Referee trending data
- **referee_trends.json** - Referee trend analysis
- **power_ratings.json** - Team power ratings

### Configuration Files

- **requirements.txt** - Python package dependencies for standard deployment
- **requirements-gpu.txt** - Python package dependencies with GPU acceleration support

### Operational Files

- **run_history.log** - Execution history and logging

## GitHub Actions Workflows

### Primary Workflow: fetch_espn_publish.yml
Runs every 15 minutes to:
1. Fetch latest ESPN odds and game data
2. Tag favorites
3. Build stadium files
4. Fetch and process weather data
5. Fetch and merge injury data
6. Build historical results
7. Train ML model (if applicable)
8. Generate predictions
9. Commit and push updated data

### Legacy Workflow: pipeline.yml
Alternative pipeline with similar functionality (kept for backup).

### Utility Workflows
- **diagnose.yml** - Diagnostic and debugging utilities

## File Consolidation Notes

### Removed Files
- **APP.JS** - Duplicate of app.js (identical content, removed to avoid confusion)

### Moved/Fixed Files
- **full_pinecone_sync.yml** - Was misnamed; actually a Python script. Moved to **sync_all_to_pinecone.py** in root directory

### Files Retained Despite Not Being in Active Workflows

The following files are NOT currently used in automated workflows but have been **retained** for the following reasons:

1. **Backup/Fallback Systems**: prediction_fallback.py, predictions_fallback.json
2. **Alternative Data Sources**: fetch_injuries_oddstrader.py, injuries_oddstrader_playwright.py, injury_scraper.py
3. **Optional Features**: referee_trends.py, build_ref_trends.py, ref_trends.json, referee_trends.json, sync_all_to_pinecone.py
4. **Performance Optimization**: gpu_backend.py
5. **Analysis Tools**: track_accuracy.py, feature_engineering.py
6. **Legacy but Functional**: build_historical.py

These files represent significant development work and may be valuable for:
- Future feature activation
- Emergency fallback scenarios
- Manual analysis and debugging
- Alternative data source integration
- Performance optimization experiments

## Data Update Frequency

The automated pipeline runs every 15 minutes via GitHub Actions to ensure:
- Live odds are up-to-date
- Weather forecasts are current
- Injury reports are fresh
- Predictions reflect latest information

## Usage

### Viewing the Web Interface
The web interface is served via GitHub Pages and displays:
- Live odds from ESPN
- ML-generated predictions
- Weather conditions for outdoor games
- Injury reports
- Team statistics and trends

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Fetch latest data
python fetch_espn_all.py

# Generate predictions
python build_predictions.py

# Serve web interface locally
python -m http.server 8000
```

## System Architecture

```
ESPN API → fetch_espn_all.py → *_latest.json → combined.json
                                                      ↓
Weather API → fetch_weather.py → weather.json → merge_weather.py
                                                      ↓
Injury Sources → fetch_injuries.py → injuries.json → merge_injuries.py
                                                      ↓
                                           weather_merged.json
                                                      ↓
Historical Data → build_historical_results.py → train_model.py
                                                      ↓
                                           predictions_model.py
                                                      ↓
                                           build_predictions.py
                                                      ↓
                                           predictions.json
                                                      ↓
                                           index.html (Web UI)
```

## Critical Files - DO NOT DELETE

The following files are **essential** for system operation:
- fetch_espn_all.py
- build_predictions.py
- predictions_model.py (imported by build_predictions.py)
- index.html, app.js (web interface)
- All workflow files in .github/workflows/
- requirements.txt

## License and Attribution

Part of the Forged By Freedom sports analytics platform.

## Last Updated

This README reflects the repository state as of: 2025-12-25

All files in this repository are related to sports gaming and analytics. The organization prioritizes active automated workflows while retaining backup systems and optional features for flexibility.
