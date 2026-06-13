"""Fetch EA Sports FC 26 player overall ratings as a player-quality snapshot.

Source: EA's public ratings API (drop-api.ea.com), which returns clean JSON
over a plain request. Ratings move slowly, so this is run occasionally (the
full-rebuild path or manually), and the result is committed to
data/ea_ratings.json; fast refreshes read that file.

Output shape:
{
  "source": "EA Sports FC 26 (drop-api.ea.com)",
  "fetched": "YYYY-MM-DD",
  "teams": { "<our team name>": [ {"name","first","last","ovr","pos"} ... ] }
}

Run: python3 fetch_ratings.py
"""

import json
import os
import time
import unicodedata
import urllib.request

from names import canon

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
API = "https://drop-api.ea.com/rating/ea-sports-fc?locale=en&limit=100&offset={}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

# EA nationality labels that differ from our dataset's canonical names.
EA_NATION_ALIASES = {
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "China PR": "China",
    "United States": "United States",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Cape Verde Islands": "Cape Verde",
    "Holland": "Netherlands",
    "DR Congo": "DR Congo",
    "Congo DR": "DR Congo",
}


def fetch_page(offset):
    req = urllib.request.Request(API.format(offset), headers={
        "User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.load(resp)


def map_nation(label):
    return EA_NATION_ALIASES.get(label, canon(label))


def fetch_all(wc_teams):
    """Pull all men's players, keep those whose nationality is a WC team."""
    wc = set(wc_teams)
    teams = {t: [] for t in wc_teams}
    first = fetch_page(0)
    total = first["totalItems"]
    unmatched = {}
    offset = 0
    while offset < total:
        data = first if offset == 0 else fetch_page(offset)
        for it in data["items"]:
            if (it.get("gender") or {}).get("id") != 0:
                continue  # men's football only
            nat = (it.get("nationality") or {}).get("label", "")
            team = map_nation(nat)
            if team not in wc:
                if nat:
                    unmatched[nat] = unmatched.get(nat, 0) + 1
                continue
            name = it.get("commonName") or (
                f"{it.get('firstName','')} {it.get('lastName','')}".strip())
            teams[team].append({
                "name": name,
                "first": it.get("firstName", ""),
                "last": it.get("lastName", ""),
                "ovr": it.get("overallRating"),
                "pos": (it.get("position") or {}).get("shortLabel", ""),
            })
        offset += 100
        time.sleep(0.05)  # be polite to the API
    # keep each team's players sorted by rating, strongest first
    for t in teams:
        teams[t].sort(key=lambda p: -(p["ovr"] or 0))
    return teams, total, unmatched


def norm(s):
    """Accent-stripped lowercase, for name matching later."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def main():
    with open(os.path.join(DATA, "fixtures.json"), encoding="utf-8") as f:
        fx = json.load(f)
    wc_teams = [t["name"] if isinstance(t, dict) else t for t in fx["teams"]]
    print(f"pulling EA ratings for {len(wc_teams)} World Cup nations...")
    teams, total, unmatched = fetch_all(wc_teams)
    out = {
        "source": "EA Sports FC 26 (drop-api.ea.com)",
        "fetched": __import__("datetime").date.today().isoformat(),
        "teams": teams,
    }
    with open(os.path.join(DATA, "ea_ratings.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    counts = {t: len(p) for t, p in teams.items()}
    empty = [t for t, n in counts.items() if n == 0]
    print(f"scanned {total} players; matched {sum(counts.values())} to WC teams")
    print("players per team (min..max):",
          min(counts.values()), "..", max(counts.values()))
    if empty:
        print("WARNING: no players matched for:", empty)
    # surface near-miss nationality labels that look like WC nations
    sus = {k: v for k, v in unmatched.items() if v >= 15}
    print("unmatched nationality labels with 15+ players (check for WC teams):",
          dict(sorted(sus.items(), key=lambda x: -x[1])[:12]))


if __name__ == "__main__":
    main()
