import json
from pathlib import Path

def merge():
    combined_file = Path("combined.json")
    weather_file = Path("weather.json")
    risk_file = Path("weather_risk1.json")

    if not combined_file.exists():
        print("❌ combined.json missing!")
        return

    with combined_file.open() as f:
        games = json.load(f)

    weather = {}
    if weather_file.exists():
        with weather_file.open() as f:
            weather = {f"{w.get('lat')},{w.get('lon')}": w for w in json.load(f)}

    risks = {}
    if risk_file.exists():
        with risk_file.open() as f:
            risks = {f"{r.get('lat')},{r.get('lon')}": r for r in json.load(f)}

    merged = []

    for g in games:
        venue = g.get("venue") or {}         # ⭐ FIX: protect against None
        lat = venue.get("lat")
        lon = venue.get("lon")

        w_key = f"{lat},{lon}" if lat and lon else None

        g["weather"] = weather.get(w_key, {"indoor": venue.get("indoor", True)})
        g["weatherRisk"] = risks.get(w_key, {"risk": None})

        merged.append(g)

    with open("combined.json", "w") as f:
        json.dump(merged, f, indent=2)

    print(f"[✔] Weather merged for {len(merged)} games.")

if __name__ == "__main__":
    merge()
