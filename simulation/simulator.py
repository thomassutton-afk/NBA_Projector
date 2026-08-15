"""
Monte Carlo season simulator.

Method: direct point-differential simulation (chosen over Log5 because
NBA point differential carries real signal for tiebreakers/seeding, not
just win-loss).

For each game:
  expected_margin = (home_rating - away_rating) + home_court_advantage
  simulated_margin ~ Normal(expected_margin, sigma)
  home team wins if simulated_margin > 0

Placeholder parameters (flagged to revisit once we have our own data):
  SIGMA = 12.7            # backtested residual SD of real NBA prediction
                           # models (RAPTOR/Elo), see design notes
  HOME_COURT_ADV = 2.5    # placeholder; real models have historically
                           # overrated HCA, so keep modest until we
                           # calibrate from real results
"""

import random
from collections import defaultdict
from teams import TEAM_LIST
from schedule import build_schedule

SIGMA = 12.7
HOME_COURT_ADV = 2.5


def simulate_game(home_rating, away_rating, rng, sigma=SIGMA, home_adv=HOME_COURT_ADV):
    """
    Returns (home_margin) for a single simulated game.
    Positive means home team won by that many points.
    """
    expected_margin = (home_rating - away_rating) + home_adv
    return rng.gauss(expected_margin, sigma)


def simulate_season(team_ratings, schedule, rng, sigma=SIGMA, home_adv=HOME_COURT_ADV):
    """
    Simulates one full season given a schedule (list of (home, away) tuples)
    and a dict of {team: rating}. Returns a dict of team -> stats:
    {wins, losses, point_diff_total}
    """
    results = {t: {"wins": 0, "losses": 0, "point_diff_total": 0.0} for t in team_ratings}

    for home, away in schedule:
        margin = simulate_game(team_ratings[home], team_ratings[away], rng, sigma, home_adv)
        results[home]["point_diff_total"] += margin
        results[away]["point_diff_total"] -= margin
        if margin > 0:
            results[home]["wins"] += 1
            results[away]["losses"] += 1
        else:
            results[away]["wins"] += 1
            results[home]["losses"] += 1

    return results


def run_monte_carlo(team_ratings, schedule=None, n_sims=10000, seed=None,
                     sigma=SIGMA, home_adv=HOME_COURT_ADV):
    """
    Runs n_sims full-season simulations against a FIXED schedule -- only
    game outcomes vary between simulations, not who plays whom, which is
    what we want for a real season.

    If schedule is None, falls back to a freshly generated synthetic
    placeholder schedule (kept only for standalone testing of this
    module -- prefer passing a real schedule, e.g. from
    data.real_schedule.load_real_schedule()).

    Returns a dict per team with summary win-distribution stats, plus the
    raw win_records for building custom distributions/plots later.
    """
    rng = random.Random(seed)
    win_records = defaultdict(list)
    point_diff_records = defaultdict(list)

    if schedule is None:
        schedule = build_schedule(seed=seed)

    for i in range(n_sims):
        season_result = simulate_season(team_ratings, schedule, rng, sigma, home_adv)
        for team, stats in season_result.items():
            win_records[team].append(stats["wins"])
            point_diff_records[team].append(stats["point_diff_total"])

    summary = {}
    for team in team_ratings:
        wins = sorted(win_records[team])
        n = len(wins)
        summary[team] = {
            "mean_wins": sum(wins) / n,
            "median_wins": wins[n // 2],
            "p10_wins": wins[int(n * 0.10)],
            "p90_wins": wins[int(n * 0.90)],
            "min_wins": wins[0],
            "max_wins": wins[-1],
        }
    return summary, win_records


if __name__ == "__main__":
    # Sanity test with placeholder/dummy ratings -- NOT real team strength,
    # just here to verify the mechanics work before real ratings exist.
    dummy_ratings = {t: 0.0 for t in TEAM_LIST}
    # Give a few teams artificial strength to confirm the model responds correctly
    dummy_ratings["BOS"] = 8.0   # strong team
    dummy_ratings["WAS"] = -8.0  # weak team
    dummy_ratings["DEN"] = 5.0
    dummy_ratings["UTA"] = -5.0

    print("Running small test batch (500 sims) with dummy ratings...")
    summary, _ = run_monte_carlo(dummy_ratings, n_sims=500, seed=1)

    for team in ["BOS", "WAS", "DEN", "UTA", "LAL"]:
        s = summary[team]
        print(f"{team}: mean={s['mean_wins']:.1f} median={s['median_wins']} "
              f"p10={s['p10_wins']} p90={s['p90_wins']} "
              f"range=[{s['min_wins']},{s['max_wins']}]")

    # Basic sanity checks
    assert summary["BOS"]["mean_wins"] > summary["WAS"]["mean_wins"], \
        "Higher-rated team should have more expected wins"
    assert summary["DEN"]["mean_wins"] > summary["UTA"]["mean_wins"]
    assert 20 < summary["LAL"]["mean_wins"] < 62, \
        "Neutral-rated team should land near .500 (~41 wins)"
    print("\nSanity checks passed: ratings ordering and neutral-team baseline look correct.")
