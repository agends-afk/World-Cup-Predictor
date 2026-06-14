"""Rating engine and goal model for the World Cup predictor.

Two layers, both fitted from raw results only (no published predictions):

1. Weighted Elo ratings over all internationals since 1900. Match importance
   sets the K factor, recent eras get multipliers per the project brief, and
   opposition strength is inherent in the rating exchange.
2. A Poisson goal model: each side's expected goals is exp(alpha + beta * x)
   where x is the rating difference (including home advantage) divided by 400.
   Alpha and beta are fitted by maximum likelihood on competitive
   internationals, the intercept is re-centred on World Cup finals scoring
   levels, and a Dixon-Coles adjustment corrects low-score draw frequencies.
"""

import csv
import math
from datetime import date as date_cls

HOME_ADV = 100.0          # Elo points for playing at home (non-neutral venue)
START_RATING = 1500.0
GRID_MAX = 10             # score grid runs 0..GRID_MAX goals per side
LAMBDA_MIN, LAMBDA_MAX = 0.15, 4.2

CONTINENTAL_FINALS = {
    "UEFA Euro", "Copa América", "African Cup of Nations", "AFC Asian Cup",
    "Gold Cup", "CONCACAF Championship", "Oceania Nations Cup",
    "Confederations Cup",
}
NATIONS_LEAGUES = {"UEFA Nations League", "CONCACAF Nations League"}

WC2022_START, WC2022_END = "2022-11-20", "2022-12-18"


def base_k(tournament, match_date, now_iso):
    """Importance-based K factor, with the recent-friendly upgrade."""
    if tournament == "FIFA World Cup":
        return 60.0
    if tournament in CONTINENTAL_FINALS:
        return 50.0
    if "qualification" in tournament or tournament in NATIONS_LEAGUES:
        return 40.0
    if tournament == "Friendly":
        # Friendlies within a year of the run date carry more signal.
        if _days_between(match_date, now_iso) <= 365:
            return 30.0
        return 20.0
    return 30.0


def era_multiplier(match_date, tournament):
    """Recency weighting per the brief: 2022 World Cup boosted, post-2022 boosted."""
    if WC2022_START <= match_date <= WC2022_END and tournament == "FIFA World Cup":
        return 1.5
    if match_date > WC2022_END:
        return 1.25
    return 1.0


def mov_multiplier(diff):
    """Margin of victory multiplier (standard world football Elo form)."""
    d = abs(diff)
    if d <= 1:
        return 1.0
    if d == 2:
        return 1.5
    return (11.0 + d) / 8.0


def _days_between(d1_iso, d2_iso):
    y1, m1, dd1 = (int(p) for p in d1_iso.split("-"))
    y2, m2, dd2 = (int(p) for p in d2_iso.split("-"))
    return abs((date_cls(y2, m2, dd2) - date_cls(y1, m1, dd1)).days)


def load_results(paths):
    """Load and merge result CSVs (dataset schema), sorted by date.

    Rows with missing scores (future fixtures) are skipped. Later files
    override earlier ones for the same (date, home, away) key.
    """
    merged = {}
    for path in paths:
        try:
            f = open(path, encoding="utf-8")
        except FileNotFoundError:
            continue
        with f:
            for r in csv.DictReader(f):
                hs, aw = r.get("home_score", "NA"), r.get("away_score", "NA")
                if hs in ("NA", "", None) or aw in ("NA", "", None):
                    continue
                try:
                    home_score, away_score = int(float(hs)), int(float(aw))
                except ValueError:
                    continue   # tolerate upstream typos; one lost row is harmless
                key = (r["date"], r["home_team"], r["away_team"])
                merged[key] = {
                    "date": r["date"],
                    "home_team": r["home_team"],
                    "away_team": r["away_team"],
                    "home_score": home_score,
                    "away_score": away_score,
                    "tournament": r["tournament"],
                    "neutral": str(r.get("neutral", "TRUE")).upper() == "TRUE",
                }
    # Order-insensitive dedupe: if the dataset later adds a match the live
    # scraper already supplied with teams swapped, keep the later entry.
    by_pair = {}
    for key in sorted(merged):
        r = merged[key]
        by_pair[(r["date"], frozenset((r["home_team"], r["away_team"])))] = r
    rows = sorted(by_pair.values(), key=lambda r: r["date"])
    return [r for r in rows if r["date"] >= "1900-01-01"]


def run_elo(matches, now_iso, snapshot_dates=(), collect_start="2010-01-01",
            sample_max_date=None):
    """Single chronological pass: ratings, goal-model samples, snapshots.

    Snapshots capture the rating table just before the first match on or
    after each snapshot date (so a snapshot at a tournament's start date
    excludes the tournament itself).
    """
    ratings = {}
    samples = []
    snapshots = {}
    pending = sorted(snapshot_dates)

    for m in matches:
        while pending and m["date"] >= pending[0]:
            snapshots[pending[0]] = dict(ratings)
            pending.pop(0)

        ra = ratings.get(m["home_team"], START_RATING)
        rb = ratings.get(m["away_team"], START_RATING)
        adv = 0.0 if m["neutral"] else HOME_ADV
        k = base_k(m["tournament"], m["date"], now_iso)

        # Collect goal-model training samples (competitive matches only).
        if m["date"] >= collect_start and k >= 40.0:
            if sample_max_date is None or m["date"] < sample_max_date:
                x = (ra + adv - rb) / 400.0
                if abs(x) <= 2.0:
                    years_ago = _days_between(m["date"], now_iso) / 365.25
                    w = math.exp(-years_ago / 8.0)
                    if m["tournament"] == "FIFA World Cup":
                        w *= 3.0
                    elif m["tournament"] in CONTINENTAL_FINALS:
                        w *= 2.0
                    samples.append({
                        "date": m["date"], "tournament": m["tournament"],
                        "x": x, "gh": m["home_score"], "ga": m["away_score"],
                        "w": w,
                    })

        expected = 1.0 / (1.0 + 10.0 ** (-(ra + adv - rb) / 400.0))
        if m["home_score"] > m["away_score"]:
            score = 1.0
        elif m["home_score"] < m["away_score"]:
            score = 0.0
        else:
            score = 0.5
        g = mov_multiplier(m["home_score"] - m["away_score"])
        delta = k * era_multiplier(m["date"], m["tournament"]) * g * (score - expected)
        ratings[m["home_team"]] = ra + delta
        ratings[m["away_team"]] = rb - delta

    for d in pending:
        snapshots[d] = dict(ratings)
    return ratings, samples, snapshots


def fit_goal_model(samples, max_date=None):
    """Poisson regression of goals on rating difference, by Newton MLE."""
    obs = []
    for s in samples:
        if max_date is not None and s["date"] >= max_date:
            continue
        obs.append((s["x"], s["gh"], s["w"]))
        obs.append((-s["x"], s["ga"], s["w"]))
    alpha, beta = math.log(1.3), 1.0
    for _ in range(25):
        ga = gb = 0.0
        haa = hab = hbb = 0.0
        for x, y, w in obs:
            lam = math.exp(alpha + beta * x)
            ga += w * (y - lam)
            gb += w * x * (y - lam)
            haa += w * lam
            hab += w * lam * x
            hbb += w * lam * x * x
        det = haa * hbb - hab * hab
        if det <= 1e-9:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        alpha += da
        beta += db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return alpha, beta


def wc_intercept(samples, alpha, beta, max_date=None):
    """Re-centre the intercept on World Cup finals scoring levels."""
    sw = sy = sl = 0.0
    for s in samples:
        if s["tournament"] != "FIFA World Cup":
            continue
        if max_date is not None and s["date"] >= max_date:
            continue
        for x, y in ((s["x"], s["gh"]), (-s["x"], s["ga"])):
            sw += s["w"]
            sy += s["w"] * y
            sl += s["w"] * math.exp(alpha + beta * x)
    if sw <= 0 or sy <= 0 or sl <= 0:
        return alpha
    return alpha + math.log((sy / sw) / (sl / sw))


def _poisson_row(lam, n):
    row = [math.exp(-lam)]
    for i in range(1, n + 1):
        row.append(row[-1] * lam / i)
    return row


def score_grid(lam_a, lam_b, rho, max_goals=GRID_MAX):
    """Joint scoreline probabilities with the Dixon-Coles tau adjustment."""
    pa = _poisson_row(lam_a, max_goals)
    pb = _poisson_row(lam_b, max_goals)
    grid = [[pa[i] * pb[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    grid[0][0] *= max(0.0, 1.0 - lam_a * lam_b * rho)
    grid[0][1] *= max(0.0, 1.0 + lam_a * rho)
    grid[1][0] *= max(0.0, 1.0 + lam_b * rho)
    grid[1][1] *= max(0.0, 1.0 - rho)
    total = sum(sum(r) for r in grid)
    return [[p / total for p in row] for row in grid]


def grid_outcomes(grid):
    pw = pd = pl = 0.0
    n = len(grid)
    for i in range(n):
        for j in range(n):
            if i > j:
                pw += grid[i][j]
            elif i == j:
                pd += grid[i][j]
            else:
                pl += grid[i][j]
    return pw, pd, pl


def calibrate_rho(samples, alpha_wc, beta, max_date=None):
    """Pick rho so the model's average draw probability matches the
    empirical draw rate on finals-level matches."""
    finals = [s for s in samples
              if (s["tournament"] == "FIFA World Cup" or s["tournament"] in CONTINENTAL_FINALS)
              and (max_date is None or s["date"] < max_date)]
    if not finals:
        return -0.05
    actual = sum(1.0 for s in finals if s["gh"] == s["ga"]) / len(finals)
    best_rho, best_gap = 0.0, 1e9
    rho = -0.20
    while rho <= 0.051:
        tot = 0.0
        for s in finals:
            la = _clamp(math.exp(alpha_wc + beta * s["x"]))
            lb = _clamp(math.exp(alpha_wc - beta * s["x"]))
            _, pd, _ = grid_outcomes(score_grid(la, lb, rho))
            tot += pd
        gap = abs(tot / len(finals) - actual)
        if gap < best_gap:
            best_gap, best_rho = gap, rho
        rho += 0.01
    return best_rho


def _clamp(lam):
    return max(LAMBDA_MIN, min(LAMBDA_MAX, lam))


def predict_match(ra, rb, adv_a, adv_b, params, knockout=False):
    """Full probabilistic prediction for one match.

    Returns 90-minute win/draw/loss probabilities, the most likely
    scorelines, and (for knockouts) the probability of advancing after
    extra time and penalties.
    """
    alpha_wc, beta, rho = params["alpha_wc"], params["beta"], params["rho"]
    x = (ra + adv_a - rb - adv_b) / 400.0
    lam_a = _clamp(math.exp(alpha_wc + beta * x))
    lam_b = _clamp(math.exp(alpha_wc - beta * x))
    grid = score_grid(lam_a, lam_b, rho)
    pw, pd, pl = grid_outcomes(grid)

    cells = []
    n = len(grid)
    for i in range(n):
        for j in range(n):
            cells.append((grid[i][j], i, j))
    cells.sort(reverse=True)
    top = [{"score": f"{i}-{j}", "p": round(p, 4)} for p, i, j in cells[:5]]

    # Most likely scoreline within each outcome class. The overall modal is
    # often a draw (1-1) even when a win is favoured, so the display uses the
    # scoreline that matches the predicted result instead.
    by_outcome = {}
    for p, i, j in cells:
        cls = "team1" if i > j else ("team2" if i < j else "draw")
        if cls not in by_outcome:
            by_outcome[cls] = {"score": f"{i}-{j}", "p": round(p, 4)}
        if len(by_outcome) == 3:
            break

    out = {
        "lam_a": round(lam_a, 3), "lam_b": round(lam_b, 3),
        "p_win": round(pw, 4), "p_draw": round(pd, 4), "p_loss": round(pl, 4),
        "top_scores": top, "outcome_scores": by_outcome,
        "modal_score": top[0]["score"], "modal_p": top[0]["p"],
    }
    if knockout:
        et = score_grid(lam_a * 0.28, lam_b * 0.28, rho, max_goals=5)
        ew, ed, el = grid_outcomes(et)
        pen_a = 1.0 / (1.0 + 10.0 ** (-(ra + adv_a - rb - adv_b) / 1200.0))
        out["p_advance"] = round(pw + pd * (ew + ed * pen_a), 4)
        out["p_et_win"] = round(pd * ew, 4)
        out["p_pens"] = round(pd * ed, 4)
        out["pen_edge"] = round(pen_a, 3)
    return out


def sample_score(grid, rng):
    """Draw one scoreline from a grid (for simulation)."""
    r = rng.random()
    acc = 0.0
    n = len(grid)
    for i in range(n):
        for j in range(n):
            acc += grid[i][j]
            if r <= acc:
                return i, j
    return n - 1, n - 1
