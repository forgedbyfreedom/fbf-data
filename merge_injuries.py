#!/usr/bin/env python3
import json

def normalize_team(name: str) -> str:
    return (
        name.lower()
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace(",", "")
        .replace("'", "")
        .replace("  ", " ")
        .strip()
    )

def main():
    with open("combined.json") as f:
        combined = json.load(f)

    with open("injuries.json") as f:
        inj = json.load(f)

    games = combined.get("data") or combined.get("games") or []
    inj_rows = inj.get("injuries", [])

    inj_index = {}  # (sport, team_norm) -> list[rows]
    for row in inj_rows:
        sport = (row.get("sport") or "").lower()
        team_norm = row.get("team_norm") or normalize_team(row.get("team"))
        if not sport or not team_norm:
            continue
        inj_index.setdefault((sport, team_norm), []).append(row)

    merged_count = 0
    for g in games:
        sport = (g.get("sport") or "").lower()
        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}

        home_name = home_team.get("name") or home_team.get("abbr") or g.get("home")
        away_name = away_team.get("name") or away_team.get("abbr") or g.get("away")

        home_key = (sport, normalize_team(home_name or ""))
        away_key = (sport, normalize_team(away_name or ""))

        home_inj = inj_index.get(home_key, [])
        away_inj = inj_index.get(away_key, [])

        if home_inj or away_inj:
            merged_count += 1

        g["home_injuries"] = home_inj
        g["away_injuries"] = away_inj
        g["injury_count_home"] = len(home_inj)
        g["injury_count_away"] = len(away_inj)

    combined["data"] = games

    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Merged injuries onto {merged_count}/{len(games)} games.")

if __name__ == "__main__":
    main()
