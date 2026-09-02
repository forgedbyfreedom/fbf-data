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
