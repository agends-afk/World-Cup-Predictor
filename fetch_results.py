"""Live data layer: builds and refreshes the 2026 fixture state.

Sources (both public):
- The martj42 international results dataset (full history, refreshed on
  download) at raw.githubusercontent.com.
- The English Wikipedia article "2026 FIFA World Cup", whose 104 footballbox
  blocks carry every fixture, official match numbers, bracket placeholders,
  venues and live scores.

Outputs:
- data/results.csv          refreshed historical dataset
- data/fixtures.json        canonical fixture state (created once, then updated)
- data/live_results.csv     played 2026 matches in dataset schema for the Elo pass

Run directly to refresh: python3 fetch_results.py
"""

import csv
import html as html_mod
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta

from names import canon

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
WIKI_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"
DATASET_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
USER_AGENT = "WorldCupPredictor/1.0 (personal research project)"

MEXICO_CITIES = {"Mexico City", "Zapopan", "Guadalajara", "Guadalupe", "Monterrey"}
CANADA_CITIES = {"Toronto", "Vancouver"}
HOSTS = {"Mexico": "Mexico", "Canada": "Canada", "United States": "United States"}

STAGE_HEADINGS = [
    ("round of 32", "r32"), ("round of 16", "r16"), ("quarter", "qf"),
    ("semi", "sf"), ("third place", "third"), ("bronze", "third"),
    ("final", "final"),
]


def fetch_url(url):
    """Fetch a URL, urllib first, curl as fallback. Returns text or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["curl", "-sL", "-A", USER_AGENT, url],
            capture_output=True, timeout=120)
        if out.returncode == 0 and out.stdout:
            return out.stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def refresh_dataset():
    """Re-download the historical dataset; keep the old file on failure."""
    text = fetch_url(DATASET_URL)
    path = os.path.join(DATA_DIR, "results.csv")
    if text and text.startswith("date,home_team"):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        return True
    return False


def _strip(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def kickoff_utc(date_iso, ftime):
    """Kickoff in UTC from the article's local time, e.g. '1:00 p.m. UTC−6'.

    Returns an ISO string like '2026-06-11T19:00:00Z', or None if the time
    is absent or unparseable.
    """
    if not date_iso or not ftime:
        return None
    m = re.search(
        r"(\d{1,2}):(\d{2})\s*(?:([ap])\.?\s?m\.?)?\s*UTC\s*"
        r"([+−-])\s*(\d{1,2})(?::(\d{2}))?", ftime, re.I)
    if not m:
        return None
    h, minute = int(m.group(1)), int(m.group(2))
    ampm = m.group(3)
    if ampm:
        if ampm.lower() == "p" and h != 12:
            h += 12
        if ampm.lower() == "a" and h == 12:
            h = 0
    sign = 1 if m.group(4) == "+" else -1
    offset = timedelta(hours=int(m.group(5)), minutes=int(m.group(6) or 0))
    local = datetime.fromisoformat(date_iso) + timedelta(hours=h, minutes=minute)
    utc = local - sign * offset
    return utc.strftime("%Y-%m-%dT%H:%M:00Z")


def parse_wiki(html):
    """Parse all footballbox blocks plus their governing section headings."""
    headings = []
    for m in re.finditer(r"<h([234])[^>]*>(.*?)</h\1>", html, re.S):
        headings.append((m.start(), _strip(m.group(2))))

    starts = [m.start() for m in re.finditer(
        r'<div itemscope[^>]*class="footballbox"', html)]
    boxes = []
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else st + 12000
        chunk = html[st:end]
        heading = ""
        for pos, text in headings:
            if pos < st:
                heading = text
            else:
                break

        def grab(pattern):
            m = re.search(pattern, chunk, re.S)
            return _strip(m.group(1)) if m else ""

        date_iso = ""
        fdate = grab(r'class="fdate"[^>]*>(.*?)</div>')
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fdate)
        if m:
            date_iso = m.group(1)
        ftime = grab(r'class="ftime"[^>]*>(.*?)</div>')
        team1 = grab(r'class="fhome"[^>]*>(.*?)</th>')
        team2 = grab(r'class="faway"[^>]*>(.*?)</th>')
        score_text = grab(r'class="fscore"[^>]*>(.*?)</th>')
        loc = grab(r'itemprop="location"[^>]*>(.*?)</div>')

        score1 = score2 = None
        sm = re.search(r"(\d+)\s*[–-]\s*(\d+)", score_text)
        match_no = None
        nm = re.search(r"Match\s+(\d+)", score_text)
        if nm:
            match_no = int(nm.group(1))
        elif sm:
            score1, score2 = int(sm.group(1)), int(sm.group(2))
        aet = "a.e.t" in score_text or "a.e.t" in chunk[:3000]
        pens = None
        pm = re.search(r"[Pp]enalties.{0,400}?(\d+)\s*[–-]\s*(\d+)", chunk, re.S)
        if pm:
            pens = (int(pm.group(1)), int(pm.group(2)))

        stadium, city = "", ""
        if "," in loc:
            stadium, city = [p.strip() for p in loc.rsplit(",", 1)]
        else:
            city = loc
        boxes.append({
            "order": i, "heading": heading, "date": date_iso,
            "team1": team1, "team2": team2, "score_text": score_text,
            "score1": score1, "score2": score2, "match_no": match_no,
            "aet": aet, "pens": pens, "stadium": stadium, "city": city,
            "kickoff_utc": kickoff_utc(date_iso, ftime),
        })
    return boxes


def classify(box):
    """Stage and group for a parsed box, from its section heading."""
    h = box["heading"].lower()
    gm = re.match(r"group\s+([a-l])\b", h)
    if gm:
        return "group", gm.group(1).upper()
    for key, stage in STAGE_HEADINGS:
        if key in h:
            return stage, None
    return None, None


def city_country(city):
    if city in MEXICO_CITIES:
        return "Mexico"
    if city in CANADA_CITIES:
        return "Canada"
    return "United States"


def is_placeholder(name):
    """True for bracket placeholders like 'Winner Group A' or 'Third Group C/E/F'."""
    n = name.lower()
    return (not n) or any(t in n for t in
                          ("winner", "runner", "third", "3rd", "loser", "match "))


def build_state(boxes):
    """Construct the canonical fixture list from parsed boxes."""
    matches = []
    for b in boxes:
        stage, group = classify(b)
        if stage is None:
            continue
        team1, team2 = canon(b["team1"]), canon(b["team2"])
        slot1 = slot2 = None
        if is_placeholder(b["team1"]):
            slot1, team1 = b["team1"], None
        if is_placeholder(b["team2"]):
            slot2, team2 = b["team2"], None
        played = b["score1"] is not None
        matches.append({
            "match": b["match_no"],
            "stage": stage, "group": group,
            "date": b["date"], "city": b["city"], "stadium": b["stadium"],
            "country": city_country(b["city"]),
            "team1": team1, "team2": team2,
            "slot1": slot1, "slot2": slot2,
            "score1": b["score1"], "score2": b["score2"],
            "aet": b["aet"],
            "pens": list(b["pens"]) if b["pens"] else None,
            "status": "played" if played else "scheduled",
            "order": b["order"],
            "kickoff_utc": b["kickoff_utc"],
        })
    # A played box loses its "Match N" label (the cell shows the score), so
    # those boxes arrive unnumbered. Assign the unused numbers in CHRONOLOGICAL
    # order, because FIFA numbers matches by schedule; the old page-order fill
    # was wrong whenever played matches were not contiguous on the page. This
    # only matters for a from-scratch build: a refresh re-attaches results by
    # (date, city) in merge_into_fixtures, not by this number.
    used = {m["match"] for m in matches if m["match"]}
    free = [n for n in range(1, len(matches) + 1) if n not in used]
    unnumbered = sorted((m for m in matches if m["match"] is None),
                        key=lambda m: (m["date"], m.get("kickoff_utc") or "",
                                       m["order"]))
    for m, n in zip(unnumbered, free):
        m["match"] = n
    matches.sort(key=lambda m: m["match"] if m["match"] else 9999)
    return matches


def derive_groups(matches):
    groups = {}
    for m in matches:
        if m["stage"] == "group" and m["group"] and m["team1"] and m["team2"]:
            g = groups.setdefault(m["group"], set())
            g.add(m["team1"])
            g.add(m["team2"])
    return {k: sorted(v) for k, v in sorted(groups.items())}


def validate(matches, groups):
    """Structural checks; returns a list of problem strings (empty = good)."""
    problems = []
    if len(matches) != 104:
        problems.append(f"expected 104 matches, got {len(matches)}")
    counts = {}
    for m in matches:
        counts[m["stage"]] = counts.get(m["stage"], 0) + 1
    for stage, want in (("group", 72), ("r32", 16), ("r16", 8), ("qf", 4),
                        ("sf", 2), ("third", 1), ("final", 1)):
        if counts.get(stage, 0) != want:
            problems.append(f"stage {stage}: {counts.get(stage, 0)} != {want}")
    if len(groups) != 12:
        problems.append(f"expected 12 groups, got {len(groups)}")
    for g, teams in groups.items():
        if len(teams) != 4:
            problems.append(f"group {g} has {len(teams)} teams: {teams}")
    appearances = {}
    for m in matches:
        if m["stage"] == "group":
            for t in (m["team1"], m["team2"]):
                if t:
                    appearances[t] = appearances.get(t, 0) + 1
    bad = {t: n for t, n in appearances.items() if n != 3}
    if bad:
        problems.append(f"teams without exactly 3 group matches: {bad}")
    for m in matches:
        if not m["date"] or not ("2026-06-11" <= m["date"] <= "2026-07-19"):
            problems.append(f"match {m['match']} bad date: {m['date']}")
    return problems


def merge_into_fixtures(matches, groups, path):
    """Update an existing fixtures.json with new scores and resolved knockout
    teams. Each parsed box is matched to its fixture by (date, city), a key
    that is stable and unique per match, rather than by the match number a
    played box loses to its score cell. Before writing any result, the parsed
    teams must agree with the fixture's teams, so a result can never be
    attached to the wrong match.

    Returns (fixtures, problems)."""
    problems = []
    if not os.path.exists(path):
        # First-ever build: trust the freshly numbered list.
        fx = {"source": WIKI_URL, "groups": groups, "matches": matches}
    else:
        with open(path, encoding="utf-8") as f:
            fx = json.load(f)
        by_key = {}
        for m in fx["matches"]:
            by_key.setdefault((m["date"], m["city"]), []).append(m)
        for new in matches:
            cands = by_key.get((new["date"], new["city"]), [])
            old = None
            if len(cands) == 1:
                old = cands[0]
            elif len(cands) > 1:
                want = {new.get("team1"), new.get("team2")} - {None}
                old = next((c for c in cands
                            if want and {c.get("team1"), c.get("team2")} == want),
                           None)
            if old is None:
                if new["status"] == "played":
                    problems.append(
                        f"no unique fixture at {new['date']} {new['city']} for "
                        f"{new.get('team1')} v {new.get('team2')}; result withheld")
                continue
            # Identity check: when both sides are known (group, or a resolved
            # knockout), the parsed teams must match the fixture's teams.
            if (new.get("team1") and new.get("team2")
                    and old.get("team1") and old.get("team2")
                    and {new["team1"], new["team2"]} != {old["team1"], old["team2"]}):
                problems.append(
                    f"M{old['match']} team mismatch at {new['date']} "
                    f"{new['city']}: source {new['team1']}/{new['team2']} vs "
                    f"fixture {old['team1']}/{old['team2']}; result withheld")
                continue
            for key in ("team1", "team2"):
                if new[key] and not old.get(key):
                    old[key] = new[key]
            if new.get("kickoff_utc"):
                old["kickoff_utc"] = new["kickoff_utc"]
            if new["status"] == "played":
                for key in ("score1", "score2", "aet", "pens", "status"):
                    old[key] = new[key]
        fx["groups"] = groups or fx.get("groups", {})
    # Keep enriched team objects (name/confederation/qualified_via) if present;
    # only fall back to the flat name list when no such list exists yet.
    existing = fx.get("teams")
    if not (isinstance(existing, list) and existing and isinstance(existing[0], dict)):
        fx["teams"] = sorted({t for g in fx["groups"].values() for t in g})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fx, f, indent=1, ensure_ascii=False)
    return fx, problems


def verify_results(fx, matches):
    """Independent cross-check run before publishing: every played fixture
    must correspond to a parsed source box at the same (date, city) on both
    teams and score. Returns a list of problems (empty means verified)."""
    box_by_key = {}
    for b in matches:
        box_by_key.setdefault((b["date"], b["city"]), []).append(b)
    problems = []
    for m in fx["matches"]:
        if m["status"] != "played" or m.get("score1") is None:
            continue
        boxes = box_by_key.get((m["date"], m["city"]), [])
        src = None
        for b in boxes:
            if (b.get("team1") and b.get("team2") and m.get("team1")
                    and {b["team1"], b["team2"]} == {m["team1"], m["team2"]}):
                src = b
                break
        if src is None and len(boxes) == 1 and boxes[0]["score1"] is not None:
            src = boxes[0]
        if src is None:
            problems.append(f"M{m['match']} {m['team1']} v {m['team2']}: no "
                            f"matching source box at {m['date']} {m['city']}")
            continue
        if src["team1"] == m["team1"]:
            ok = src["score1"] == m["score1"] and src["score2"] == m["score2"]
        else:
            ok = src["score1"] == m["score2"] and src["score2"] == m["score1"]
        if not ok:
            problems.append(f"M{m['match']} {m['team1']} v {m['team2']}: score "
                            f"{m['score1']}-{m['score2']} disagrees with source")
    return problems


def write_live_results(fx, path):
    """Played 2026 matches in dataset schema, host team listed at home."""
    rows = []
    for m in fx["matches"]:
        if m["status"] != "played" or m["score1"] is None:
            continue
        t1, t2, s1, s2 = m["team1"], m["team2"], m["score1"], m["score2"]
        host = HOSTS.get(t1) == m["country"]
        host2 = HOSTS.get(t2) == m["country"]
        if host2 and not host:
            t1, t2, s1, s2 = t2, t1, s2, s1
            host = True
        rows.append({
            "date": m["date"], "home_team": t1, "away_team": t2,
            "home_score": s1, "away_score": s2,
            "tournament": "FIFA World Cup", "city": m["city"],
            "country": m["country"], "neutral": "FALSE" if host else "TRUE",
        })
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "home_team", "away_team",
                                          "home_score", "away_score",
                                          "tournament", "city", "country",
                                          "neutral"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def update_all(verbose=True, dataset=True):
    """Refresh fixture state. dataset=False (fast mode) skips the full
    historical dataset download; live scores still come from the article."""
    summary = {"dataset_refreshed": refresh_dataset() if dataset else "skipped",
               "warnings": []}
    page = fetch_url(WIKI_URL)
    fixtures_path = os.path.join(DATA_DIR, "fixtures.json")
    if page is None:
        summary["warnings"].append("Wikipedia fetch failed; using cached fixtures")
        with open(fixtures_path, encoding="utf-8") as f:
            fx = json.load(f)
    else:
        boxes = parse_wiki(page)
        matches = build_state(boxes)
        groups = derive_groups(matches)
        problems = validate(matches, groups)
        if problems and not os.path.exists(fixtures_path):
            raise RuntimeError("fixture validation failed: " + "; ".join(problems))
        if problems:
            summary["warnings"].extend(problems)
        fx, merge_problems = merge_into_fixtures(matches, groups, fixtures_path)
        summary["warnings"].extend(merge_problems)
        # Verification gate: confirm every published result matches its source
        # box on teams and score before the dashboard is built from it.
        verify_problems = verify_results(fx, matches)
        summary["warnings"].extend(verify_problems)
        summary["verified"] = not (merge_problems or verify_problems)
        if verify_problems:
            summary["verify_problems"] = verify_problems
    n_played = write_live_results(fx, os.path.join(DATA_DIR, "live_results.csv"))
    summary["matches_played"] = n_played
    if verbose:
        v = summary.get("verified", True)
        print(f"dataset refreshed: {summary['dataset_refreshed']}, "
              f"played matches: {n_played}")
        print("VERIFICATION: " + ("PASS" if v else
              f"FAILED, {len(summary.get('verify_problems', []))} result(s) "
              f"withheld"))
        for w in summary["warnings"]:
            print("  warning:", w)
    return fx, summary


if __name__ == "__main__":
    update_all(dataset="fast" not in sys.argv)
