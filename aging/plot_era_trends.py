"""
Module 2 (Aging Curve) -- Quick sanity-check visualization, NOT part of
curve-fitting itself. Plots league-average (minutes-weighted) TS% and
PTS/36 by season, so era trends are visible before anything gets fit.

Also marks the three candidate era-break years (2000, 2010, 2015) the
README flags for empirical testing later -- purely as a visual
reference here, not a statistical test of where the real break is.

Run from your aging/ folder, after compute_metrics.py has produced
player_metrics.csv:

    python plot_era_trends.py

Outputs:
    era_trends.png -- saved to this script's directory
"""

import os
import pandas as pd
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS_PATH = os.path.join(HERE, "player_metrics.csv")
OUT_PATH = os.path.join(HERE, "era_trends.png")

CANDIDATE_ERA_BREAKS = [2000, 2010, 2015]


def main():
    if not os.path.exists(METRICS_PATH):
        raise FileNotFoundError(
            f"Expected player_metrics.csv in {HERE} -- run compute_metrics.py first."
        )

    df = pd.read_csv(METRICS_PATH)

    # The league_mean columns already carry one repeated value per season
    # (computed in compute_metrics.py) -- just take one row per season.
    by_season = (
        df.dropna(subset=["PTS_per36_league_mean", "TS_pct_league_mean"])
        .drop_duplicates("SeasonStart")
        .sort_values("SeasonStart")
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    ax1.plot(by_season["SeasonStart"], by_season["PTS_per36_league_mean"],
              color="#c0392b", linewidth=1.8)
    ax1.set_ylabel("League avg PTS / 36 min")
    ax1.set_title("League-average scoring rate by season (minutes-weighted)")
    ax1.grid(alpha=0.3)

    ax2.plot(by_season["SeasonStart"], by_season["TS_pct_league_mean"],
              color="#2980b9", linewidth=1.8)
    ax2.set_ylabel("League avg True Shooting %")
    ax2.set_xlabel("Season (SeasonStart year)")
    ax2.set_title("League-average shooting efficiency by season (minutes-weighted)")
    ax2.grid(alpha=0.3)

    for ax in (ax1, ax2):
        for year in CANDIDATE_ERA_BREAKS:
            ax.axvline(year, color="gray", linestyle="--", alpha=0.5, linewidth=1)
        ax.axvline(1976, color="green", linestyle=":", alpha=0.6, linewidth=1)

    ax1.text(1976, ax1.get_ylim()[1] * 0.98, " 1976 fit start",
              color="green", fontsize=8, va="top")
    for year in CANDIDATE_ERA_BREAKS:
        ax2.text(year, ax2.get_ylim()[0], f" {year}", color="gray",
                  fontsize=8, va="bottom")

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=150)
    print(f"Saved {OUT_PATH}")
    print(f"\nSeasons plotted: {by_season['SeasonStart'].min():.0f}-"
          f"{by_season['SeasonStart'].max():.0f} "
          f"({len(by_season)} seasons; 1950/1951 excluded, no MP data)")


if __name__ == "__main__":
    main()
