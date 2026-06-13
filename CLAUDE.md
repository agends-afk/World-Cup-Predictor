# World Cup Predictor

Self-contained prediction engine for the 2026 FIFA World Cup (11 June to
19 July 2026). Two outputs: an interactive dashboard (serve.py, AEST
times, team selector, refresh button) and a companion document,
PREDICTIONS.md.

## Session start during the tournament

Run `python3 update.py` FIRST, before anything else, then tell Campbell
what changed: new results since last refresh, model record (hits and
misses), meaningful shifts in title or advancement odds, and any warnings
printed by the fetch step. Then offer nothing further unless asked.

If a matchday produced red cards or confirmed injuries, update
data/adjustments.json before the refresh (see below).

## Refresh pipeline

`python3 update.py [sim_count]` is the FAST path (default, ~5 to 20s):

1. fetch_results.py fast: re-parses the official schedule, live scores and
   kickoff times from the Wikipedia 2026 FIFA World Cup article (no
   dataset download), updates data/fixtures.json and data/live_results.csv.
2. tournament.py: loads data/model_state.json (cached ratings plus goal
   model parameters), applies ONLY unseen results to the ratings with the
   same update rule as the full pass, re-runs 10,000 simulations, writes
   output/predictions.json. Pre-match predictions are FROZEN once a match
   is played. Do not delete output/predictions.json or
   data/model_state.json mid-tournament (the state file rebuilds itself,
   but a rebuild mid-day is just wasted time; the predictions file holds
   the locked record and is not recoverable).
3. report.py and dashboard.py regenerate PREDICTIONS.md and
   output/dashboard.html.

`python3 update.py full` is the HEAVY path: re-downloads the full dataset,
recomputes the Elo history pass and refits the goal model, then saves a
fresh state file. Use occasionally (e.g. weekly) or after editing model.py.

The dashboard server (`python3 serve.py`, http://localhost:8642) exposes
POST /refresh, which runs the fast path; the dashboard's Refresh button
calls it. Incremental ratings were verified to match a full recompute to
the state file's rounding (0.001).

Campbell's entry point is "Start World Cup Dashboard.command"
(double-click in Finder): it runs the fast update, starts serve.py and
opens the browser; serve.py auto-opens the browser unless WC_NO_BROWSER
is set, and a second launch just reopens the running dashboard. Keep this
launcher working whenever the pipeline changes.

backtest.py is standalone validation (2022 holdout); output/backtest.json
feeds the method section of the document.

## Hosting (Vercel + GitHub Actions)

Public site is a static deploy of output/ on Vercel (vercel.json: no build,
serves output/, root rewrites to dashboard.html). .github/workflows/update.yml
runs update.py every 30 min and on manual dispatch (mode fast|full), then
commits and pushes ONLY when output/predictions.json content_hash changed,
so Vercel redeploys on real changes only. content_hash (set in tournament.py)
covers data_through, params, teams, matches, ko_pairings, groups; it excludes
the generated_* timestamps, and the sim uses a fixed seed, so reruns with no
new data are byte-stable. generated_aest is computed via zoneinfo
(Australia/Sydney) so timestamps are right on the UTC CI runner; the
dashboard reads that field directly. The dashboard Refresh button is
host-aware: on localhost it POSTs /refresh (real model run); on the public
site it just reloads predictions.json. data/results.csv is gitignored
(re-downloaded on full rebuild); data/model_state.json IS committed so fast
runs work on a clean checkout. update.py self-heals to a full rebuild if
model_state.json is missing. Setup steps for Campbell are in DEPLOY.md.
Repo should be public (free unlimited Actions minutes); if private, drop the
cron to hourly to stay within the free minute cap.

## Squad news and suspensions

data/adjustments.json holds per-team Elo adjustments:
- "elo": tournament-long adjustment for confirmed absences (scale: one key
  starter -20 to -30, multiple -40 to -60, cap -60).
- "per_match": {"<match_no>": delta} for single-match suspensions (red
  cards, yellow accumulation).
Keep notes and sources in the "note" field. Remove entries when players
return. Conservative by design; doubtful players are mostly excluded.

## Open items

- Deployment: code is committed locally on branch main but NOT yet pushed.
  Campbell publishes via GitHub Desktop then connects Vercel per DEPLOY.md
  (publish public; set Actions write permission; import to Vercel). Confirm
  the first Action run pushed a deploy and the .vercel.app site loads once
  he has done this; the Vercel auto-deploy-on-bot-push assumption is sound
  but unverified end to end until then.
- Verify FIFA's third-place combination table against the constraint-matching
  approximation in tournament.py before the group stage ends (24 to 27 June);
  affects only pre-bracket projections, the real bracket takes over once set.
- Refresh data/adjustments.json after each matchday (injuries, suspensions,
  recoveries). Last refreshed 2026-06-12 from the ESPN injuries tracker.
- Fair play points (cards) are not ingested, so that group tiebreak falls to
  random lots in simulation. Edge case only; revisit if a real group comes
  down to it.
