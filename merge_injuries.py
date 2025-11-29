#!/usr/bin/env python3
import json
import re

def normalize(name):
    return re.sub(r'[^a-z]', '', name.lower())

ALIAS = {
    "msu": "michiganstate",
    "ecu": "eastcarolina",
    "bama": "alabama",
    "uga": "georgia",
}

def match_team(team_name, game):
    n = normalize(team_name)
    if n in ALIAS:
        n = ALIAS[n]

    home = normalize(game["home_team"]["name"])
    away = normalize(game["away_team"]["name"])

    if n == home:
        return "home"
    if n == away:
        return "away"
    return None

def main():
    with open("combined.json") as f:
        combined = json.load(f)

    with open("injuries.json") as f:
        injuries = json.load(f)

    count = 0
    for g in combined["data"]:
        g["home_injuries"] = []
        g["away_injuries"] = []

        for inj in injuries:
            side = match_team(inj["team"], g)
            if side == "home":
                g["home_injuries"].append(inj)
                count += 1
            elif side == "away":
                g["away_injuries"].append(inj)
                count += 1

    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Merged {count} injuries across {len(combined['data'])} games")

if __name__ == "__main__":
    main()
