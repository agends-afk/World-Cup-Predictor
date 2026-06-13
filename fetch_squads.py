"""Fetch the official 26-man squads for each team.

Source: Wikipedia "2026 FIFA World Cup squads". Used to anchor the
availability baseline to players actually in the squad, so EA ratings for
retired or unselected players of the same nationality (e.g. a still-rated
veteran) do not inflate a team's baseline or show as falsely "missing".

Output data/squads.json: { "<team>": ["Full Name", ...] }

Run: python3 fetch_squads.py
"""

import json
import os
import re

from names import canon
from fetch_results import fetch_url

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"


def parse_squads(html, wc_teams):
    wc = set(wc_teams)
    # Section headers (h2 groups, h3 teams) with ids, in document order.
    heads = [(m.start(), m.group(1))
             for m in re.finditer(r'<h[23][^>]*\bid="([^"]+)"', html)]
    heads.append((len(html), "_end"))
    squads = {}
    for i in range(len(heads) - 1):
        pos, hid = heads[i]
        team = canon(hid.replace("_", " "))
        if team not in wc:
            continue
        region = html[pos:heads[i + 1][0]]
        names = re.findall(
            r'<tr class="nat-fs-player">.*?scope="row"[^>]*>\s*<a[^>]*title="([^"]+)"',
            region, re.S)
        if names:
            # Strip Wikipedia disambiguation suffixes like "(footballer)".
            squads[team] = [re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
                            for n in names]
    return squads


def update(verbose=True):
    with open(os.path.join(DATA, "fixtures.json"), encoding="utf-8") as f:
        fx = json.load(f)
    wc_teams = [t["name"] if isinstance(t, dict) else t for t in fx["teams"]]
    html = fetch_url(URL)
    path = os.path.join(DATA, "squads.json")
    if not html or "nat-fs-player" not in html:
        if verbose:
            print("squads: fetch failed or markup changed; keeping existing file")
        return None
    squads = parse_squads(html, wc_teams)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(squads, f, ensure_ascii=False, indent=1)
    if verbose:
        sizes = {t: len(p) for t, p in squads.items()}
        missing = [t for t in wc_teams if t not in squads]
        print(f"squads: parsed {len(squads)}/48 teams, "
              f"sizes {min(sizes.values())}..{max(sizes.values())}")
        if missing:
            print("  WARNING: no squad parsed for:", missing)
    return squads


if __name__ == "__main__":
    update()
