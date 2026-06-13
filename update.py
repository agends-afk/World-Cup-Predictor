"""One-command refresh: fetch latest data, re-rate, re-predict, rebuild
the dashboard.

Run: python3 update.py [sim_count]
"""

import subprocess
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def run(script, args=(), optional=False):
    cmd = [sys.executable, os.path.join(BASE, script), *args]
    print(f"\n=== {script} {' '.join(args)} ===")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        if optional:
            print(f"{script} failed (exit {r.returncode}); continuing without it.")
            return
        print(f"{script} failed (exit {r.returncode}); stopping.")
        sys.exit(r.returncode)


def have(name):
    return os.path.exists(os.path.join(BASE, "data", name))


def main():
    args = sys.argv[1:]
    full = "full" in args
    sims = [a for a in args if a.isdigit()]
    # Self-heal: a fast run needs the cached model state. If it is missing
    # (e.g. a fresh clone without it), force a full rebuild so we never
    # produce ratings from an incomplete history.
    if not have("model_state.json"):
        if not full:
            print("No cached model state found; doing a full rebuild this run.")
        full = True

    # EA player ratings are a STATIC committed snapshot (they barely move and
    # the pull is slow). Never fetched on routine or full runs; only self-heal
    # if the committed file is missing. Refresh by hand with fetch_ratings.py.
    if not have("ea_ratings.json"):
        run("fetch_ratings.py", optional=True)
    # The 26-man squads are fixed for the tournament; refresh on a full run or
    # if missing, then reuse the committed file.
    if full or not have("squads.json"):
        run("fetch_squads.py", optional=True)

    # Fast (default): live scores only, cached ratings, new results applied
    # incrementally. Full: re-download the dataset and rebuild the model.
    run("fetch_results.py", [] if full else ["fast"])
    # Lineups change match to match, so fetch them every refresh.
    run("fetch_lineups.py", optional=True)
    run("tournament.py", (["full"] if full else []) + sims)
    run("report.py")
    run("dashboard.py")
    print("\nRefresh complete. PREDICTIONS.md and output/dashboard.html updated.")


if __name__ == "__main__":
    main()
