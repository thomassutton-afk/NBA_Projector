"""
Standalone verification script #2: Pythagorean win check.

Run this file directly to see, for all 30 teams, using last season's
real points-for/points-against:
  1. Each team's point differential
  2. Their Pythagorean win expectation (the standard sabermetrics-style
     formula for converting point differential into expected wins)
  3. Our simulator's own mean win total when given that same point
     differential as its rating
  4. The difference between #2 and #3 (should be small if the
     simulator's core mechanics are sound)

This tests the simulation ENGINE, not a real projection -- it uses
already-known past point differential, not a projection of a future
season. It's a check that the machine computes correctly, not a
prediction of next year.
"""

import sys
import os
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "simulation"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "data"))

from teams import TEAM_LIST                    # noqa: E402
from real_schedule import load_real_schedule    # noqa: E402
from real_pfpa_2025_26 import PF_PA             # noqa: E402
from simulator import run_monte_carlo           # noqa: E402

PYTHAG_EXPONENT = 13.91


def main():
    print("=" * 70)
    print("PYTHAGOREAN WIN VALIDATION - ALL 30 TEAMS")
    print("=" * 70)

    assert set(PF_PA.keys()) == set(TEAM_LIST), "Team list mismatch"

    ratings = {t: PF_PA[t][0] - PF_PA[t][1] for t in TEAM_LIST}

    pythag_win_pct = {}
    for t in TEAM_LIST:
        pf, pa = PF_PA[t]
        pythag_win_pct[t] = (pf ** PYTHAG_EXPONENT) / (pf ** PYTHAG_EXPONENT + pa ** PYTHAG_EXPONENT)

    real_schedule = load_real_schedule()
    games_per_team = len(real_schedule) * 2 / 30
    print(f"\nUsing real 2025-26 schedule: {games_per_team:.0f} games per team")
    print("Running 10,000 simulations per team rating...")

    start = time.time()
    summary, _ = run_monte_carlo(ratings, schedule=real_schedule, n_sims=10000, seed=7)
    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f} seconds.\n")

    print(f"{'Team':<6}{'PF':<8}{'PA':<8}{'PtDiff':<9}{'Pythag Wins':<14}{'Sim Mean Wins':<16}{'Diff'}")
    print("-" * 70)

    rows = []
    for t in sorted(TEAM_LIST, key=lambda x: -ratings[x]):
        pf, pa = PF_PA[t]
        pythag_wins = pythag_win_pct[t] * games_per_team
        sim_mean = summary[t]["mean_wins"]
        diff = sim_mean - pythag_wins
        rows.append(diff)
        print(f"{t:<6}{pf:<8.1f}{pa:<8.1f}{ratings[t]:<9.1f}"
              f"{pythag_wins:<14.1f}{sim_mean:<16.1f}{diff:+.1f}")

    avg_abs_diff = sum(abs(d) for d in rows) / len(rows)
    max_abs_diff = max(abs(d) for d in rows)

    print("-" * 70)
    print(f"\nAverage absolute difference: {avg_abs_diff:.2f} wins")
    print(f"Maximum absolute difference: {max_abs_diff:.2f} wins")
    print()
    if avg_abs_diff < 1.5:
        print("VALIDATION PASSED: simulator closely matches the Pythagorean formula.")
    else:
        print("VALIDATION CONCERN: larger-than-expected gap from Pythagorean formula.")

    print("\nNote: this uses last season's REAL (already known) point")
    print("differential -- it validates the simulation engine's math, not")
    print("a projection of a future, uncertain season.")


if __name__ == "__main__":
    main()
