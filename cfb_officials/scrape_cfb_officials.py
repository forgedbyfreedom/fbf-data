#!/usr/bin/env python3
"""
scrape_cfb_officials.py
College football officiating crews + per-team penalties, game by game.

ESPN carries no officials for college games (the core API's /officials list
is empty for every FBS game), so the historical file had none and nothing
referee-related could be tested for NCAAF. School athletics sites on the
SIDEARM platform publish the official NCAA box score, which carries the full
8-person crew and each team's penalties/yards. Every game has two schools,
so a game is covered when EITHER side's site is SIDEARM.

Output (append-only, resumable):
  cfb_officials/games_raw.jsonl   one line per box-score URL fetched
  cfb_officials/cfb_officials.json  deduped games, one per contest

Usage: python3 cfb_officials/scrape_cfb_officials.py [first_season] [last_season]
"""
import json, os, re, sys, time, threading
import concurrent.futures as cf
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SITES = os.path.join(HERE, "team_sites.json")
RAW = os.path.join(HERE, "games_raw.jsonl")
OUT = os.path.join(HERE, "cfb_officials.json")
HDR = {"User-Agent": "Mozilla/5.0 (fbf-data research; officials study)"}
ROLES = ["referee", "umpire", "linesman", "lineJudge", "backJudge",
         "fieldJudge", "sideJudge", "centerJudge"]
lock = threading.Lock()


def get(url, tries=3):
    for k in range(tries):
        try:
            r = requests.get(url, headers=HDR, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (k + 1))
    return None


def nuxt(text):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    return json.loads(m.group(1)) if m else None


def resolver(A):
    def R(i, depth=0):
        if not isinstance(i, int) or i < 0 or i >= len(A):
            return i
        v = A[i]
        if depth > 5:
            return None
        if isinstance(v, dict):
            return {k: R(x, depth + 1) for k, x in v.items()}
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in ("ShallowReactive", "Reactive", "Ref", "ShallowRef"):
                return R(v[1], depth)
            return [R(x, depth + 1) for x in v]
        return v
    return R


def name_fmt(s):
    """'Gautreaux,Daniel' -> 'Daniel Gautreaux'."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if "," in s:
        last, first = [p.strip() for p in s.split(",", 1)]
        s = f"{first} {last}".strip()
    return re.sub(r"\s+", " ", s) or None


LEGACY_ROLES = {"Referee": "referee", "Umpire": "umpire", "Linesman": "linesman",
                "Line Judge": "lineJudge", "Back Judge": "backJudge",
                "Field Judge": "fieldJudge", "Side Judge": "sideJudge",
                "Center Judge": "centerJudge"}


def parse_legacy(text, url):
    """Older SIDEARM template (server-rendered HTML, no __NUXT_DATA__).
    The NCAA box score lists the VISITOR first, then the home team."""
    import html as _h
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S)
    flat = _h.unescape(re.sub(r"<[^>]+>", " | ", t))
    flat = re.sub(r"\s*\|\s*(\|\s*)*", " | ", flat)
    flat = re.sub(r"\s+", " ", flat)
    crew = {}
    for m in re.finditer(r"(Referee|Umpire|Linesman|Line Judge|Back Judge|Field Judge|Side Judge|Center Judge): \| ([^|]+?) \|", flat):
        nm = name_fmt(m.group(2))
        if nm and not nm.endswith(":") and LEGACY_ROLES[m.group(1)] not in crew:
            crew[LEGACY_ROLES[m.group(1)]] = nm
    d = re.search(r"Date: \| (\d{1,2}/\d{1,2}/\d{4})", flat)
    i = flat.find("Team Score By Quarter")
    rows = re.findall(r"([A-Za-z][A-Za-z0-9&.\-']{1,7}) \| ([^|0-9][^|]*?) \| ((?:\d+ \| ){2,8})", flat[i:i + 600]) if i >= 0 else []
    pen = re.search(r"Penalties - Yds\. \| (\d+) \| - \| (\d+) \| (\d+) \| - \| (\d+)", flat)
    if not crew.get("referee") or not d or len(rows) < 2:
        return None
    (va, vn, vs), (ha, hn, hs) = rows[0], rows[1]
    vsc = int(vs.strip(" |").split(" | ")[-1]); hsc = int(hs.strip(" |").split(" | ")[-1])
    return {
        "url": url, "date": d.group(1),
        "home": hn.strip(), "home_id": ha, "away": vn.strip(), "away_id": va,
        "home_score": hsc, "away_score": vsc,
        "home_pen": int(pen.group(3)) if pen else None, "home_pen_yds": int(pen.group(4)) if pen else None,
        "away_pen": int(pen.group(1)) if pen else None, "away_pen_yds": int(pen.group(2)) if pen else None,
        "referee": crew.get("referee"), "crew": crew, "neutral": None, "template": "legacy",
    }


def parse_box(text, url):
    A = nuxt(text)
    if not A:
        return parse_legacy(text, url)
    R = resolver(A)
    info = None
    for v in A:
        if isinstance(v, dict) and "officials" in v and "homeId" in v and "visitorId" in v:
            info = {k: R(x) for k, x in v.items()
                    if k in ("date", "officials", "homeName", "homeId", "visitorName",
                             "visitorId", "location", "stadium", "attendance", "neutralGame")}
            break
    if not info or not isinstance(info.get("officials"), dict):
        return None
    teams = {}
    for v in A:
        if isinstance(v, dict) and "totals" in v and "score" in v and "id" in v and "lineScores" in v:
            tid = R(v["id"])
            tot = R(v["totals"]) or {}
            pen = (tot.get("penalties") or {}) if isinstance(tot, dict) else {}
            teams[tid] = {
                "name": R(v.get("name")),
                "score": R(v.get("score")),
                "pen_n": pen.get("number"),
                "pen_yds": pen.get("yards"),
            }
    off = info["officials"]
    crew = {r: name_fmt(off.get(r)) for r in ROLES if name_fmt(off.get(r))}
    h, a = teams.get(info["homeId"], {}), teams.get(info["visitorId"], {})

    def i(x):
        try:
            return int(str(x).strip())
        except (TypeError, ValueError):
            return None
    return {
        "url": url,
        "date": info.get("date"),
        "home": info.get("homeName"), "home_id": info.get("homeId"),
        "away": info.get("visitorName"), "away_id": info.get("visitorId"),
        "home_score": i(h.get("score")), "away_score": i(a.get("score")),
        "home_pen": i(h.get("pen_n")), "home_pen_yds": i(h.get("pen_yds")),
        "away_pen": i(a.get("pen_n")), "away_pen_yds": i(a.get("pen_yds")),
        "referee": crew.get("referee"),
        "crew": crew,
        "neutral": info.get("neutralGame"),
    }


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    sites = sorted({d for d in json.load(open(SITES)).values() if d})
    done = set()
    if os.path.exists(RAW):
        for line in open(RAW):
            try:
                r = json.loads(line)
                if not r.get("error"):
                    done.add(r["url"])
            except Exception:
                pass

    # 1. collect box-score links from every site's schedule pages
    def links(job):
        dom, yr = job
        t = get(f"https://{dom}/sports/football/schedule/{yr}")
        if not t:
            return []
        # some SIDEARM themes JSON-escape the slashes in their links
        t = t.replace("\\u002F", "/").replace("\\/", "/")
        paths = set(re.findall(rf'/sports/football/stats/{yr}/[^"\'\s<>]+/boxscore/\d+', t))
        return [f"https://{dom}{p}" for p in paths]
    jobs = [(d, y) for d in sites for y in range(first, last + 1)]
    urls = []
    with cf.ThreadPoolExecutor(16) as ex:
        for got in ex.map(links, jobs):
            urls.extend(got)
    todo = [u for u in sorted(set(urls)) if u not in done]
    print(f"[cfb_officials] {len(sites)} sites, {len(urls)} box scores listed, {len(todo)} to fetch")

    # 2. fetch + parse
    n_ok = n_bad = 0

    def work(u):
        t = get(u)
        g = parse_box(t, u) if t else None
        return u, g
    with open(RAW, "a") as fh, cf.ThreadPoolExecutor(16) as ex:
        for k, (u, g) in enumerate(ex.map(work, todo), 1):
            rec = g or {"url": u, "error": True}
            with lock:
                fh.write(json.dumps(rec) + "\n")
            if g and g.get("referee"):
                n_ok += 1
            else:
                n_bad += 1
            if k % 250 == 0:
                fh.flush()
                print(f"  {k}/{len(todo)} fetched, {n_ok} with a referee")
    print(f"[cfb_officials] new: {n_ok} with referee, {n_bad} without")
    build()


def build():
    """Dedupe raw rows into one record per contest."""
    games = {}
    for line in open(RAW):
        try:
            g = json.loads(line)
        except Exception:
            continue
        if g.get("error") or not g.get("referee") or not g.get("date"):
            continue
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", g["date"])
        if not m:
            continue
        g["date_iso"] = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        # Team names differ by site ("Fla. Atlantic" / "Florida Atlantic",
        # "#7 Iowa State"), so the same contest seen from both schools is
        # matched on date + score pair + referee instead.
        key = (g["date_iso"], tuple(sorted([g.get("home_score") or -1, g.get("away_score") or -1])),
               (g.get("referee") or "").lower())
        # same game seen from both schools' sites: keep the more complete one
        prev = games.get(key)
        if not prev or len(g.get("crew") or {}) > len(prev.get("crew") or {}):
            games[key] = g
    out = sorted(games.values(), key=lambda g: g["date_iso"])
    json.dump({"source": "SIDEARM athletics box scores (official NCAA box score)",
               "games": out}, open(OUT, "w"))
    print(f"[cfb_officials] {len(out)} unique games with a named referee -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        main()
