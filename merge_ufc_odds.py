#!/usr/bin/env python3
"""
merge_ufc_odds.py
Merges scraped UFC odds from BestFightOdds onto UFC bouts in combined.json.

Matches bouts by normalized fighter names, then sets:
- home_ml / away_ml (moneylines)
- spread (derived from moneyline implied probabilities)
- total (2.5 rounds, using over/under line)

Run AFTER: fetch_espn_all.py, scrape_ufc_odds.py
Run BEFORE: build_predictions.py
"""

import json, re, unicodedata

COMBINED = "combined.json"
UFC_ODDS = "ufc_odds.json"


def normalize(name):
    """Normalize fighter name for fuzzy matching (strips accents)."""
    s = unicodedata.normalize("NFD", (name or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s)


def ml_to_implied_prob(ml):
    """Convert American moneyline to implied probability (0-1)."""
    if ml is None:
        return 0.5
    if ml > 0:
        return 100 / (ml + 100)
    else:
        return abs(ml) / (abs(ml) + 100)


def ml_to_spread(home_ml, away_ml):
    """
    Derive a pseudo-spread from moneylines for UFC.
    Returns a negative number for the favorite (convention: home team spread).
    """
    if home_ml is None or away_ml is None:
        return None
    home_prob = ml_to_implied_prob(home_ml)
    away_prob = ml_to_implied_prob(away_ml)
    # Normalize to remove vig
    total_prob = home_prob + away_prob
    if total_prob == 0:
        return 0
    home_fair = home_prob / total_prob
    # Convert to a spread-like value: scale by typical UFC scoring
    # In MMA, spread is essentially a points handicap on rounds
    # A -300 favorite (~75%) maps to roughly -3.5 in "rounds spread"
    # Use logit-style: spread ~ (away_fair - home_fair) * 5
    spread = round((away_prob / total_prob - home_fair) * 5, 1)
    return spread


def main():
    # Load combined.json
    try:
        with open(COMBINED) as f:
            combined = json.load(f)
    except Exception as e:
        print(f"[merge_ufc_odds] Error loading {COMBINED}: {e}")
        return

    games = combined.get("data", [])
    ufc_games = [g for g in games if (g.get("sport") or "").lower() == "ufc"]
    if not ufc_games:
        print("[merge_ufc_odds] No UFC games in combined.json")
        return

    # Load UFC odds
    try:
        with open(UFC_ODDS) as f:
            odds_data = json.load(f)
    except Exception as e:
        print(f"[merge_ufc_odds] Error loading {UFC_ODDS}: {e}")
        return

    bouts = odds_data.get("bouts", [])
    if not bouts:
        print("[merge_ufc_odds] No bouts in ufc_odds.json")
        return

    # Build lookup by normalized fighter names
    # Key: frozenset of (norm_f1, norm_f2) -> bout data
    odds_lookup = {}
    for bout in bouts:
        key = frozenset([normalize(bout["fighter1"]), normalize(bout["fighter2"])])
        odds_lookup[key] = bout

    merged = 0
    for g in ufc_games:
        home = g.get("home_team") or {}
        away = g.get("away_team") or {}
        home_name = home.get("name", "") if isinstance(home, dict) else str(home)
        away_name = away.get("name", "") if isinstance(away, dict) else str(away)

        norm_home = normalize(home_name)
        norm_away = normalize(away_name)

        # Try exact match
        key = frozenset([norm_home, norm_away])
        bout = odds_lookup.get(key)

        # Try fuzzy match: substring containment, reversed names, last-name match
        if not bout:
            for bkey, bval in odds_lookup.items():
                bnames = list(bkey)
                # Strategy 1: one ESPN name is a substring of a BFO name (or vice versa)
                # Handles "Sumudaerji" matching "sumudaerjisumudaerji"
                home_match = any(norm_home in bn or bn in norm_home for bn in bnames) if norm_home else False
                away_match = any(norm_away in bn or bn in norm_away for bn in bnames) if norm_away else False
                if home_match and away_match:
                    bout = bval
                    break

                # Strategy 2: last-name matching
                # Handles "Xiao Long" (ESPN) vs "Long Xiao" (BFO)
                home_last = normalize(home_name.split()[-1]) if home_name else ""
                away_last = normalize(away_name.split()[-1]) if away_name else ""
                if home_last and away_last and len(home_last) >= 3 and len(away_last) >= 3:
                    if (any(home_last in bn for bn in bnames)) and \
                       (any(away_last in bn for bn in bnames)):
                        bout = bval
                        break

        if not bout:
            continue

        # Determine which fighter is "home" (fighter1 in BFO = first listed)
        norm_f1 = normalize(bout["fighter1"])
        norm_f2 = normalize(bout["fighter2"])

        # Match home to fighter1 or fighter2
        home_is_f1 = (norm_home == norm_f1 or norm_home in norm_f1 or norm_f1 in norm_home
                       or normalize(home_name.split()[-1]) in norm_f1)
        if home_is_f1:
            home_ml = bout.get("fighter1_ml")
            away_ml = bout.get("fighter2_ml")
        else:
            home_ml = bout.get("fighter2_ml")
            away_ml = bout.get("fighter1_ml")

        # Set moneylines
        g["home_ml"] = home_ml
        g["away_ml"] = away_ml

        # Derive spread from moneylines
        spread = ml_to_spread(home_ml, away_ml)
        if spread is not None:
            g["spread"] = spread

        # Set total (2.5 rounds is standard UFC)
        if bout.get("over_2_5") is not None:
            g["total"] = 2.5
            g["total_over_ml"] = bout["over_2_5"]
            g["total_under_ml"] = bout.get("under_2_5")

        # Store odds metadata
        g["odds"] = {
            "provider": "BestFightOdds (consensus)",
            "home_ml": home_ml,
            "away_ml": away_ml,
            "spread": spread,
            "total": 2.5 if bout.get("over_2_5") else None,
            "over_2_5": bout.get("over_2_5"),
            "under_2_5": bout.get("under_2_5"),
            "over_1_5": bout.get("over_1_5"),
            "under_1_5": bout.get("under_1_5"),
        }

        # Determine favorite
        if home_ml is not None and away_ml is not None:
            home_abbr = home.get("abbr", home_name[:3].upper()) if isinstance(home, dict) else home_name[:3].upper()
            away_abbr = away.get("abbr", away_name[:3].upper()) if isinstance(away, dict) else away_name[:3].upper()
            if home_ml < away_ml:
                g["favorite"] = home_abbr
            else:
                g["favorite"] = away_abbr

        merged += 1

    # Write back
    with open(COMBINED, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[merge_ufc_odds] Merged odds onto {merged}/{len(ufc_games)} UFC bouts (from {len(bouts)} scraped bouts)")


if __name__ == "__main__":
    main()
