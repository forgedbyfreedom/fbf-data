#!/usr/bin/env python3
"""
Standalone ESPN Core API debugger.
Pulls:
1. Event metadata
2. Competition details
3. Odds object (spread + total)
"""

import requests
import json

# ==========================================================
# 🔥 ENTER ANY EVENT ID YOU WANT TO DEBUG
# Example using your provided ID
# ==========================================================

event_id = "401674987"

# ==========================================================
# URLs
# ==========================================================

event_url = (
    f"https://sports.core.api.espn.com/v2/sports/football/"
    f"leagues/college-football/events/{event_id}"
)

print("\n==============================")
print("📡 FETCHING EVENT")
print("==============================\n")
print(f"URL: {event_url}\n")

event_res = requests.get(event_url)
event_json = event_res.json()

print(json.dumps(event_json, indent=2))


# ==========================================================
# Locate Competition
# ==========================================================

if "competitions" not in event_json or not event_json["competitions"]:
    print("\n❌ No competitions found in event JSON.")
    exit()

comp_ref = event_json["competitions"][0].get("$ref")

if not comp_ref:
    print("\n❌ competitions[0] has no $ref field!")
    exit()

print("\n==============================")
print("📡 FETCHING COMPETITION")
print("==============================\n")
print(f"URL: {comp_ref}\n")

comp_json = requests.get(comp_ref).json()
print(json.dumps(comp_json, indent=2))


# ==========================================================
# Locate Odds block
# ==========================================================

# Odds is usually like:
# "odds": { "$ref": "https://sports.core.api..." }

odds_ref = None

if "odds" in comp_json and isinstance(comp_json["odds"], dict):
    odds_ref = comp_json["odds"].get("$ref")

if not odds_ref:
    print("\n❌ No odds found in competition JSON.")
    exit()

print("\n==============================")
print("📡 FETCHING ODDS")
print("==============================\n")
print(f"URL: {odds_ref}\n")

odds_json = requests.get(odds_ref).json()
print(json.dumps(odds_json, indent=2))

print("\n==============================")
print("✅ DONE — odds printed above.")
print("==============================\n")

