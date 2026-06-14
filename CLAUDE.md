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
   Results are attached to fixtures by (date, city), which is stable and
   unique per match, NOT by match number: a played box shows its score in
   place of "Match N", so the number is unreliable for played matches (this
   caused a score swap between matches before it was fixed). merge_into_fixtures
   refuses to write a result unless the parsed teams match the fixture's teams,
   and verify_results re-checks every published result against its source box
   on teams and score, printing VERIFICATION: PASS/FAILED. A result that fails
   is withheld (the match stays "scheduled") rather than attached to the wrong
   fixture, so a swap cannot reach the dashboard. build_state also numbers
   played boxes chronologically (only used on a from-scratch rebuild).
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
runs update.py every 15 min (cron 7,22,37,52 past, offset to dodge GitHub's
top-of-hour delay so confirmed lineups ~1h pre-kickoff are caught) and on
manual dispatch (mode fast|full), then commits and pushes ONLY when
output/predictions.json content_hash changed,
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

## Ratings cross-check and fair odds

data/external_ratings.json is a read-only FIFA ranking snapshot (rank +
points, as of 2026-06-11), NOT a model input. tournament.py attaches
fifa_rank/fifa_points plus the model's own model_rank to each team in
predictions.json (payload.external holds source/as_of). The dashboard team
panel shows model rank vs FIFA rank; report.py prints a full cross-check
table. FIFA's next update is 2026-07-20, so the snapshot is correct through
the group stage; refresh it after that date by editing the file (or re-run
the pot/whereig extraction). The dashboard also shows fair decimal odds per
scheduled match, computed client-side as 1/probability (win/draw/loss and
advance), labelled back-only-above with a not-advice caveat.

## Lineup availability engine

Live missing-player adjustment, wired into per-match predictions (not the
tournament sim, since future XIs are unknowable). Pipeline:
- fetch_ratings.py: EA Sports FC 26 overall ratings from drop-api.ea.com
  (curl-fetchable JSON, ~17.5k players paged by 100), filtered to the 48 WC
  nations into data/ea_ratings.json. Slow (~80s, 175 requests); run on the
  full path or when the file is missing, not every tick. EA does not license
  the Qatari league, so Qatar has ~no rated players and the engine abstains.
- fetch_squads.py: official 26-man squads from the Wikipedia squads page into
  data/squads.json. Anchors the baseline to real squad members so retired or
  unselected same-nationality players (e.g. Suarez for Uruguay) do not inflate
  it or show as falsely missing. Day-to-day players (e.g. Davies) ARE in the
  squad, so their per-match absence is priced.
- fetch_lineups.py: RotoWire WOC feed (curl-fetchable), per-match XIs with
  confirmed/projected status, mapped to match numbers by team pair, into
  data/lineups.json. Fetched every refresh.
- availability.py: matches lineup names to EA players (accent-stripped, last
  name + first initial; data/player_aliases.json for misses), builds a
  position-valid strongest XI baseline (4-3-3 by EA position, excluding the
  adjustments.json "out" list), and returns per-team Elo = 15 x (named XI mean
  OVR - baseline mean OVR), capped at 120, confirmed full weight / projected
  half. Abstains below 80% XI coverage.
- tournament.py displayed_predictions stores prediction (lineup-adjusted),
  prediction_base (full strength), and lineup {team1,team2: {elo, missing,
  status...}} when active. A lineup supersedes the manual per_match suspension
  (no double count). The dashboard shows the before/after and who is out; a
  played match keeps the frozen lineup-adjusted call.
Calibration note: K=15 Elo/OVR, set deliberately below the measured
between-team slope of Elo on squad rating (~22.5 Elo/OVR, an upper bound for
within-team availability effects) and conservative for EA subjectivity and
its lean toward ageing players. No historical lineup feed to backtest
against; tunable in availability.py (K_ELO_PER_OVR, CAP_ELO). EA ratings only
size this per-match adjustment; they never touch base Elo, the goal model or
the simulation, and the adjustment is a difference so a uniform ratings-level
bias cancels.

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
- Lineup engine: data/player_aliases.json is empty; add entries for any
  recurring unmatched lineup names (e.g. a player EA lists under a variant).
  Refresh data/ea_ratings.json and data/squads.json via a full run after EA
  rating updates or squad changes; both are committed snapshots.
- Refresh data/external_ratings.json (FIFA cross-check snapshot) after FIFA's
  2026-07-20 ranking update; until then the 2026-06-11 snapshot is current.
- Verify FIFA's third-place combination table against the constraint-matching
  approximation in tournament.py before the group stage ends (24 to 27 June);
  affects only pre-bracket projections, the real bracket takes over once set.
- Refresh data/adjustments.json after each matchday (injuries, suspensions,
  recoveries). Last refreshed 2026-06-12 from the ESPN injuries tracker.
- Fair play points (cards) are not ingested, so that group tiebreak falls to
  random lots in simulation. Edge case only; revisit if a real group comes
  down to it.
