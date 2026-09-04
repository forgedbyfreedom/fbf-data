# Model notes

What the prediction model does, what was measured, and what was rejected.
Written 2026-09-02. Numbers here come from 5 seasons of NFL and college
football in `historical_results.json` unless stated otherwise.

## The baseline you have to beat

The closing spread is the best public predictor of a football result that
exists. Measured against 2,299 held-out games:

| predictor | MAE vs actual margin |
| --- | --- |
| the closing line | **9.25 points** |
| the RandomForest that used to run here | 10.46 points |

Correlation of the closing line with actual margin is 0.693. Elo alone manages
0.442. Breakeven at -110 is 52.38%. Sustained 53-55% ATS is a strong result;
anything claiming much more over a real sample is almost certainly measuring
itself wrong.

The practical consequence: **the model is an opinion layered on the line, not a
replacement for it.** `monte_carlo.build_expected_values()` is built that way
on purpose - it starts at `-spread` and adjusts.

## What was removed, and why

### The ML ensemble (removed 2026-09-02)

`build_predictions.py` used to blend a RandomForest into every projection at
40% weight. Its entire feature vector was:

    spread, total, is_nfl, is_ncaaf, is_nba, is_ncaab, is_nhl

The market line, the market total, and sport flags. None of the Elo, power
rating, injury, weather, referee, rest, head-to-head, line-movement or
public-betting features this pipeline computes ever reached it. It correlated
0.867 with the line - a noisy photocopy - and scored 51.4% ATS out of sample,
below breakeven. It was making projections worse, and it could not have done
otherwise.

### A residual model was built and rejected

The right way to use ML here is to predict the *residual* - `margin + spread`,
how much a game beats the line - because any skill at that is edge by
definition. That was built with causally-derived, leak-free features (Elo
walked forward game by game, rest days, recent form, season week), trained on
prior seasons and tested forward:

| test season | ATS, all games | ATS, model edge > 3 |
| --- | --- | --- |
| 2023 | 52.8% | 59.9% |
| 2024 | 49.7% | 54.0% |
| 2025 | 50.2% | 47.3% |
| **pooled** | **50.9%** | 55.4% |

Pooled ATS is below the 52.38% breakeven, and the apparent edge in the filtered
bucket decays from 59.9% to 47.3% across three consecutive forward seasons.
That is the shape of overfitting, not skill. **No ML component ships until it
beats the line on a forward test.** Do not reintroduce one on in-sample numbers.

Note: `train_test_split(random_state=42)` on game data leaks the future into
the past - it trains on Week 10 and tests on Week 3. Always split on season.

## Bugs found and fixed on 2026-09-02

**`compute_ats()` graded the favourite against a home-relative spread.** It
tested `fav_margin > spread`, so a home favourite at -6 winning by 4 evaluated
as `4 > -6` and was recorded as covering. Stored `ats_result` agreed with the
actual outcome only **48.9%** of the time and reported the favourite covering
**99.7%** of all games. `build_power_ratings.py` and `build_ref_trends.py` both
read that field, so every team ATS rate and every referee trend was built on it.

**The spread column held two sign conventions at once.** `fetch_event_detail()`
converted the spread to an absolute value, but only on the branch where the
favourite had to be derived. Rows whose favourite came from the odds details
kept a signed home-relative number. Anything trained or graded on that column
was reading a mix.

**The adjustment layer was uncapped.** `expected_margin` was the line plus
eleven unbounded adjustment terms. On 2026-09-01 the mean adjustment on games
priced at 14+ was **-18.0 points**, and Furman at Tennessee (line +46.5) was
adjusted by **-103.8** to an expected margin of -57.3 - the model projected
Furman to win by 57. The board took the underdog in **37 of 37** games priced
at 14 or more. It now caps at `MAX_MARGIN_ADJ` (7 NFL, 10 NCAAF).

**Ratings were poisoned by thin samples.** Arkansas-Pine Bluff carried a net
rating of -55.3 off 4 games, against 32-37 games for the FBS sides it was
compared with. Ratings now shrink toward the league mean with weight
`games / (games + 8)`. Arkansas-Pine Bluff went to -25.6, Furman -32.0 to
-18.9; Ohio State and Georgia barely moved.

## Design rules that came out of this

1. **Anchor on the line.** Every projection starts at `-spread`.
2. **Cap the opinion.** The adjustment layer may move the line by at most one
   score and a half. It has never demonstrated the skill to earn more.
3. **Say nothing rather than something wrong.** When the adjustment clamps, the
   inputs are outside what the ratings can represent - usually a side with
   almost no game history. The ATS pick is suppressed (`ats_suppressed`)
   instead of published. On the 2026-09-02 slate this suppressed 28 of 86 games
   and moved the ATS split from 69% dogs to a balanced 49/51.
4. **Show what the pick engine believes.** The displayed projection is the
   Monte Carlo expected margin, not the standalone rule model, so the board and
   the picks cannot disagree.
5. **Publish calibration, not just accuracy.** `accuracy.json` carries a
   `calibration` block bucketing graded picks by their stated confidence
   against what that bucket actually did. A 55% call that hits 55% is the goal;
   a 70% call that hits 51% is worse than useless.

## Which features are actually doing work (measured 2026-09-02)

`build_expected_values()` stashes a per-factor breakdown on each game
(`_adj_breakdown`, `_total_adj_breakdown`), so this can be re-measured any time
rather than assumed. On an 81-game slate:

| margin factor | games active | mean pts | max pts |
| --- | --- | --- | --- |
| team quality composite (Elo + power + momentum + H2H) | 79/81 | 1.28 | 3.92 |
| home/away splits | 79/81 | 0.53 | 1.41 |
| line movement | 30/81 | 0.18 | 1.80 |
| situational spots | 57/81 | 0.17 | 0.48 |
| off/def mismatch | 78/81 | 0.07 | 0.26 |
| public betting fade | 2/81 | 0.02 | 0.80 |
| rest | 0/81 | 0 | 0 |
| referee home bias | 0/81 | 0 | 0 |
| injuries | 0/81 | 0 | 0 |
| travel | 0/81 | 0 | 0 |
| starters | 0/81 | 0 | 0 |

Totals side: weather 3.25 mean (53/81), big-spread-under 1.59, pace 1.33,
referee over bias 0.60, total mismatch 0.07, total line move 0.07.

**Team quality is the model.** Everything else is a rounding error on top of it.

### Rest was measuring the offseason

Before the fix, `rest` was the largest term in the entire layer - mean 10.7
points, max 107.5. `rest_data.json` stores raw days since a team last played,
which across an offseason is ~240. Differencing unclamped gave Furman at
Tennessee a `rest_diff_days` of **-430**, and at 0.25 points a day that is a
-107 point "rest advantage" for the FCS side.

This, not the ratings, was the main cause of the 37-of-37 underdog board.
`MAX_USEFUL_REST_DAYS = 14` now clamps each side before differencing. Past a
bye week, more days off is a schedule gap, not rest.

### Three features are dead, one is a constant in disguise

- **Injuries: 0 of 81 games.** `injuries.json` holds entries for 3 teams.
  The pipeline advertises injury reports and does not have them.
- **Travel: 0 of 81.** `travel_km` never populates.
- **Starters: 0 of 81.** Correct - it only covers MLB pitchers and NHL goalies.
- **Referees: 0 of 81 games have a crew assigned.** ESPN does not publish them
  until close to kickoff. The code fell back to a sport constant, so every game
  carried a `ref_home_bias` of exactly 0.5 or 0.6 - a blanket home-field nudge
  wearing a referee label, double-counting something the market already prices.
  Now zero when no crew is known. 562 refs are profiled and none are being used.

### Three stacked dog leans, two of them unsupported

`make_picks()` carried four separate thumbs on the scale toward underdogs:

1. `base_rate` regression toward 0.49 - **kept**, it matches the data.
2. `(abs_spread - 7) * 0.005` - up to **19.8 points** of cover probability at a
   46.5 line. **Removed.**
3. A "big spread dampener" pulling toward 50% - **kept**, it is symmetric and
   only reduces confidence.
4. A further college dog lean of up to 6 points on 15+ spreads, justified as
   "underdogs historically cover ~55-58% of the time". **Removed.**

Against 5 repaired seasons, the favourite covers:

| spread | games | favourite covers | dog lean the code applied |
| --- | --- | --- | --- |
| 0-7 | 5,410 | 46.8% | none |
| 7-14 | 2,042 | 48.5% | 1.8 pts |
| 14-25 | 1,089 | 49.1% | 6.2 pts |
| 25+ | 913 | 50.1% | 17.8 pts |

The correction ran backwards - heaviest exactly where favourites do best,
absent where underdogs actually have an edge. The "55-58%" claim in the comment
is contradicted by the same repository's own data.

Effect of removing them: ATS picks fell from 62 to 25, high-confidence from 38
to 9, and games priced at 14 or more now produce **no ATS pick at all** - the
model correctly reports no opinion on a 46-point spread instead of
mechanically fading it.

## RETRACTED: "the edge is asymmetric"

An earlier version of this file reported a 60.6% underdog edge from 9,121
games. **That result was wrong and the rule built on it has been removed.**

The feature builder never filtered by sport. The sample was mostly basketball
and hockey; football was under half of it. Re-run on football alone, deriving
on 2021-2023 and holding out 2024-2025:

| model leans | train (fav covers) | holdout (fav covers) |
| --- | --- | --- |
| underdog | 52.1% | 54.9% |
| neutral | 48.7% | 44.5% |
| favourite | 50.1% | 50.9% |

The effect is absent. Lesson recorded because it nearly shipped: check what is
actually in the sample before believing the number that comes out of it.

## What was tested, and what survived (2026-09-03)

3,893 football games with a closing line, 2021-2025. Derivation on 2021-2023,
a single evaluation on the 2024-2025 holdout.

### Nothing beats the closing line

Projection error, mean absolute, sweeping the weight on the team quality term:

| quality weight | train MAE | holdout MAE |
| --- | --- | --- |
| **0.0 (line only)** | **11.382** | **10.979** |
| 0.4 (was production) | 11.462 | 11.061 |
| 0.8 | 11.619 | 11.266 |

Monotonic, optimum at zero. Swept per subset - NFL, NCAAF, early season, late
season, spreads under 7, spreads over 14 - and every apparent training gain
reversed on the holdout.

Fitted optimally by OLS across Elo, rest, form and season stage, predicting the
residual the line does not explain:

- holdout MAE **11.138** against **10.979** for trusting the line
- holdout **R-squared of -0.02** - worse than a horizontal line
- holdout ATS **48.0%**

A full scan of candidate splits (spread size, sport, rest edges, form, season
stage, totals, high and low totals) produced **no signal whose lower confidence
bound cleared the 52.4% breakeven.**

**Conclusion: with the data available there is no demonstrated ATS or totals
edge in football.** The quality composite and rest are now weighted zero. They
were not merely unhelpful - they were making the projection measurably worse.

One caveat that matters: ESPN's stored spread is at or near the closing line,
which is the hardest possible benchmark. The live model runs against an earlier
line. That cannot be tested with this data, and it is the most plausible place
for a real edge to exist.

### What DID improve: the uncertainty was wrong

| | production before | measured (train) | holdout |
| --- | --- | --- | --- |
| NFL margin SD | 13.5 | **12.88** | 12.42 |
| NCAAF margin SD | 16.0 | **15.10** | 15.12 |
| NFL total SD | 6.5 | **13.21** | 12.81 |
| NCAAF total SD | 7.5 | **15.55** | 15.41 |

The totals figures were roughly **half** the true dispersion, which made every
over/under probability far more confident than the data supports. O/U
confidence on the current slate now peaks at 54.9% rather than the inflated
numbers it was printing.

With the corrected values, win probability calibration on the untouched
2024-2025 holdout:

| predicted | games | predicted | actual | gap |
| --- | --- | --- | --- | --- |
| 0-35% | 233 | 22.6% | 22.3% | -0.3 |
| 35-50% | 269 | 41.7% | 39.4% | -2.3 |
| 50-65% | 302 | 58.7% | 60.3% | +1.5 |
| 65-80% | 260 | 71.5% | 69.6% | -1.8 |
| 80-100% | 458 | 93.0% | 96.1% | +3.0 |

**Weighted mean absolute calibration error: 1.99 percentage points**, against
2.47 for the old standard deviations. Nothing was fitted to the holdout.

### The gate

No directional claim is made, because none is supported. `MIN_EDGE_PTS = 2.0`
is a magnitude test: at the measured college SD of 15.1, a 2 point disagreement
with the line is a 55% cover and a 1 point disagreement is 52.6%, inside the
vig. Below that the model has nothing to say.

The inputs still live - injuries, weather, line movement, public betting -
could not be tested, because the historical file carries no snapshot of them.
They are unvalidated, not endorsed. Weather is the one with a physical
rationale for totals.

### What this engine now claims

It does **not** claim to beat the market. It claims to produce a projection as
accurate as the closing line, and win probabilities calibrated to within about
two percentage points. Those are the claims the evidence supports.

## The one experiment that can still find an edge

Every accuracy test above compared the model to ESPN's stored spread, which
sits at or very near the **closing** line. That is the hardest benchmark in
sports betting - it contains every injury report, weather update and sharp bet
placed right up to kickoff - and nobody can bet it. The model runs on a 6-hour
cycle and sees a number hours or days earlier.

Whether it beats *that* number is a different question and it has never been
tested, because the historical file carries no line-movement snapshots.

`build_line_study.py` now runs on every pull and accumulates `line_study.json`,
append-only. Per game it records:

- the line at the earliest lock (the number that could actually have been bet)
- the closing line, from the last snapshot before kickoff
- how many snapshots were seen
- the model's projection and which side it leaned
- the final result, graded against BOTH the locked line and the closing line
- **`clv_points`** - closing line value

### Why CLV is the metric to watch

If the model likes a team at +7 and the market closes at +5, it captured 2
points of CLV. Sustained positive CLV is the best available predictor of
long-run profitability, and it reads far faster than win rate: a few dozen
games gives a usable signal where ATS results need several hundred.

CLV is computed for every game the model had an opinion on, not only games
where a pick cleared MIN_EDGE_PTS, so the sample builds at the speed of the
schedule rather than the speed of the gate.

### How to read it

- **Mean CLV clearly positive over 50+ games** - the model is finding
  something the market later agrees with. That is the first real evidence of an
  edge, and it would justify loosening MIN_EDGE_PTS and publishing more picks.
- **Mean CLV around zero** - the model is neither ahead of nor behind the
  market. Expect ATS around 50% forever, and treat the board as a projection
  tool rather than a betting tool.
- **Mean CLV negative** - the model is systematically on the wrong side of
  where the market moves. That is worse than no signal and would argue for
  weighting the remaining live adjustments to zero as well.

First reading, on the 7 games available at build time: mean CLV +0.29 points,
but the line never moved on 5 of them - the pipeline had only just resumed, so
most games had a single snapshot. This number means nothing yet. It becomes
meaningful once games are seen 10-20 times across the week before kickoff,
which is what the 6-hour cadence produces during a normal season week.

## Where to look next

The honest answer is that edge, if it exists here, is narrow and specific -
particular spots, not a general model. Candidates worth testing once there is a
real football sample, each on a forward test:

- late injury news that moved after the line was set
- weather games (wind especially) against the total
- line movement against public betting percentages (reverse line movement)
- rest mismatches at the extremes

Test each one the same way: forward seasons, breakeven at 52.38%, and a
willingness to conclude that it does not work.
