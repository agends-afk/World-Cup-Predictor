"""Tournament engine: per-match predictions and full Monte Carlo simulation.

Reads data/fixtures.json (live state), data/results.csv + data/live_results.csv
(history), data/adjustments.json (squad news), and writes
output/predictions.json for the dashboard.

Run: python3 tournament.py [sim_count]
"""

import bisect
import csv
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import date as date_cls, datetime, timedelta

import model

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "output")
HOSTS = {"Mexico", "Canada", "United States"}
SIM_RUNS = 10000
STAKES_PENALTY = -40.0   # Elo applied to a team whose round 3 game is dead
PRE_TOURNAMENT = "2026-06-11"


def host_adv(team, country):
    return model.HOME_ADV if team in HOSTS and team == country else 0.0


def now_sydney():
    """Current time in Sydney. The CI runner is UTC, so convert explicitly
    rather than trusting the machine clock. June/July is always AEST (+10)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Sydney"))
    except Exception:
        return datetime.utcnow() + timedelta(hours=10)


def fmt_aest(dt):
    h = dt.hour % 12 or 12
    ap = "am" if dt.hour < 12 else "pm"
    return (f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')} {dt.year}, "
            f"{h}:{dt.minute:02d}{ap} AEST")


def load_inputs():
    fixtures, adjustments, _ = load_inputs_light()
    results = model.load_results([
        os.path.join(DATA, "results.csv"),
        os.path.join(DATA, "live_results.csv"),
    ])
    return fixtures, adjustments, results


def load_inputs_light():
    """Fixtures and adjustments only; skips the 49,000-row history load."""
    with open(os.path.join(DATA, "fixtures.json"), encoding="utf-8") as f:
        fixtures = json.load(f)
    adjustments = {}
    adj_path = os.path.join(DATA, "adjustments.json")
    if os.path.exists(adj_path):
        with open(adj_path, encoding="utf-8") as f:
            adjustments = json.load(f).get("teams", {})
    return fixtures, adjustments, None


def compute_ratings(results, today_iso):
    ratings, samples, snaps = model.run_elo(
        results, now_iso=today_iso, snapshot_dates=(PRE_TOURNAMENT,))
    alpha, beta = model.fit_goal_model(samples)
    alpha_wc = model.wc_intercept(samples, alpha, beta)
    rho = model.calibrate_rho(samples, alpha_wc, beta)
    params = {"alpha_wc": alpha_wc, "beta": beta, "rho": rho}
    return ratings, params, snaps.get(PRE_TOURNAMENT, {})


def effective(ratings, adjustments, team):
    r = ratings.get(team, model.START_RATING)
    adj = adjustments.get(team, {}).get("elo", 0)
    return r + adj


# ---------------------------------------------------------------- slots

def parse_slot(slot):
    """Slot label -> resolver spec. Pattern-based so wording variants like
    '3rd Group A/B/C', 'Third place Group A/B/C' or 'Winner Match 74' all parse."""
    if slot is None:
        return None
    low = slot.strip().lower()
    m = re.search(r"match\s+(\d+)", low)
    if m:
        return ("LM" if "loser" in low else "WM", int(m.group(1)))
    m = re.search(r"group\s+([a-l](?:/[a-l])*)\b", low)
    if not m:
        return None
    letters = m.group(1).upper().split("/")
    if "3rd" in low or "third" in low:
        return ("T", letters)
    if "runner" in low:
        return ("R", letters[0])
    if "winner" in low:
        return ("W", letters[0])
    return None


# ---------------------------------------------------------------- grids

class GridCache:
    """Caches scoreline grids and their cumulative samplers."""

    def __init__(self, params):
        self.params = params
        self.cache = {}

    def get(self, ra, rb, adv_a, adv_b, et=False):
        key = (round(ra, 1), round(rb, 1), adv_a, adv_b, et)
        hit = self.cache.get(key)
        if hit:
            return hit
        p = self.params
        x = (ra + adv_a - rb - adv_b) / 400.0
        la = model._clamp(2.718281828 ** (p["alpha_wc"] + p["beta"] * x))
        lb = model._clamp(2.718281828 ** (p["alpha_wc"] - p["beta"] * x))
        if et:
            grid = model.score_grid(la * 0.28, lb * 0.28, p["rho"], max_goals=5)
        else:
            grid = model.score_grid(la, lb, p["rho"])
        cum, cells, acc = [], [], 0.0
        n = len(grid)
        for i in range(n):
            for j in range(n):
                acc += grid[i][j]
                cum.append(acc)
                cells.append((i, j))
        entry = (grid, cum, cells)
        self.cache[key] = entry
        return entry

    def sample(self, entry, rng):
        _, cum, cells = entry
        idx = bisect.bisect_left(cum, rng.random() * cum[-1])
        return cells[min(idx, len(cells) - 1)]


def pen_edge(ra, rb, adv_a, adv_b):
    return 1.0 / (1.0 + 10.0 ** (-(ra + adv_a - rb - adv_b) / 1200.0))


# ---------------------------------------------------------------- standings

def rank_teams(teams, played, rng):
    """FIFA group ranking: points, GD, GF, head-to-head among tied, lots."""
    stats = {t: [0, 0, 0] for t in teams}   # pts, gd, gf
    for t1, t2, s1, s2 in played:
        stats[t1][1] += s1 - s2
        stats[t2][1] += s2 - s1
        stats[t1][2] += s1
        stats[t2][2] += s2
        if s1 > s2:
            stats[t1][0] += 3
        elif s2 > s1:
            stats[t2][0] += 3
        else:
            stats[t1][0] += 1
            stats[t2][0] += 1

    def h2h_order(tied):
        sub = [(a, b, s1, s2) for a, b, s1, s2 in played if a in tied and b in tied]
        mini = {t: [0, 0, 0] for t in tied}
        for a, b, s1, s2 in sub:
            mini[a][1] += s1 - s2
            mini[b][1] += s2 - s1
            mini[a][2] += s1
            mini[b][2] += s2
            if s1 > s2:
                mini[a][0] += 3
            elif s2 > s1:
                mini[b][0] += 3
            else:
                mini[a][0] += 1
                mini[b][0] += 1
        return sorted(tied, key=lambda t: (-mini[t][0], -mini[t][1],
                                           -mini[t][2], rng.random()))

    primary = sorted(teams, key=lambda t: (-stats[t][0], -stats[t][1],
                                           -stats[t][2]))
    final = []
    i = 0
    while i < len(primary):
        j = i
        key = tuple(stats[primary[i]])
        while j < len(primary) and tuple(stats[primary[j]]) == key:
            j += 1
        block = primary[i:j]
        final.extend(block if len(block) == 1 else h2h_order(block))
        i = j
    return final, stats


def allocate_thirds(qualified, slots, rng):
    """Assign 8 qualified third-place teams (by group letter) to the 8
    constrained R32 slots via backtracking."""
    letters = set(qualified)
    order = sorted(slots, key=lambda s: len(set(s[1]) & letters))
    assign = {}

    def bt(k, used):
        if k == len(order):
            return True
        match_no, allowed = order[k]
        opts = [l for l in allowed if l in letters and l not in used]
        rng.shuffle(opts)
        for l in opts:
            assign[match_no] = l
            if bt(k + 1, used | {l}):
                return True
            del assign[match_no]
        return False

    if not bt(0, set()):
        # Should not occur with FIFA's slot design; fall back unconstrained.
        rest = list(letters)
        rng.shuffle(rest)
        for (match_no, _), l in zip(order, rest):
            assign[match_no] = l
    return assign


# ---------------------------------------------------------------- simulation

def prepare(fixtures, ratings, adjustments, stakes):
    """Precompute per-fixture static info for fast simulation."""
    prep = {"group_fixtures": {}, "ko": [], "slots3": []}
    for m in fixtures["matches"]:
        if m["stage"] == "group":
            prep["group_fixtures"].setdefault(m["group"], []).append(m)
        else:
            spec1, spec2 = parse_slot(m["slot1"]), parse_slot(m["slot2"])
            if m.get("team1"):
                spec1 = ("FIXED", m["team1"])
            if m.get("team2"):
                spec2 = ("FIXED", m["team2"])
            prep["ko"].append((m, spec1, spec2))
            if spec2 and spec2[0] == "T":
                prep["slots3"].append((m["match"], spec2[1]))
    for g in prep["group_fixtures"]:
        prep["group_fixtures"][g].sort(key=lambda m: (m["date"], m["match"]))
    prep["ko"].sort(key=lambda t: t[0]["match"])
    return prep


def team_rating(team, country, ratings, adjustments, stakes, match_no):
    r = effective(ratings, adjustments, team)
    # Optional per-match adjustments, e.g. suspensions from red or
    # accumulated yellow cards that bite in one specific fixture.
    per_match = adjustments.get(team, {}).get("per_match", {})
    r += per_match.get(str(match_no), 0)
    r += stakes.get((match_no, team), 0.0)
    return r, host_adv(team, country)


def sim_once(prep, ratings, adjustments, params, gc, rng, stakes, collect):
    group_third = {}
    winners, runners = {}, {}
    # Group stage
    for g, fxs in prep["group_fixtures"].items():
        teams = set()
        played = []
        for m in fxs:
            teams.add(m["team1"])
            teams.add(m["team2"])
            if m["status"] == "played":
                played.append((m["team1"], m["team2"], m["score1"], m["score2"]))
            else:
                ra, aa = team_rating(m["team1"], m["country"], ratings,
                                     adjustments, stakes, m["match"])
                rb, ab = team_rating(m["team2"], m["country"], ratings,
                                     adjustments, stakes, m["match"])
                s1, s2 = gc.sample(gc.get(ra, rb, aa, ab), rng)
                played.append((m["team1"], m["team2"], s1, s2))
        order, stats = rank_teams(sorted(teams), played, rng)
        winners[g], runners[g] = order[0], order[1]
        group_third[g] = (order[2], stats[order[2]])
        for pos, t in enumerate(order):
            collect["positions"][t][pos] += 1
            collect["points"][t] += stats[t][0]

    # Rank thirds, take best 8, allocate to slots
    thirds_sorted = sorted(
        group_third.items(),
        key=lambda kv: (-kv[1][1][0], -kv[1][1][1], -kv[1][1][2], rng.random()))
    qualified = {g: tv[0] for g, tv in thirds_sorted[:8]}
    assign = allocate_thirds(qualified, prep["slots3"], rng)

    for g, (t, _) in group_third.items():
        if g in qualified:
            collect["third_q"][t] += 1

    # Knockouts
    ko_winner, ko_loser = {}, {}

    def resolve(spec):
        kind, val = spec
        if kind == "FIXED":
            return val
        if kind == "W":
            return winners[val]
        if kind == "R":
            return runners[val]
        if kind == "T":
            return qualified[assign_lookup[id(spec)]]
        if kind == "WM":
            return ko_winner[val]
        if kind == "LM":
            return ko_loser[val]
        raise ValueError(spec)

    assign_lookup = {}
    for m, spec1, spec2 in prep["ko"]:
        if spec2 and spec2[0] == "T":
            assign_lookup[id(spec2)] = assign[m["match"]]

    for m, spec1, spec2 in prep["ko"]:
        a, b = resolve(spec1), resolve(spec2)
        no = m["match"]
        collect["pairings"][no][(a, b)] += 1
        stage = m["stage"]
        collect["reach"][stage][a] += 1
        collect["reach"][stage][b] += 1
        if m["status"] == "played" and m["score1"] is not None:
            s1, s2 = m["score1"], m["score2"]
            if s1 != s2:
                w, l = (a, b) if s1 > s2 else (b, a)
            else:
                p = m.get("pens") or [1, 0]
                w, l = (a, b) if p[0] > p[1] else (b, a)
        else:
            ra, aa = team_rating(a, m["country"], ratings, adjustments, stakes, no)
            rb, ab = team_rating(b, m["country"], ratings, adjustments, stakes, no)
            s1, s2 = gc.sample(gc.get(ra, rb, aa, ab), rng)
            if s1 == s2:
                e1, e2 = gc.sample(gc.get(ra, rb, aa, ab, et=True), rng)
                if e1 != e2:
                    s1, s2 = s1 + e1, s2 + e2
                else:
                    w_pen = rng.random() < pen_edge(ra, rb, aa, ab)
                    s1, s2 = (s1 + 1, s2) if w_pen else (s1, s2 + 1)
                    # Synthetic +1 marks the shootout winner inside the sim only.
            w, l = (a, b) if s1 > s2 else (b, a)
        ko_winner[no], ko_loser[no] = w, l
        if stage == "final":
            collect["champion"][w] += 1


def team_names(fixtures):
    """Fixture team entries may be plain names or enriched objects."""
    return [t["name"] if isinstance(t, dict) else t for t in fixtures["teams"]]


def simulate(fixtures, ratings, adjustments, params, stakes, n_runs, seed=20260612):
    teams = team_names(fixtures)
    collect = {
        "positions": {t: [0, 0, 0, 0] for t in teams},
        "points": {t: 0.0 for t in teams},
        "third_q": Counter(),
        "reach": {s: Counter() for s in ("r32", "r16", "qf", "sf", "third", "final")},
        "pairings": {m["match"]: Counter() for m in fixtures["matches"]
                     if m["stage"] != "group"},
        "champion": Counter(),
    }
    prep = prepare(fixtures, ratings, adjustments, stakes)
    gc = GridCache(params)
    rng = random.Random(seed)
    for _ in range(n_runs):
        sim_once(prep, ratings, adjustments, params, gc, rng, stakes, collect)
    return collect


# ---------------------------------------------------------------- stakes

def round_number(fixtures):
    """Group fixtures in date order within each group: rounds 1, 2, 3."""
    rounds = {}
    by_group = {}
    for m in fixtures["matches"]:
        if m["stage"] == "group":
            by_group.setdefault(m["group"], []).append(m)
    for g, fxs in by_group.items():
        fxs.sort(key=lambda m: (m["date"], m["match"]))
        for i, m in enumerate(fxs):
            rounds[m["match"]] = i // 2 + 1
    return rounds


def compute_stakes(fixtures, collect, n_runs):
    """Teams already sure of advancing (or elimination) treat their final
    group game as low stakes; apply a rating penalty for that match."""
    stakes = {}
    rounds = round_number(fixtures)
    for m in fixtures["matches"]:
        if m["stage"] != "group" or m["status"] == "played":
            continue
        if rounds.get(m["match"]) != 3:
            continue
        for t in (m["team1"], m["team2"]):
            n32 = collect["reach"]["r32"][t]
            # Only when every simulation agrees, approximating a side whose
            # qualification is already settled before its final group game.
            if n32 == n_runs or n32 == 0:
                stakes[(m["match"], t)] = STAKES_PENALTY
    return stakes


# ---------------------------------------------------------------- output

def outcome_of(m):
    if m["score1"] is None:
        return None
    if m["score1"] > m["score2"]:
        return "team1"
    if m["score1"] < m["score2"]:
        return "team2"
    return "draw"


def displayed_predictions(fixtures, ratings, pre_ratings, adjustments, params,
                          stakes, collect, n_runs, old_by_match):
    out = []
    for m in fixtures["matches"]:
        entry = {
            "match": m["match"], "stage": m["stage"], "group": m["group"],
            "date": m["date"], "city": m["city"], "stadium": m.get("stadium", ""),
            "country": m["country"], "kickoff_utc": m.get("kickoff_utc"),
            "team1": m["team1"], "team2": m["team2"],
            "slot1": m["slot1"], "slot2": m["slot2"],
            "status": m["status"], "projected": False,
        }
        knockout = m["stage"] != "group"
        if m["status"] == "played":
            old = old_by_match.get(m["match"], {})
            if old.get("prediction"):
                entry["prediction"] = old["prediction"]
                entry["retrospective"] = old.get("retrospective", False)
            else:
                ra = effective(pre_ratings, {}, m["team1"])
                rb = effective(pre_ratings, {}, m["team2"])
                entry["prediction"] = model.predict_match(
                    ra, rb, host_adv(m["team1"], m["country"]),
                    host_adv(m["team2"], m["country"]), params, knockout)
                entry["retrospective"] = True
            entry["actual"] = {
                "score1": m["score1"], "score2": m["score2"],
                "aet": m.get("aet", False), "pens": m.get("pens"),
                "outcome": outcome_of(m),
            }
        else:
            t1, t2 = m["team1"], m["team2"]
            if knockout and (not t1 or not t2):
                top = collect["pairings"][m["match"]].most_common(1)
                if top:
                    (a, b), cnt = top[0]
                    t1, t2 = a, b
                    entry["projected"] = True
                    entry["p_pairing"] = round(cnt / n_runs, 3)
                    entry["team1"], entry["team2"] = t1, t2
            if t1 and t2:
                ra, aa = team_rating(t1, m["country"], ratings, adjustments,
                                     stakes, m["match"])
                rb, ab = team_rating(t2, m["country"], ratings, adjustments,
                                     stakes, m["match"])
                entry["prediction"] = model.predict_match(ra, rb, aa, ab,
                                                          params, knockout)
                if (m["match"], t1) in stakes or (m["match"], t2) in stakes:
                    entry["low_stakes"] = True
        out.append(entry)
    return out


# ------------------------------------------------------- model state cache

STATE_PATH = os.path.join(DATA, "model_state.json")


def result_key(d, t1, t2):
    return f"{d}|" + "|".join(sorted((t1, t2)))


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def load_state():
    if not os.path.exists(STATE_PATH):
        return None
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def full_build():
    """Heavy path: full Elo pass over all history plus goal-model fit.
    Run once (or with 'full' to resync); refreshes reuse the saved state."""
    today = date_cls.today().isoformat()
    fixtures, adjustments, results = load_inputs()
    print(f"full build: {len(results)} matches through {results[-1]['date']}")
    ratings, params, pre_ratings = compute_ratings(results, today)
    applied = [result_key(r["date"], r["home_team"], r["away_team"])
               for r in results
               if r["date"] >= PRE_TOURNAMENT and r["tournament"] == "FIFA World Cup"]
    state = {
        "built": datetime.now().isoformat(timespec="seconds"),
        "data_through": results[-1]["date"],
        "params": params,
        "ratings": {t: round(r, 3) for t, r in ratings.items()},
        "pre_ratings": {t: round(r, 3) for t, r in pre_ratings.items()},
        "applied": applied,
    }
    save_state(state)
    print(f"state saved: {len(applied)} tournament results applied, "
          f"params {dict((k, round(v, 4)) for k, v in params.items())}")
    return state


def apply_new_results(state):
    """Fast path: fold only unseen played matches into the cached ratings.
    Identical updates to the full pass (same K, era, margin rules), so the
    incremental ratings match a recompute; goal-model parameters stay fixed."""
    live_path = os.path.join(DATA, "live_results.csv")
    if not os.path.exists(live_path):
        return []
    today = date_cls.today().isoformat()
    seen = set(state["applied"])
    ratings = state["ratings"]
    new = []
    with open(live_path, encoding="utf-8") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: r["date"])
    for r in rows:
        key = result_key(r["date"], r["home_team"], r["away_team"])
        if key in seen:
            continue
        ra = ratings.get(r["home_team"], model.START_RATING)
        rb = ratings.get(r["away_team"], model.START_RATING)
        adv = 0.0 if str(r["neutral"]).upper() == "TRUE" else model.HOME_ADV
        s1, s2 = int(r["home_score"]), int(r["away_score"])
        expected = 1.0 / (1.0 + 10.0 ** (-(ra + adv - rb) / 400.0))
        score = 1.0 if s1 > s2 else (0.0 if s1 < s2 else 0.5)
        k = model.base_k(r["tournament"], r["date"], today)
        delta = (k * model.era_multiplier(r["date"], r["tournament"])
                 * model.mov_multiplier(s1 - s2) * (score - expected))
        ratings[r["home_team"]] = round(ra + delta, 3)
        ratings[r["away_team"]] = round(rb - delta, 3)
        state["applied"].append(key)
        if r["date"] > state["data_through"]:
            state["data_through"] = r["date"]
        new.append(f"{r['home_team']} {s1}-{s2} {r['away_team']} ({r['date']})")
    if new:
        save_state(state)
    return new


def generate(state, n_runs):
    """Simulate and write predictions from the cached state."""
    fixtures, adjustments, _unused = load_inputs_light()
    ratings, params = state["ratings"], state["params"]
    pre_ratings = state["pre_ratings"]

    old_by_match = {}
    pred_path = os.path.join(OUT, "predictions.json")
    if os.path.exists(pred_path):
        with open(pred_path, encoding="utf-8") as f:
            for mm in json.load(f).get("matches", []):
                old_by_match[mm["match"]] = mm

    # Pass 1 without stakes, derive stakes, then the final pass.
    collect = simulate(fixtures, ratings, adjustments, params, {}, n_runs)
    stakes = compute_stakes(fixtures, collect, n_runs)
    if stakes:
        print(f"low-stakes round 3 adjustments: {len(stakes)}")
        collect = simulate(fixtures, ratings, adjustments, params, stakes, n_runs)

    matches = displayed_predictions(fixtures, ratings, pre_ratings, adjustments,
                                    params, stakes, collect, n_runs, old_by_match)

    teams_out = {}
    for g, members in fixtures["groups"].items():
        for t in members:
            pos = collect["positions"][t]
            teams_out[t] = {
                "group": g,
                "rating": round(effective(ratings, adjustments, t), 1),
                "adjust": adjustments.get(t, {}).get("elo", 0),
                "adjust_note": adjustments.get(t, {}).get("note", ""),
                "p_r32": round(collect["reach"]["r32"][t] / n_runs, 4),
                "p_r16": round(collect["reach"]["r16"][t] / n_runs, 4),
                "p_qf": round(collect["reach"]["qf"][t] / n_runs, 4),
                "p_sf": round(collect["reach"]["sf"][t] / n_runs, 4),
                "p_final": round(collect["reach"]["final"][t] / n_runs, 4),
                "p_champion": round(collect["champion"][t] / n_runs, 4),
                "p_third_q": round(collect["third_q"][t] / n_runs, 4),
                "exp_points": round(collect["points"][t] / n_runs, 2),
                "pos_probs": [round(c / n_runs, 4) for c in pos],
            }

    ko_pairings = {}
    for no, counter in collect["pairings"].items():
        ko_pairings[str(no)] = [
            {"pair": list(pair), "p": round(cnt / n_runs, 3)}
            for pair, cnt in counter.most_common(3)]

    backtest = None
    bt_path = os.path.join(OUT, "backtest.json")
    if os.path.exists(bt_path):
        with open(bt_path, encoding="utf-8") as f:
            backtest = json.load(f).get("summary")

    syd = now_sydney()
    payload = {
        "generated": syd.isoformat(timespec="seconds"),
        "generated_aest": fmt_aest(syd),
        "data_through": state["data_through"],
        "sim_runs": n_runs,
        "params": {k: round(v, 4) for k, v in params.items()},
        "teams": teams_out,
        "matches": matches,
        "ko_pairings": ko_pairings,
        "groups": fixtures["groups"],
        "backtest": backtest,
    }
    # Fingerprint the meaningful content (everything except the wall-clock
    # timestamp), so a refresh that found no new data produces an identical
    # hash and the deploy step can skip a pointless redeploy.
    core = {k: payload[k] for k in ("data_through", "sim_runs", "params",
                                    "teams", "matches", "ko_pairings", "groups")}
    payload["content_hash"] = hashlib.sha1(
        json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    top = sorted(teams_out.items(), key=lambda kv: -kv[1]["p_champion"])[:10]
    print("\nTitle odds:")
    for t, info in top:
        print(f"  {t:<15s} rating {info['rating']:7.1f}  champion "
              f"{info['p_champion']*100:5.1f}%  reach KO {info['p_r32']*100:5.1f}%")
    print(f"\nWrote {pred_path}")


def main():
    n_runs = SIM_RUNS
    for a in sys.argv[1:]:
        if a.isdigit():
            n_runs = int(a)
    full = "full" in sys.argv[1:]
    state = load_state()
    if full or state is None:
        state = full_build()
    else:
        new = apply_new_results(state)
        if new:
            print(f"incremental: applied {len(new)} new result(s):")
            for line in new:
                print(f"  {line}")
        else:
            print("incremental: no new results since last refresh")
    generate(state, n_runs)


if __name__ == "__main__":
    main()
