"""Lineup-driven availability adjustment.

Combines RotoWire starting XIs (data/lineups.json) with EA FC 26 ratings
(data/ea_ratings.json) to estimate how much a named XI is weaker than the
team's strongest available XI, and converts that to an Elo adjustment for
that match.

Design choices:
- Baseline pool is the team's top EA-rated players, minus any season-long
  absentees listed under "out" in data/adjustments.json. Those season-long
  cases are already handled by the team-level Elo penalty there, so excluding
  them from the baseline avoids penalising the same absence twice.
- Strongest XI = the 11 highest-rated players in that pool.
- Adjustment = K x (named XI mean rating - strongest XI mean rating),
  which is <= 0, weighted by lineup confidence and capped.
- The model abstains (no adjustment) when too few of the named XI match EA
  data, e.g. teams whose domestic league EA does not license.
"""

import json
import os
import statistics
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

# Elo per rating point of XI shortfall. Anchored below the between-team slope
# of Elo on squad rating measured in this dataset (~22.5 Elo/OVR), which is an
# upper bound: a within-team absence shifts only a few positions and a strong
# squad cushions it, so the marginal effect is smaller. EA ratings are also
# subjective and lean kind to ageing players, so a conservative coefficient is
# warranted. Set to about two-thirds of the empirical slope.
K_ELO_PER_OVR = 15.0
CAP_ELO = 120.0            # backstop; does not bind for realistic shortfalls
WEIGHT = {"confirmed": 1.0, "projected": 0.5}
MIN_COVERAGE = 0.8         # need >=80% of the named XI matched to EA
BASELINE_XI = 11


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace(".", "").replace("-", " ").strip()


def last_token(s):
    parts = norm(s).split()
    return parts[-1] if parts else ""


def _index(pool):
    """Precompute match keys for a team's EA player pool."""
    idx = []
    for p in pool:
        full = norm(p.get("name", ""))
        fl = norm(f"{p.get('first','')} {p.get('last','')}")
        idx.append({
            "p": p, "full": full, "fl": fl,
            "last": last_token(p.get("last", "") or p.get("name", "")),
            "first_init": (norm(p.get("first", ""))[:1]
                           or full[:1]),
        })
    return idx


def match_player(name, idx, aliases=None):
    """Match a lineup name to an EA player; return the player dict or None."""
    n = norm(name)
    if aliases and name in aliases:
        target = norm(aliases[name])
        for e in idx:
            if e["full"] == target or e["fl"] == target or e["last"] == last_token(target):
                return e["p"]
    # 1) exact full-name match
    for e in idx:
        if n == e["full"] or n == e["fl"]:
            return e["p"]
    # 2) last-name match, disambiguated by first initial when needed
    ln = last_token(name)
    fi = n[:1]
    cands = [e for e in idx if e["last"] == ln]
    if len(cands) == 1:
        return cands[0]["p"]
    if cands:
        same_init = [e for e in cands if e["first_init"] == fi]
        pick = same_init or cands
        return max(pick, key=lambda e: e["p"].get("ovr") or 0)["p"]
    return None


def pos_bucket(pos):
    p = (pos or "").upper()
    if p == "GK":
        return "GK"
    if p in ("CB", "LB", "RB", "RWB", "LWB", "SW", "LCB", "RCB"):
        return "DEF"
    if p in ("CDM", "CM", "CAM", "DM", "LM", "RM", "LCM", "RCM", "LDM", "RDM"):
        return "MID"
    return "FWD"   # LW, RW, ST, CF and the like


# A realistic strongest XI shape, so the baseline matches what a full-strength
# side actually fields rather than the 11 highest-rated names regardless of
# position (which no real lineup equals).
FORMATION = {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3}


def baseline(pool, out_names, aliases=None, squad_names=None):
    """Position-valid strongest XI mean rating from the available pool.

    When a squad list is given, the pool is first restricted to actual squad
    members, so EA-rated players of the same nationality who are retired or
    unselected do not inflate the baseline."""
    if squad_names:
        full_idx = _index(pool)
        squad_ids = set()
        for nm in squad_names:
            m = match_player(nm, full_idx, aliases)
            if m:
                squad_ids.add(id(m))
        if len(squad_ids) >= BASELINE_XI:
            pool = [p for p in pool if id(p) in squad_ids]
    idx = _index(pool)
    out_keys = set()
    for nm in out_names or []:
        m = match_player(nm, idx, aliases)
        if m:
            out_keys.add(id(m))
    avail = [p for p in pool if id(p) not in out_keys and p.get("ovr")]
    if len(avail) < BASELINE_XI:
        return None, []
    avail.sort(key=lambda p: -p["ovr"])
    buckets = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in avail:
        buckets[pos_bucket(p.get("pos"))].append(p)
    chosen, chosen_ids = [], set()
    for b, n in FORMATION.items():
        for p in buckets[b][:n]:
            chosen.append(p)
            chosen_ids.add(id(p))
    # Backfill to 11 from the best remaining players if a bucket was short.
    if len(chosen) < BASELINE_XI:
        for p in avail:
            if id(p) not in chosen_ids:
                chosen.append(p)
                chosen_ids.add(id(p))
                if len(chosen) == BASELINE_XI:
                    break
    return statistics.mean(p["ovr"] for p in chosen), chosen


def team_adjustment(pool, xi_names, status, out_names, aliases=None,
                    squad_names=None):
    """Compute the availability adjustment for one team in one match."""
    if not pool or not xi_names:
        return None
    base_mean, base_xi = baseline(pool, out_names, aliases, squad_names)
    if base_mean is None:
        return None
    idx = _index(pool)
    matched, matched_keys = [], set()
    for nm in xi_names:
        p = match_player(nm, idx, aliases)
        if p and p.get("ovr"):
            matched.append(p["ovr"])
            matched_keys.add(last_token(p.get("last", "") or p.get("name", "")))
    coverage = len(matched) / max(1, len(xi_names))
    if coverage < MIN_COVERAGE or len(matched) < 8:
        return None
    xi_mean = statistics.mean(matched)
    delta_ovr = xi_mean - base_mean
    weight = WEIGHT.get(status, 0.0)
    elo = max(-CAP_ELO, min(0.0, K_ELO_PER_OVR * delta_ovr * weight))
    missing = [{"name": p["name"], "ovr": p["ovr"]} for p in base_xi
               if last_token(p.get("last", "") or p.get("name", "")) not in matched_keys]
    missing.sort(key=lambda m: -m["ovr"])
    return {
        "elo": round(elo, 1),
        "delta_ovr": round(delta_ovr, 2),
        "status": status,
        "xi_mean": round(xi_mean, 1),
        "baseline_mean": round(base_mean, 1),
        "coverage": round(coverage, 2),
        "missing": missing[:4],
    }


def load_aliases():
    path = os.path.join(DATA, "player_aliases.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("teams", data)   # tolerate the {"teams": {...}} wrapper
    return {}


def load_out_names():
    """Season-long absentees per team, from adjustments.json 'out' lists."""
    path = os.path.join(DATA, "adjustments.json")
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for team, info in json.load(f).get("teams", {}).items():
                if info.get("out"):
                    out[team] = info["out"]
    return out


def compute_all():
    """Return {match_no(str): {"team1": adj|None, "team2": adj|None}} from
    the current lineups and ratings. Empty if data is missing."""
    ea_path = os.path.join(DATA, "ea_ratings.json")
    lu_path = os.path.join(DATA, "lineups.json")
    if not (os.path.exists(ea_path) and os.path.exists(lu_path)):
        return {}
    with open(ea_path, encoding="utf-8") as f:
        ea = json.load(f)["teams"]
    with open(lu_path, encoding="utf-8") as f:
        lineups = json.load(f).get("matches", {})
    aliases_all = load_aliases()
    out_all = load_out_names()
    sq_path = os.path.join(DATA, "squads.json")
    squads = {}
    if os.path.exists(sq_path):
        with open(sq_path, encoding="utf-8") as f:
            squads = json.load(f)

    # The lineup file does not name the teams, so the caller passes the
    # fixture to resolve team1/team2 -> team name. Build a resolver here from
    # fixtures.json instead.
    with open(os.path.join(DATA, "fixtures.json"), encoding="utf-8") as f:
        fixtures = json.load(f)
    no_to_teams = {str(m["match"]): (m.get("team1"), m.get("team2"))
                   for m in fixtures["matches"]}

    result = {}
    for no, entry in lineups.items():
        t1, t2 = no_to_teams.get(no, (None, None))
        out = {}
        for slot, team in (("team1", t1), ("team2", t2)):
            if slot in entry and team and team in ea:
                adj = team_adjustment(
                    ea[team], entry[slot]["xi"], entry[slot]["status"],
                    out_all.get(team), aliases_all.get(team),
                    squads.get(team))
                if adj:
                    out[slot] = adj
        if out:
            result[no] = out
    return result
