"""Fetch projected and confirmed starting XIs from RotoWire's World Cup feed.

Source: rotowire.com/soccer/lineups.php?league=WOC, fetchable over a plain
request. Confirmed XIs post about an hour before kickoff; projected XIs
appear earlier. Each player's full name is in the anchor's title attribute,
which is what we match against EA ratings.

Output data/lineups.json:
{
  "fetched_utc": "...Z",
  "matches": {
    "<match_no>": {
      "team1": {"status": "confirmed|projected", "xi": ["Full Name", ...]},
      "team2": {"status": "confirmed|projected", "xi": [...]}
    }
  }
}

Run: python3 fetch_lineups.py
"""

import json
import os
import re
from datetime import datetime, timezone

from names import canon
from fetch_results import fetch_url

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
URL = "https://www.rotowire.com/soccer/lineups.php?league=WOC"


def parse_lineups(html):
    """Return a list of parsed matches with both teams' XIs and status."""
    # Team names appear in document order as home then visit, per match.
    teams = re.findall(
        r'lineup__mteam is-(home|visit)">\s*([^<]+?)\s*<', html)
    # Each starting XI list, in the same document order.
    lists = re.findall(
        r'<ul class="lineup__list is-(home|visit)">(.*?)</ul>', html, re.S)

    def players(block):
        names = re.findall(r'class="lineup__player"[^>]*>.*?<a[^>]*title="([^"]+)"',
                           block, re.S)
        # RotoWire can append a duplicate or a first substitute after the XI;
        # dedupe in order and keep the 11 starters.
        seen, uniq = set(), []
        for n in names:
            n = n.strip()
            if n and n not in seen:
                seen.add(n)
                uniq.append(n)
        return uniq[:11]

    def status(block):
        return "confirmed" if "is-confirmed" in block else "projected"

    matches = []
    # Walk teams and lists in pairs (home, visit) per match.
    for i in range(0, min(len(teams), len(lists)) - 1, 2):
        (s1, t1), (s2, t2) = teams[i], teams[i + 1]
        (ls1, b1), (ls2, b2) = lists[i], lists[i + 1]
        if s1 != "home" or s2 != "visit" or ls1 != "home" or ls2 != "visit":
            continue  # markup drifted; skip rather than misalign
        xi1, xi2 = players(b1), players(b2)
        if not xi1 and not xi2:
            continue
        matches.append({
            "home": canon(t1), "away": canon(t2),
            "home_status": status(b1), "away_status": status(b2),
            "home_xi": xi1, "away_xi": xi2,
        })
    return matches


def map_to_matches(parsed, fixtures):
    """Align parsed lineups to official match numbers by team pair."""
    pair_to_no = {}
    for m in fixtures["matches"]:
        if m.get("team1") and m.get("team2"):
            pair_to_no[frozenset((m["team1"], m["team2"]))] = (
                m["match"], m["team1"], m["team2"])
    out = {}
    for p in parsed:
        key = frozenset((p["home"], p["away"]))
        if key not in pair_to_no:
            continue
        no, fx1, fx2 = pair_to_no[key]
        # Assign the home/away XIs to fixture team1/team2 by identity.
        if p["home"] == fx1:
            s1, x1, s2, x2 = (p["home_status"], p["home_xi"],
                              p["away_status"], p["away_xi"])
        else:
            s1, x1, s2, x2 = (p["away_status"], p["away_xi"],
                              p["home_status"], p["home_xi"])
        entry = {}
        if len(x1) >= 7:
            entry["team1"] = {"status": s1, "xi": x1}
        if len(x2) >= 7:
            entry["team2"] = {"status": s2, "xi": x2}
        if entry:
            out[str(no)] = entry
    return out


def update(verbose=True):
    html = fetch_url(URL)
    path = os.path.join(DATA, "lineups.json")
    if not html or "lineup__player" not in html:
        if verbose:
            print("lineups: fetch failed or empty; keeping existing file")
        return None
    with open(os.path.join(DATA, "fixtures.json"), encoding="utf-8") as f:
        fixtures = json.load(f)
    parsed = parse_lineups(html)
    mapped = map_to_matches(parsed, fixtures)
    payload = {
        "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z"),
        "matches": mapped,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    if verbose:
        conf = sum(1 for e in mapped.values()
                   for s in e.values() if s["status"] == "confirmed")
        print(f"lineups: parsed {len(parsed)} matches, mapped {len(mapped)} "
              f"to fixtures, {conf} confirmed XIs")
    return payload


if __name__ == "__main__":
    update()
