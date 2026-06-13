# World Cup 2026 Predictor

Predicts every match of the 2026 FIFA World Cup: win, draw or loss
probabilities, the most likely scoreline with its own probability, and
tournament odds (reaching each round, winning the title) from 10,000
simulations. When a starting lineup is published, a match's odds adjust for
the players missing from it, weighed by EA Sports FC 26 ratings, with the
shift shown on each affected match. Two outputs: an interactive **dashboard**
(selectable teams, upcoming fixtures, results, fair odds, all times in AEST,
one-click refresh) and a companion document, **PREDICTIONS.md**, with all
104 matches and the full method.

Built from public raw data. No betting odds or published predictions are
used anywhere.

## Online (public site)

To publish this as a public, self-updating website on Vercel, follow
**DEPLOY.md**. Once live, the site sits at a `*.vercel.app` address, updates
itself every 30 minutes as results come in, and needs nothing run by hand.

## To use the dashboard locally

Double-click **Start World Cup Dashboard.command** in this folder.

That is the whole workflow: it updates the predictions with the latest
results, starts the dashboard and opens it in your browser. Keep the small
Terminal window it opens in the background; close it when you are done.
Click **Refresh predictions** on the page any time during a matchday.

Tip: drag "Start World Cup Dashboard.command" to your Dock or make an
alias on your Desktop for one-click access. If macOS asks the first time,
choose Open.

Manual alternative: in Terminal, `python3 serve.py` from this folder does
the same minus the automatic update on launch.

The refresh is incremental by design: the full historical model (the Elo
pass over 49,000 matches and the goal-model fit) was built once and saved
to data/model_state.json. A refresh only applies results the model has not
seen, then re-runs the tournament simulation, so it stays fast.

## To update from Terminal instead

- `python3 update.py` does the same fast refresh and rewrites both the
  dashboard data and PREDICTIONS.md.
- `python3 update.py full` is the heavy resync: re-downloads the full
  dataset and rebuilds the model from scratch (use occasionally, or if the
  state file is ever deleted; it recreates itself automatically).

Or open a Claude Code session in this folder and it will refresh
automatically at the start of the session.

## What the numbers mean

- The result call ("Mexico win 68%") is the probability of the match
  outcome. The likely score ("2-0, 14%") is the single most probable
  scoreline; even heavy favourites rarely exceed 15 to 20% on an exact
  score because goals spread across many scorelines.
- Knockout lines include the probability of advancing after extra time
  and penalties.
- Until the group stage ends, knockout pairings show the most frequent
  matchup across simulations. Once real pairings are set, refreshing
  replaces them with firm predictions.
- Once a match is played, the pre-match prediction is frozen and scored
  against the actual result, so the model keeps an honest record.

## How it works (short version)

1. **Team strength.** A weighted Elo rating over every senior
   international since 1900. Match importance sets the weight (World Cup
   finals highest, friendlies lowest), the 2022 World Cup gets a 1.5x
   boost, everything since the 2022 final gets 1.25x, recent friendlies
   are upgraded, wins move ratings more when the opponent is stronger,
   and the three hosts get home advantage in their own stadiums.
2. **Goals.** Expected goals for each side come from the rating gap via a
   Poisson model fitted on competitive internationals, corrected for the
   known bias on low-scoring draws. Score and result probabilities come
   from the resulting goal grid.
3. **Simulation.** The remaining tournament is simulated 10,000 times with
   FIFA tiebreakers, best-thirds allocation and the real bracket. Ratings
   update after every real match, and squad news (injuries, suspensions)
   applies as rating adjustments in data/adjustments.json.

**Validation.** Trained only on pre-2022 data, the engine called 53% of
Qatar 2022 results (random guessing gives 33%) with honest confidence
levels, and 9% of exact scorelines, in line with what public models and
bookmakers achieved at an unusually upset-heavy tournament.

## Files

| File | Purpose |
| - | - |
| Start World Cup Dashboard.command | Double-click launcher: update, serve, open browser |
| serve.py | Local server: dashboard plus the refresh endpoint |
| output/dashboard.html | The dashboard (regenerated each refresh) |
| PREDICTIONS.md | The full predictions document (regenerated each refresh) |
| update.py | One-command refresh (add `full` for a complete rebuild) |
| fetch_results.py | Downloads results, parses fixtures, scores and kickoff times |
| model.py | Elo engine and goal model |
| tournament.py | Simulator, incremental state and per-match predictions |
| report.py | Renders PREDICTIONS.md |
| dashboard.py | Renders output/dashboard.html |
| backtest.py | 2022 holdout validation |
| data/model_state.json | Cached ratings and parameters (the heavy build) |
| data/adjustments.json | Squad news adjustments (editable) |
| output/predictions.json | Prediction state, including frozen predictions |

## Known limits

- Third-place bracket routing approximates FIFA's combination table; the
  real bracket takes over once set.
- Injury adjustments are judgement-scaled from confirmed reports.
- Lineups, tactics and referees are outside the model. Penalties are
  close to a coin flip. Probabilities are estimates, not promises.
