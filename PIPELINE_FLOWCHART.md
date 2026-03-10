# FBF Prediction Pipeline Flowchart

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          PHASE 1: DATA INGESTION                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

    ┌─────────────────────┐      ┌─────────────────────┐
    │   ESPN Core API     │      │  BestFightOdds.com  │
    │  (8 sports, 7 days) │      │   (UFC moneylines)  │
    └────────┬────────────┘      └──────────┬──────────┘
             │                              │
             ▼                              ▼
    ┌─────────────────────┐      ┌─────────────────────┐
    │  fetch_espn_all.py  │      │ scrape_ufc_odds.py  │
    │                     │      │                     │
    │ • Teams & scores    │      │ • Fighter MLs       │
    │ • Venues            │      │ • Round O/U lines   │
    │ • Odds (spread/ML)  │      │ • Consensus across  │
    │ • Officials         │      │   6+ sportsbooks    │
    └────────┬────────────┘      └──────────┬──────────┘
             │                              │
             ▼                              │
    ┌─────────────────────┐                 │
    │   combined.json     │◄────────────────┘
    │   (raw game data)   │      merge_ufc_odds.py
    └────────┬────────────┘
             │
             ▼
    ┌─────────────────────┐
    │  tag_favorites.py   │
    │                     │
    │ • Parse spreads     │
    │ • ID fav vs dog     │
    │ • ML fallback       │
    └────────┬────────────┘
             │
             ▼

╔══════════════════════════════════════════════════════════════════════════════════╗
║                      PHASE 2: FEATURE ENRICHMENT                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
    │   WEATHER    │  │  INJURIES    │  │   VENUES     │  │ HISTORICAL DATA  │
    │   PIPELINE   │  │  PIPELINE    │  │  PIPELINE    │  │    PIPELINE      │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
           │                 │                 │                   │
           ▼                 ▼                 ▼                   ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
    │fetch_weather │  │fetch_injuries│  │build_venues  │  │build_historical  │
    │    .py       │  │    .py       │  │_from_combined│  │  _results.py     │
    │              │  │              │  │    .py       │  │                  │
    │ NOAA API     │  │ ESPN +       │  │ stadiums_    │  │ ESPN Core API    │
    │ • Temp (°F)  │  │ Oddstrader   │  │ master.json  │  │ 3 years back     │
    │ • Wind (mph) │  │ • Player     │  │ • lat/lon    │  │ 5 sports         │
    │ • Rain (%)   │  │ • Status     │  │ • 393 venues │  │ ~10K+ games      │
    │ • Forecast   │  │ • Position   │  │              │  │                  │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
           │                 │                 │                   │
           ▼                 │                 │                   │
    ┌──────────────┐         │                 │         ┌─────────┴─────────┐
    │weather_risk1 │         │                 │         │                   │
    │    .py       │         │                 │    ┌────▼─────┐  ┌─────────▼────┐
    │              │         │                 │    │build_elo │  │ build_h2h.py │
    │ Risk 0-3:    │         │                 │    │   .py    │  │              │
    │ 0=clear      │         │                 │    │          │  │ • Matchup    │
    │ 1=mild       │         │                 │    │ • Elo    │  │   history    │
    │ 2=moderate   │         │                 │    │   1500   │  │ • Last 5     │
    │ 3=severe     │         │                 │    │   base   │  │   margins    │
    └──────┬───────┘         │                 │    │ • K=20   │  │ • Avg margin │
           │                 │                 │    └────┬─────┘  └──────┬───────┘
           ▼                 │                 │         │               │
    ┌──────────────┐         │                 │         │               │
    │merge_weather │         │                 │    ┌────▼───────────────▼───────┐
    │    .py       │         │                 │    │   build_ref_trends.py      │
    └──────┬───────┘         │                 │    │                            │
           │                 ▼                 │    │ + scrape_nfl_penalties.py  │
           │          ┌──────────────┐         │    │ + scrape_mlb_umpires.py    │
           │          │merge_injuries│         │    │                            │
           │          │    .py       │         │    │ • home_win_pct             │
           │          └──────┬───────┘         │    │ • over_pct (career+recent) │
           │                 │                 │    │ • fav_cover_pct            │
           │                 │ ┌───────────┐   │    │ • total_stdev (consistency)│
           │                 │ │build_rest │   │    │ • NFL penalty ratios       │
           │                 │ │ _days.py  │   │    │ • MLB ump run tendencies   │
           │                 │ └─────┬─────┘   │    │ • By-sport breakdowns      │
           │                 │       │         │    └────────────┬───────────────┘
           │                 │       │         │                │
           ▼                 ▼       ▼         ▼                ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │   POWER      │  │ SITUATIONAL  │  │   PUBLIC     │  │    LINE      │
    │   RATINGS    │  │   SPOTS      │  │   BETTING    │  │  MOVEMENT    │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                 │                 │
           ▼                 ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │build_power   │  │build_        │  │scrape_public │  │track_line    │
    │ _ratings.py  │  │situational.py│  │ _betting.py  │  │ _movement.py │
    │              │  │              │  │              │  │              │
    │ From hist:   │  │ From hist +  │  │ Covers.com   │  │ Snapshots    │
    │ • net_rating │  │ schedule:    │  │ consensus:   │  │ spread/total │
    │ • off/def    │  │ • B2B games  │  │ • Public %   │  │ each run:    │
    │ • pace       │  │ • Revenge    │  │ • Fade signal│  │ • Spread Δ   │
    │ • H/A splits │  │ • Divisional │  │   (0-3)      │  │ • Total Δ    │
    │ • momentum   │  │ • Timezone   │  │ • 6 sports   │  │ • Direction  │
    │ • ATS record │  │ • Streaks    │  │              │  │ • Move count │
    │ • margin_std │  │ • spot_score │  │              │  │              │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                 │                 │
           └────────┬────────┴────────┬────────┴────────┬────────┘
                    │                 │                 │
                    │    ┌────────────┘                 │
                    │    │  ┌──────────────┐            │
                    │    │  │ STARTERS     │            │
                    │    │  │ (MLB/NHL)    │            │
                    │    │  └──────┬───────┘            │
                    │    │         │                    │
                    │    │         ▼                    │
                    │    │  ┌──────────────┐            │
                    │    │  │fetch_starters│            │
                    │    │  │    .py       │            │
                    │    │  │              │            │
                    │    │  │ ESPN API:    │            │
                    │    │  │ • MLB ERA,   │            │
                    │    │  │   WHIP, K/9  │            │
                    │    │  │ • NHL SV%,   │            │
                    │    │  │   GAA        │            │
                    │    │  └──────┬───────┘            │
                    │    │         │                    │
                    ▼    ▼         ▼                    ▼

    ╔══════════════════════════════════════════════════════════════════╗
    ║                    merge_features.py                            ║
    ║                                                                ║
    ║  Unifies ALL signals onto each game in combined.json:          ║
    ║                                                                ║
    ║  CORE SIGNALS:                                                 ║
    ║  ref_home_bias ──── (blended_home% - 50) × 0.15               ║
    ║  ref_over_bias ──── (blended_over% - 50) × 0.15               ║
    ║  ref_consistency ── avg stdev across officials                 ║
    ║  h2h_margin_avg ─── historical matchup advantage               ║
    ║  rest_diff_days ─── home_rest - away_rest                      ║
    ║  elo_diff ───────── home_elo - away_elo                        ║
    ║  travel_km ──────── away_distance - home_distance              ║
    ║                                                                ║
    ║  ADVANCED SIGNALS:                                             ║
    ║  power_diff ─────── home_net_rating - away_net_rating          ║
    ║  off_def_mismatch ─ (home_off-away_def)-(away_off-home_def)    ║
    ║  pace_avg ───────── (home_pace + away_pace) / 2                ║
    ║  home_split_edge ── home_win_pct - away_away_win_pct           ║
    ║  momentum_diff ──── home_momentum - away_momentum              ║
    ║  recent_ats_diff ── home_recent_ats% - away_recent_ats%        ║
    ║  home/away_margin_stdev ── team volatility                     ║
    ║  spot_score ─────── B2B/revenge/division/timezone (pts)        ║
    ║  public_pct ─────── % public on one side                       ║
    ║  fade_signal ────── 0-3 (0=none, 3=80%+ public)                ║
    ║  spread_delta ───── current - opening spread                   ║
    ║  total_delta ────── current - opening total                    ║
    ║  starter_era_diff ─ away_ERA - home_ERA (MLB)                  ║
    ║  goalie_sv_diff ─── home_SV% - away_SV% (NHL)                 ║
    ║                                                                ║
    ╚════════════════════════════════╤═══════════════════════════════╝
                                     │
                                     ▼

╔══════════════════════════════════════════════════════════════════════════════════╗
║                    PHASE 3: PREDICTION ENGINE                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝

                         combined.json
                     (fully enriched games)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
    ┌─────────────────┐ ┌───────────┐ ┌──────────────────┐
    │  Rule-Based     │ │  ML Model │ │  Monte Carlo     │
    │  Model          │ │           │ │  Simulation      │
    │                 │ │ train_    │ │                  │
    │ predictions_    │ │ model.py  │ │  monte_carlo.py  │
    │ model.py        │ │           │ │                  │
    │                 │ │ • Random  │ │  10,000 sims/game│
    │ • Feature-based │ │   Forest  │ │                  │
    │   scoring       │ │ • 250     │ │  (see detail     │
    │ • Win prob      │ │   trees   │ │   below)         │
    │ • Confidence    │ │ • Spread  │ │                  │
    │                 │ │   + Total │ │                  │
    └────────┬────────┘ │   models  │ └────────┬─────────┘
             │          └─────┬─────┘          │
             │                │                │
             └────────┬───────┘                │
                      │                        │
                      ▼                        │
              ┌───────────────┐                │
              │   ENSEMBLE    │                │
              │               │                │
              │ 60% rule-based│                │
              │ 40% ML model  │                │
              │               │                │
              │ → expected    │                │
              │   margin      │────────────────┘
              │ → expected    │     (feeds into MC)
              │   total       │
              └───────────────┘


╔══════════════════════════════════════════════════════════════════════════════════╗
║               MONTE CARLO SIMULATION DETAIL                                    ║
╚══════════════════════════════════════════════════════════════════════════════════╝

    BUILD EXPECTED VALUES:
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │  expected_margin = base_margin (from Vegas spread)          │
    │                                                             │
    │  CORE ADJUSTMENTS:                                          │
    │    + injury_shift    (away_inj - home_inj) × 0.3 pts       │
    │    + rest_shift      rest_diff × 0.4 pts/day                │
    │    + elo_shift       elo_diff × 0.03 (100 Elo ≈ 3 pts)     │
    │    + h2h_shift       h2h_margin × 0.1                       │
    │    + ref_home_bias   referee tendency                       │
    │    + travel_shift    travel_km × 0.0005 pts/km              │
    │                                                             │
    │  ADVANCED ADJUSTMENTS:                                      │
    │    + power_shift     power_diff × 0.06 (10-pt gap ≈ 0.6)   │
    │    + mismatch_shift  off_def_mismatch × 0.03                │
    │    + split_shift     home_split_edge × 0.02                 │
    │    + momentum_shift  momentum_diff × 0.03                   │
    │    + spot_shift      spot_score × 0.5 (pre-calibrated)      │
    │    + public_shift    ±0.8 pts (when fade_signal ≥ 2)        │
    │    + line_shift      spread_delta × 0.3 (sharp money)       │
    │    + starter_shift   ERA_diff × 0.4 (MLB) / SV% × 8 (NHL) │
    │                                                             │
    │  expected_total = base_total (from Vegas line)              │
    │    - weather_penalty (wind×0.15 + rain%×0.08 + risk×1.5)   │
    │    + ref_over_bias   referee scoring tendency               │
    │    + pace_shift      (pace_avg - total_line) × 0.05         │
    │    + total_line_shift total_delta × 0.25 (sharp money)      │
    │                                                             │
    └────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
    RUN 10,000 SIMULATIONS:
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │  FOR each of 10,000 iterations:                             │
    │                                                             │
    │    sim_margin = gaussian(expected_margin, margin_stdev)      │
    │    sim_total  = gaussian(expected_total, total_stdev)        │
    │                                                             │
    │    Sport stdevs (margin):                                   │
    │      NFL 13.5 | NCAAF 16.0 | NBA 11.0 | NCAAB 11.5        │
    │      NCAAW 12.0 | NHL 2.2 | MLB 3.5 | UFC 0.45            │
    │                                                             │
    │    Sport stdevs (total):                                    │
    │      NFL 10.0 | NCAAF 12.0 | NBA 10.0 | NCAAB 11.0        │
    │      NCAAW 11.0 | NHL 1.8 | MLB 3.0 | UFC 0.3             │
    │                                                             │
    │    STDEV ADJUSTMENTS:                                       │
    │    • Ref consistency: ±15% (predictable refs tighten sims)  │
    │    • Team volatility: 60% sport + 40% team margin_stdev     │
    │    • Divisional games: × 0.92 (tighter, more competitive)   │
    │                                                             │
    │    Count: home_wins, home_covers, overs                     │
    │                                                             │
    └────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
    GENERATE PICKS:
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │  ┌───────────┐  ┌───────────────┐  ┌────────────────┐      │
    │  │  SU PICK  │  │   ATS PICK    │  │   O/U PICK     │      │
    │  │           │  │               │  │                │      │
    │  │ Home if   │  │ Fav covers if │  │ Over if        │      │
    │  │ win% ≥50% │  │ cover% ≥50%   │  │ over% ≥50%    │      │
    │  │           │  │               │  │                │      │
    │  │ Conf =    │  │ Conf =        │  │ Conf =         │      │
    │  │ win% × 100│  │ cover% × 100  │  │ over% × 100   │      │
    │  └───────────┘  └───────────────┘  └────────────────┘      │
    │                                                             │
    └────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼

╔══════════════════════════════════════════════════════════════════════════════════╗
║                       PHASE 4: OUTPUT & TRACKING                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

                         build_predictions.py
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
    ┌───────────────┐ ┌─────────────┐ ┌──────────────────┐
    │predictions    │ │predictions  │ │predictions       │
    │  .json        │ │ _locked.json│ │ _archive.json    │
    │               │ │             │ │                  │
    │ All current   │ │ Frozen at   │ │ Completed games  │
    │ picks         │ │ game time   │ │ (historical)     │
    └───────┬───────┘ └──────┬──────┘ └──────────────────┘
            │                │
            ▼                ▼
    ┌───────────────┐ ┌──────────────┐
    │  index.html   │ │track_accuracy│
    │  Dashboard    │ │    .py       │
    │               │ │              │
    │ • Game cards  │ │ • SU W/L     │
    │ • Ref trends  │ │ • ATS W/L    │──▶ accuracy.json
    │ • Confidence  │ │ • O/U W/L    │
    │ • Filters     │ │ • By sport   │
    └───────────────┘ └──────────────┘


╔══════════════════════════════════════════════════════════════════════════════════╗
║                     NIGHTLY BUILD (4 AM UTC)                                   ║
╚══════════════════════════════════════════════════════════════════════════════════╝

    build_historical.yml (separate workflow):

    build_historical_results.py ──▶ historical_results.json
              │
              ▼
    scrape_nfl_penalties.py ──────▶ nfl_ref_penalties.json
    scrape_mlb_umpires.py ────────▶ mlb_ump_data.json
              │
              ▼
    build_ref_trends.py ──────────▶ referee_trends.json
              │
              ▼
    Commit & push (feeds into next day's 30-min cycle)
```

## Signal Weight Summary

### Core Signals
| Signal | Weight | Impact Example |
|--------|--------|----------------|
| Vegas spread/total | Baseline | Starting point for all projections |
| ML ensemble | 40% of baseline | Adjusts margin + total from historical patterns |
| Injuries | 0.3 pts/injury | 3 injuries = ~1 pt shift |
| Rest days | 0.4 pts/day | 3-day rest edge = ~1.2 pts |
| Elo ratings | 0.03 × diff | 200 Elo gap = ~6 pts |
| H2H history | 0.1 × avg margin | Historical +4 avg = 0.4 pt shift |
| Ref home bias | 0.15 × (pct-50) | Ref at 55% home = +0.75 pts home |
| Ref over bias | 0.15 × (pct-50) | Ref at 58% over = +1.2 pts total |
| Travel | 0.0005 × km | 2000km trip = ~1 pt home edge |
| Weather (wind) | 0.15 × mph | 20mph wind = -3 pts total |
| Weather (rain) | 0.08 × pct | 60% rain = -4.8 pts total |
| Weather (risk) | 1.5 × score | Risk 2 = -3 pts total |

### Advanced Signals
| Signal | Weight | Impact Example |
|--------|--------|----------------|
| Power rating diff | 0.06 × net_rating | 10-pt net gap = ~0.6 pts |
| Off/def mismatch | 0.03 × mismatch | Subtle matchup advantage |
| Pace (total adj) | 0.05 × (pace-line) | High-pace teams push totals |
| Home/away splits | 0.02 × edge | 20% home edge = ~0.4 pts |
| Momentum | 0.03 × diff | Hot team trending up |
| Situational spots | 0.5 × spot_score | B2B = ±2.0, revenge = ±0.5 |
| Public fade | ±0.8 pts | When 70%+ public on one side |
| Line movement | 0.3 × spread_delta | 2-pt move = ~0.6 pts sharp money |
| Total movement | 0.25 × total_delta | Sharp total move signals |
| Starter ERA (MLB) | 0.4 × ERA_diff | 1.0 ERA advantage = 0.4 runs |
| Goalie SV% (NHL) | 8.0 × SV%_diff | 0.010 SV% diff = 0.08 goals |

### Stdev Adjustments (Simulation Tightness)
| Adjustment | Effect | Condition |
|------------|--------|-----------|
| Ref consistency | ±15% stdev | Based on ref total_stdev vs sport avg |
| Team volatility | 40% weight blend | 60% sport default + 40% team margin_stdev |
| Divisional | ×0.92 (8% tighter) | When divisional flag is true |

### Sport-Specific Default Totals (when no Vegas line)
| Sport | Default Total | Margin Stdev | Total Stdev |
|-------|---------------|-------------|-------------|
| NFL | 44.0 | 13.5 | 10.0 |
| NCAAF | 52.0 | 16.0 | 12.0 |
| NBA | 225.0 | 11.0 | 10.0 |
| NCAAB | 145.0 | 11.5 | 11.0 |
| NCAAW | 140.0 | 12.0 | 11.0 |
| NHL | 6.0 | 2.2 | 1.8 |
| MLB | 8.5 | 3.5 | 3.0 |
| UFC | 1.0 | 0.45 | 0.3 |

## Execution Schedule
- **Every 30 minutes**: Full pipeline (ESPN fetch → features → predictions → push)
- **Nightly at 4 AM UTC**: Historical data rebuild + ML model retraining
