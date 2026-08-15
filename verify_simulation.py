"""
Standalone verification script.

Run this file directly (see README instructions) to see the Monte Carlo
simulator run against the real 2025-26 schedule with a few test team
ratings, and print out results you can sanity-check by hand.

This file exists purely so you can run and see the simulation yourself,
independent of anything Claude reports -- no hidden setup, no other
files need editing.
"""

import sys
import os
import time

# Make sure Python can find our other modules regardless of where this
# script is run from.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "simulation"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "data"))

from teams import TEAM_LIST          # noqa: E402
from real_schedule import load_real_schedule  # noqa: E402
from simulator import run_monte_carlo  # noqa: E402


def main():
    print("=" * 60)
    print("NBA PROJECTOR - SIMULATION ENGINE VERIFICATION")
    print("=" * 60)

    real_schedule = load_real_schedule()
    print(f"\nLoaded real 2025-26 schedule: {len(real_schedule)} games")

    # These are FAKE test ratings, not real team strength.
    # We're only checking that the math behaves the way it should:
    #   - a much better team should win much more often
    #   - a much worse team should win much less often
    #   - a neutral (0.0) team should land close to a .500 record
    test_ratings = {t: 0.0 for t in TEAM_LIST}
    test_ratings["BOS"] = 8.0    # artificially strong
    test_ratings["WAS"] = -8.0   # artificially weak
    test_ratings["DEN"] = 4.0    # moderately strong
    test_ratings["UTA"] = -4.0   # moderately weak
    # LAL is left at 0.0 -- our "neutral" team to check against .500

    print("\nTest ratings assigned (everyone else left at 0.0 / neutral):")
    print("  BOS = +8.0 (should look like a very strong team)")
    print("  DEN = +4.0 (should look like a solidly good team)")
    print("  UTA = -4.0 (should look like a below-average team)")
    print("  WAS = -8.0 (should look like a very weak team)")
    print("  LAL =  0.0 (neutral -- should land close to a .500 record)")

    n_sims = 10000
    print(f"\nRunning {n_sims:,} full-season simulations... "
          f"(takes several seconds, this is normal)")

    start = time.time()
    summary, win_records = run_monte_carlo(
        test_ratings, schedule=real_schedule, n_sims=n_sims, seed=42
    )
    elapsed = time.time() - start

    print(f"Done in {elapsed:.1f} seconds.\n")

    print("-" * 60)
    print(f"{'Team':<6}{'Mean Wins':<12}{'Median':<10}{'10th %ile':<12}{'90th %ile':<12}{'Range'}")
    print("-" * 60)
    for team in ["BOS", "DEN", "LAL", "UTA", "WAS"]:
        s = summary[team]
        print(f"{team:<6}{s['mean_wins']:<12.1f}{s['median_wins']:<10}"
              f"{s['p10_wins']:<12}{s['p90_wins']:<12}"
              f"[{s['min_wins']}, {s['max_wins']}]")

    print("\n" + "=" * 60)
    print("WHAT TO CHECK (things that should be true if this is working):")
    print("=" * 60)
    games_per_team = len(real_schedule) * 2 / 30  # rough estimate
    print(f"1. BOS (+8) should have the HIGHEST mean wins of the five teams.")
    print(f"2. WAS (-8) should have the LOWEST mean wins of the five teams.")
    print(f"3. DEN (+4) should be higher than LAL, but lower than BOS.")
    print(f"4. UTA (-4) should be lower than LAL, but higher than WAS.")
    print(f"5. LAL (neutral) should sit close to HALF of the season's games")
    print(f"   per team (roughly {games_per_team/2:.0f} wins out of ~{games_per_team:.0f} games),")
    print(f"   since a rating of 0.0 means a perfectly average team.")
    print(f"6. Every team's [min, max] range should be fairly WIDE, not a")
    print(f"   single repeated number -- that confirms randomness/variance")
    print(f"   is actually happening across the {n_sims:,} simulations, not")
    print(f"   just running the same season over and over.")

    # Automated pass/fail so you don't have to eyeball everything by hand
    print("\n" + "=" * 60)
    print("AUTOMATED CHECKS:")
    print("=" * 60)
    checks = [
        ("BOS mean > DEN mean", summary["BOS"]["mean_wins"] > summary["DEN"]["mean_wins"]),
        ("DEN mean > LAL mean", summary["DEN"]["mean_wins"] > summary["LAL"]["mean_wins"]),
        ("LAL mean > UTA mean", summary["LAL"]["mean_wins"] > summary["UTA"]["mean_wins"]),
        ("UTA mean > WAS mean", summary["UTA"]["mean_wins"] > summary["WAS"]["mean_wins"]),
        ("LAL mean is close to half its games (+/- 3 wins)",
         abs(summary["LAL"]["mean_wins"] - games_per_team / 2) < 3),
        ("BOS shows real variance (max - min > 10 wins)",
         (summary["BOS"]["max_wins"] - summary["BOS"]["min_wins"]) > 10),
    ]
    all_passed = True
    for description, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status}] {description}")

    print()
    if all_passed:
        print("ALL CHECKS PASSED. The simulator is behaving correctly.")
    else:
        print("SOME CHECKS FAILED -- something is wrong, do not trust results yet.")


if __name__ == "__main__":
    main()
