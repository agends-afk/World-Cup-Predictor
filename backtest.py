"""Holdout validation: train on data before the 2022 World Cup, then
predict all 64 matches of Qatar 2022 and score the predictions.

Run: python3 backtest.py
"""

import json
import math

import model

CUTOFF = "2022-11-20"          # 2022 tournament start
WC_END = "2022-12-18"
GROUP_END = "2022-12-03"       # group stage finished 2 December


def outcome_label(hs, aw):
    if hs > aw:
        return "W"
    if hs < aw:
        return "L"
    return "D"


def main():
    matches = model.load_results(["data/results.csv"])
    train = [m for m in matches if m["date"] < CUTOFF]
    wc = [m for m in matches
          if m["tournament"] == "FIFA World Cup" and CUTOFF <= m["date"] <= WC_END]
    print(f"Training matches: {len(train)}, 2022 WC matches: {len(wc)}")

    ratings, samples, snaps = model.run_elo(
        train, now_iso=CUTOFF, snapshot_dates=(CUTOFF,), sample_max_date=CUTOFF)
    start_ratings = snaps[CUTOFF]

    alpha, beta = model.fit_goal_model(samples)
    alpha_wc = model.wc_intercept(samples, alpha, beta)
    rho = model.calibrate_rho(samples, alpha_wc, beta)
    params = {"alpha_wc": alpha_wc, "beta": beta, "rho": rho}
    print(f"alpha={alpha:.4f} alpha_wc={alpha_wc:.4f} beta={beta:.4f} rho={rho:.3f}")
    print(f"baseline goals per side at even ratings: {math.exp(alpha_wc):.3f}")

    top = sorted(start_ratings.items(), key=lambda t: -t[1])[:12]
    print("\nTop ratings going into Qatar 2022:")
    for name, r in top:
        print(f"  {name:<15s} {r:7.1f}")

    # Dynamic replay: ratings update as the tournament progresses,
    # mirroring how the 2026 predictor will run.
    live = dict(start_ratings)
    rows, brier, logloss, acc, modal_hits = [], 0.0, 0.0, 0, 0
    acc_static = 0
    buckets = {}
    for m in sorted(wc, key=lambda r: r["date"]):
        adv = 0.0 if m["neutral"] else model.HOME_ADV
        ra = live.get(m["home_team"], model.START_RATING)
        rb = live.get(m["away_team"], model.START_RATING)
        pred = model.predict_match(ra, rb, adv, 0.0, params)
        sa = start_ratings.get(m["home_team"], model.START_RATING)
        sb = start_ratings.get(m["away_team"], model.START_RATING)
        pred_static = model.predict_match(sa, sb, adv, 0.0, params)

        actual = outcome_label(m["home_score"], m["away_score"])
        probs = {"W": pred["p_win"], "D": pred["p_draw"], "L": pred["p_loss"]}
        pick = max(probs, key=probs.get)
        picks_static = {"W": pred_static["p_win"], "D": pred_static["p_draw"],
                        "L": pred_static["p_loss"]}
        if pick == actual:
            acc += 1
        if max(picks_static, key=picks_static.get) == actual:
            acc_static += 1
        if pred["modal_score"] == f"{m['home_score']}-{m['away_score']}":
            modal_hits += 1
        brier += sum((probs[k] - (1.0 if k == actual else 0.0)) ** 2 for k in probs)
        logloss += -math.log(max(probs[actual], 1e-9))
        b = int(probs[pick] * 10) / 10.0
        buckets.setdefault(b, [0, 0])
        buckets[b][1] += 1
        if pick == actual:
            buckets[b][0] += 1
        rows.append({
            "date": m["date"], "match": f"{m['home_team']} v {m['away_team']}",
            "actual": f"{m['home_score']}-{m['away_score']}",
            "pick": pick, "p_pick": round(probs[pick], 3),
            "modal": pred["modal_score"], "stage": "group" if m["date"] <= GROUP_END else "knockout",
        })

        # Elo update with the same live rule the 2026 engine uses.
        expected = 1.0 / (1.0 + 10.0 ** (-(ra + adv - rb) / 400.0))
        score = {"W": 1.0, "D": 0.5, "L": 0.0}[actual]
        g = model.mov_multiplier(m["home_score"] - m["away_score"])
        k = model.base_k(m["tournament"], m["date"], CUTOFF)
        delta = k * model.era_multiplier(m["date"], m["tournament"]) * g * (score - expected)
        live[m["home_team"]] = ra + delta
        live[m["away_team"]] = rb - delta

    n = len(wc)
    group_rows = [r for r in rows if r["stage"] == "group"]
    g_acc = sum(1 for r in group_rows if r["pick"] == r["actual_outcome"]) if False else \
        sum(1 for r in group_rows
            if r["pick"] == outcome_label(*[int(v) for v in r["actual"].split("-")]))
    summary = {
        "n_matches": n,
        "outcome_accuracy": round(acc / n, 4),
        "outcome_accuracy_static": round(acc_static / n, 4),
        "group_stage_accuracy": round(g_acc / len(group_rows), 4),
        "modal_score_hit_rate": round(modal_hits / n, 4),
        "mean_brier": round(brier / n, 4),
        "mean_log_loss": round(logloss / n, 4),
        "params": {k: round(v, 4) for k, v in params.items()},
        "note": ("Knockout outcome labels use the recorded score, which includes "
                 "extra time, so a few 90-minute draws count against the model."),
    }
    print("\nBacktest summary:", json.dumps(summary, indent=2))
    print("\nConfidence buckets (hit rate when pick probability in bucket):")
    for b in sorted(buckets):
        hit, tot = buckets[b]
        print(f"  p {b:.1f}+ : {hit}/{tot} = {hit / tot:.2f}")

    with open("output/backtest.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "matches": rows}, f, indent=1)
    print("\nWrote output/backtest.json")


if __name__ == "__main__":
    main()
