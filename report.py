"""Render PREDICTIONS.md (the single predictions document) from
output/predictions.json.

Run: python3 report.py
"""

import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")

STAGE_NAMES = {"r32": "Round of 32", "r16": "Round of 16",
               "qf": "Quarterfinals", "sf": "Semifinals",
               "third": "Third place playoff", "final": "Final"}


def pct(x, dp=0):
    return f"{x * 100:.{dp}f}%"


def fmt_date(d):
    if not d:
        return ""
    return datetime.strptime(d, "%Y-%m-%d").strftime("%a %d %b")


def call_line(m):
    """One-line prediction: result call, full probabilities, likely score."""
    p = m.get("prediction")
    if not p:
        return "awaiting teams"
    w, d, l = p["p_win"], p["p_draw"], p["p_loss"]
    if w >= max(d, l):
        call, pick = f"**{m['team1']} win {pct(w)}**", "team1"
    elif l >= max(w, d):
        call, pick = f"**{m['team2']} win {pct(l)}**", "team2"
    else:
        call, pick = f"**Draw {pct(d)}**", "draw"
    # Scoreline that matches the predicted result, not the overall modal
    # (which is usually a draw even when a win is favoured).
    sc = (p.get("outcome_scores") or {}).get(
        pick, {"score": p["modal_score"], "p": p["modal_p"]})
    return (f"{call} (win {pct(w)} / draw {pct(d)} / loss {pct(l)} for "
            f"{m['team1']}); most likely score {sc['score']} "
            f"({pct(sc['p'])})")


def played_line(m):
    a = m["actual"]
    p = m.get("prediction", {})
    probs = {"team1": p.get("p_win", 0), "draw": p.get("p_draw", 0),
             "team2": p.get("p_loss", 0)}
    pick = max(probs, key=probs.get)
    res_tag = "result hit" if pick == a["outcome"] else "result miss"
    score_tag = ("score hit"
                 if p.get("modal_score") == f"{a['score1']}-{a['score2']}"
                 else "score miss")
    aet = " aet" if a.get("aet") else ""
    pens = f", {a['pens'][0]}-{a['pens'][1]} pens" if a.get("pens") else ""
    note = " (pre-match view reconstructed)" if m.get("retrospective") else ""
    return (f"**Played: {m['team1']} {a['score1']}-{a['score2']} "
            f"{m['team2']}{aet}{pens}.** Model said "
            f"{call_line(m).replace('**', '')}; "
            f"{res_tag}, {score_tag}{note}")


def main():
    with open(os.path.join(OUT, "predictions.json"), encoding="utf-8") as f:
        data = json.load(f)
    adjustments = {}
    adj_path = os.path.join(BASE, "data", "adjustments.json")
    if os.path.exists(adj_path):
        with open(adj_path, encoding="utf-8") as f:
            adjustments = json.load(f)

    teams = data["teams"]
    matches = sorted(data["matches"], key=lambda m: m["match"])
    played = [m for m in matches if m["status"] == "played"]
    gen = data.get("generated_aest", data["generated"])
    lines = []
    add = lines.append

    add("# World Cup 2026: match predictions")
    add("")
    add(f"Generated {gen}. Results included through {data['data_through']}. "
        f"{len(played)} of 104 matches played. {data['sim_runs']:,} "
        f"tournament simulations.")
    add("")
    add("Every probability below is a model estimate built only from match "
        "results and public squad news, not from betting odds or published "
        "predictions. A favourite can be 75% to win while its most likely "
        "exact score sits near 12 to 15%; goals spread across many "
        "scorelines, so read the two numbers separately.")
    add("")
    add("Refresh after new results with: `python3 update.py` (regenerates "
        "this document).")

    # ------------------------------------------------------------ outlook
    add("")
    add("## Tournament outlook")
    add("")
    add("| Team | Group | Rating | Last 32 | Quarterfinal | Semifinal | Final | Champion |")
    add("| - | - | - | - | - | - | - | - |")
    top16 = sorted(teams.items(), key=lambda kv: -kv[1]["p_champion"])[:16]
    for name, i in top16:
        add(f"| {name} | {i['group']} | {i['rating']:.0f} | {pct(i['p_r32'])} "
            f"| {pct(i['p_qf'])} | {pct(i['p_sf'])} | {pct(i['p_final'])} "
            f"| **{pct(i['p_champion'], 1)}** |")

    if played:
        hits = sum(1 for m in played if m.get("prediction") and
                   max({"team1": m["prediction"]["p_win"],
                        "draw": m["prediction"]["p_draw"],
                        "team2": m["prediction"]["p_loss"]},
                       key=lambda k: {"team1": m["prediction"]["p_win"],
                                      "draw": m["prediction"]["p_draw"],
                                      "team2": m["prediction"]["p_loss"]}[k])
                   == m["actual"]["outcome"])
        mhits = sum(1 for m in played if m.get("prediction") and
                    m["prediction"]["modal_score"] ==
                    f"{m['actual']['score1']}-{m['actual']['score2']}")
        add("")
        add(f"Model record so far: {hits}/{len(played)} correct results, "
            f"{mhits}/{len(played)} exact scorelines.")

    # ------------------------------------------------- ratings cross-check
    ext = data.get("external") or {}
    if any(t.get("fifa_rank") for t in teams.values()):
        add("")
        add("## Ratings cross-check (model vs FIFA)")
        add("")
        add(f"A read-only comparison of the model's own rating order against "
            f"the {ext.get('source', 'FIFA')} ranking (as of "
            f"{ext.get('as_of', 'n/a')}). The FIFA ranking is not an input to "
            f"the model; this is a sanity check. A positive 'vs FIFA' means "
            f"the model rates the team higher than FIFA does.")
        add("")
        add("| Model # | Team | Model rating | FIFA # | FIFA pts | vs FIFA |")
        add("| - | - | - | - | - | - |")
        for name, i in sorted(teams.items(),
                              key=lambda kv: kv[1].get("model_rank", 999)):
            fr, fp = i.get("fifa_rank"), i.get("fifa_points")
            diff = f"{fr - i['model_rank']:+d}" if fr and i.get("model_rank") else "n/a"
            add(f"| {i.get('model_rank', '')} | {name} | {i['rating']:.0f} | "
                f"{fr if fr else 'n/a'} | {fp if fp else 'n/a'} | {diff} |")

    # ------------------------------------------------------------- groups
    add("")
    add("## Group stage")
    by_group = {}
    for m in matches:
        if m["stage"] == "group":
            by_group.setdefault(m["group"], []).append(m)

    for g in sorted(by_group):
        fxs = sorted(by_group[g], key=lambda m: (m["date"], m["match"]))
        add("")
        add(f"### Group {g}")
        add("")
        add("| Team | Pts now | Expected pts | Reach last 32 |")
        add("| - | - | - | - |")
        pts = {t: 0 for t in data["groups"][g]}
        for m in fxs:
            if m["status"] == "played":
                a = m["actual"]
                if a["score1"] > a["score2"]:
                    pts[m["team1"]] += 3
                elif a["score2"] > a["score1"]:
                    pts[m["team2"]] += 3
                else:
                    pts[m["team1"]] += 1
                    pts[m["team2"]] += 1
        for t in sorted(data["groups"][g], key=lambda t: -teams[t]["p_r32"]):
            i = teams[t]
            add(f"| {t} | {pts[t]} | {i['exp_points']:.1f} | {pct(i['p_r32'])} |")
        add("")
        for m in fxs:
            head = (f"M{m['match']}, {fmt_date(m['date'])}, {m['city']}: "
                    f"{m['team1']} v {m['team2']}")
            if m["status"] == "played":
                add(f"- {head}. {played_line(m)}")
            else:
                low = " *(low stakes for a settled side)*" if m.get("low_stakes") else ""
                add(f"- {head}. {call_line(m)}{low}")

    # ----------------------------------------------------------- knockout
    add("")
    add("## Knockout projection")
    add("")
    add("Until the groups finish, knockout pairings show the most frequent "
        "matchup across the simulations with its probability; predictions "
        "are for that projected pairing. Advance probabilities include "
        "extra time and penalties. Once real pairings are set, refreshing "
        "replaces projections with firm predictions.")
    third_slots = [f"M{m['match']} ({m['slot2']})" for m in matches
                   if m["stage"] == "r32" and m.get("slot2")
                   and "3rd" in (m.get("slot2") or "")]
    if third_slots:
        add("")
        add("Third-placed teams feed: " + "; ".join(third_slots) + ".")

    for stage in ("r32", "r16", "qf", "sf", "third", "final"):
        ms = [m for m in matches if m["stage"] == stage]
        if not ms:
            continue
        add("")
        add(f"### {STAGE_NAMES[stage]}")
        add("")
        for m in ms:
            slotline = f"{m.get('slot1') or ''} v {m.get('slot2') or ''}".strip()
            head = f"M{m['match']}, {fmt_date(m['date'])}, {m['city']}"
            if m["status"] == "played":
                add(f"- {head}: {slotline}. {played_line(m)}")
                continue
            p = m.get("prediction")
            if m.get("team1") and p:
                proj = (f" Most likely pairing ({pct(m.get('p_pairing', 0))} "
                        f"of simulations):" if m.get("projected") else "")
                adv = p.get("p_advance", p["p_win"])
                fav, fp = (m["team1"], adv) if adv >= 0.5 else (m["team2"], 1 - adv)
                if p["p_win"] >= max(p["p_draw"], p["p_loss"]):
                    pick = "team1"
                elif p["p_loss"] >= max(p["p_win"], p["p_draw"]):
                    pick = "team2"
                else:
                    pick = "draw"
                sc = (p.get("outcome_scores") or {}).get(
                    pick, {"score": p["modal_score"], "p": p["modal_p"]})
                add(f"- {head}: {slotline}.{proj} **{m['team1']} v "
                    f"{m['team2']}**; 90-minute win {pct(p['p_win'])} / draw "
                    f"{pct(p['p_draw'])} / loss {pct(p['p_loss'])} for "
                    f"{m['team1']}, likely score {sc['score']} "
                    f"({pct(sc['p'])}); **{fav} advance {pct(fp)}**")
            else:
                add(f"- {head}: {slotline}. Awaiting qualified teams.")

    # ------------------------------------------------------------- method
    bt = data.get("backtest") or {}
    params = data["params"]
    add("")
    add("## Method in brief")
    add("")
    add("1. **Team strength.** Weighted Elo over every senior international "
        "since 1900 (49,000+ results). Importance sets the update size: "
        "World Cup finals 60, continental finals 50, qualifiers and Nations "
        "League 40, minor tournaments 30, friendlies 20 (30 if inside the "
        "last 12 months). The 2022 World Cup carries a 1.5x boost and "
        "everything since the 2022 final 1.25x, so current form leads. "
        "Margin of victory scales updates; opposition strength is priced "
        "into every exchange. Home advantage is 100 points, which here "
        "applies to the three hosts in their own stadiums.")
    add(f"2. **Goals.** Each side's expected goals is exp(alpha + beta x "
        f"rating gap / 400), fitted on competitive internationals since "
        f"2010 and centred on World Cup scoring (alpha {params['alpha_wc']}, "
        f"beta {params['beta']}), with a Dixon-Coles low-score correction "
        f"(rho {params['rho']}). Scoreline and result probabilities come "
        f"from the resulting goal grid; knockouts add extra time and a "
        f"near-coin-flip penalty model.")
    add(f"3. **Simulation.** The rest of the tournament runs "
        f"{data['sim_runs']:,} times with FIFA tiebreakers, best-thirds "
        f"ranking and constrained bracket allocation. Played matches are "
        f"locked to real scores and ratings update after every match, so "
        f"the model sharpens as the tournament goes. Pre-match predictions "
        f"are frozen once a match is played.")
    add("4. **Lineups.** When a starting XI is published (projected ahead of "
        "kickoff, confirmed about an hour before), that match's odds are "
        "adjusted for the players missing from it versus the team's strongest "
        "available XI, weighed by EA Sports FC 26 ratings (15 Elo per rating "
        "point of shortfall, capped, confirmed lineups at full weight and "
        "projected at half). The live dashboard shows the shift and who is "
        "out per match; this report carries the full-strength model. Lineup "
        "data is not used in the tournament simulation, since future XIs are "
        "unknowable.")
    if bt:
        add(f"5. **Validation.** Trained only on pre-2022 data, the engine "
            f"called {pct(bt.get('outcome_accuracy_static', 0))} of Qatar "
            f"2022 results (random baseline 33%) and "
            f"{pct(bt.get('modal_score_hit_rate', 0))} of exact scores, "
            f"with honest confidence (picks made at about 60% confidence "
            f"landed about 64% of the time). Qatar was an unusually "
            f"upset-heavy edition; the two biggest misses were the Saudi "
            f"Arabia and Cameroon shocks.")
    if adjustments.get("teams"):
        add("")
        add(f"**Squad adjustments (as of {adjustments.get('as_of', '')}).** "
            "Confirmed absences reduce a team's effective rating; "
            "suspensions apply to single matches:")
        add("")
        for t, a in sorted(adjustments["teams"].items()):
            per = ""
            if a.get("per_match"):
                per = " " + "; ".join(
                    f"match {k}: {v}" for k, v in a["per_match"].items())
            add(f"- {t} {a.get('elo', 0):+d}{per}: {a.get('note', '')}")
    add("")
    add("**Limits.** Third-place bracket routing approximates FIFA's "
        "combination table by constraint matching (the real bracket takes "
        "over once set). Injury adjustments are judgement-scaled and may "
        "overlap with form already in the ratings. Lineups, tactics and "
        "referees sit outside the model. Penalties are close to a coin "
        "flip. Treat every number as an estimate with real uncertainty.")
    add("")
    add("Data: the open martj42 international results dataset; the "
        "official schedule and live scores as published on the Wikipedia "
        "2026 FIFA World Cup article (re-parsed each refresh and "
        "cross-checked against the dataset); squad news from press "
        "reports cited above.")
    add("")

    path = os.path.join(BASE, "PREDICTIONS.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
