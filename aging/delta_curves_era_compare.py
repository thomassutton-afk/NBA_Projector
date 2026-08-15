"""
delta_curves_era_compare.py

Tests whether the primary curve-fitting window should start at 1976, 1980,
or somewhere else entirely -- empirically, rather than assuming a boundary.

Approach:
1. Build a "reference" delta curve per stat category using only the most
   recent N years of data (REFERENCE_START-2024), on the assumption that
   recent data is the least likely to be distorted by long-gone rule/pace
   eras.
2. For a range of candidate start years, build the same delta curve using
   data from [candidate_start_year, 2024].
3. Compute a single divergence score between each candidate curve and the
   reference curve (sum of squared differences across matched age-transition
   buckets, restricted to age brackets present in both).
4. Plot divergence (y) vs. candidate start year (x), one line per category.
   A flat line = start year doesn't matter much (older data isn't
   distorting the fit). A line that climbs past some year = that's roughly
   where the real boundary sits.

Uses the same delta-method logic and n>=20 sample-size cutoff already
locked in via delta_curves_exploratory.py -- this script doesn't touch or
overwrite delta_table.csv / delta_curves_compare.png, it writes its own
separate outputs.

Run from aging/, after player_metrics.csv exists:
    python delta_curves_era_compare.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---- Config ----
INPUT_FILE = "player_metrics.csv"
CATEGORIES = [
    "PTS_per36", "TRB_per36", "ORB_per36", "DRB_per36",
    "AST_per36", "STL_per36", "BLK_per36", "TOV_per36", "PF_per36", "TS_pct",
]
# NOTE: adjust CATEGORIES above if your z-score column names differ --
# this script expects a "<category>_z" column per entry (same convention
# as delta_curves_exploratory.py). If your 8 core categories use different
# base names, edit this list to match player_metrics.csv's actual columns.

N_CUTOFF = 20          # sample-size floor per age-transition bucket (locked in step 2)
REFERENCE_START = 2005 # reference window: 2005-2024
REFERENCE_END = 2024
CANDIDATE_START_YEARS = list(range(1950, 2001, 5))  # 1950, 1955, ..., 2000
CANDIDATE_END = 2024

OUTPUT_CHART = "era_divergence_by_start_year.png"
OUTPUT_TABLE = "era_divergence_table.csv"


def build_delta_curve(df, start_year, end_year, category_z_col, n_cutoff):
    """
    Given a player-season dataframe already restricted to [start_year, end_year],
    build age-transition deltas for one z-scored category, applying the
    n_cutoff sample-size floor. Returns a dict {age_from: delta} for buckets
    meeting the cutoff.
    """
    sub = df[(df["SeasonStart"] >= start_year) & (df["SeasonStart"] <= end_year)].copy()
    sub = sub.dropna(subset=[category_z_col, "Age", "player_id"])

    # pair each player's consecutive-season rows (age -> age+1)
    sub = sub.sort_values(["player_id", "Age"])
    sub["next_age"] = sub.groupby("player_id")["Age"].shift(-1)
    sub["next_z"] = sub.groupby("player_id")[category_z_col].shift(-1)

    transitions = sub[sub["next_age"] == sub["Age"] + 1].copy()
    transitions["delta"] = transitions["next_z"] - transitions[category_z_col]

    grouped = transitions.groupby("Age")["delta"].agg(["mean", "count"])
    grouped = grouped[grouped["count"] >= n_cutoff]

    return grouped["mean"].to_dict()


def divergence(curve_a, curve_b):
    """
    Sum of squared differences between two {age: delta} dicts, restricted
    to ages present in both. Returns (score, n_matched_ages).
    Returns (np.nan, 0) if no overlap.
    """
    shared_ages = set(curve_a.keys()) & set(curve_b.keys())
    if not shared_ages:
        return np.nan, 0
    sq_diffs = [(curve_a[age] - curve_b[age]) ** 2 for age in shared_ages]
    return sum(sq_diffs), len(shared_ages)


def main():
    print(f"Loading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} rows")

    available_categories = []
    for cat in CATEGORIES:
        z_col = f"{cat}_z"
        if z_col in df.columns:
            available_categories.append(cat)
        else:
            print(f"  WARNING: '{z_col}' not found in {INPUT_FILE} -- skipping {cat}. "
                  f"Check column naming and edit CATEGORIES list if needed.")

    if not available_categories:
        print("ERROR: none of the expected z-score columns were found. "
              "Check player_metrics.csv column names and edit the CATEGORIES "
              "list at the top of this script to match.")
        return

    results = []  # rows: category, start_year, divergence, n_matched_ages

    for cat in available_categories:
        z_col = f"{cat}_z"
        print(f"\n{cat}:")

        ref_curve = build_delta_curve(df, REFERENCE_START, REFERENCE_END, z_col, N_CUTOFF)
        print(f"  Reference window ({REFERENCE_START}-{REFERENCE_END}): "
              f"{len(ref_curve)} age-transition buckets with n>={N_CUTOFF}")

        for start_year in CANDIDATE_START_YEARS:
            cand_curve = build_delta_curve(df, start_year, CANDIDATE_END, z_col, N_CUTOFF)
            score, n_matched = divergence(cand_curve, ref_curve)
            results.append({
                "category": cat,
                "start_year": start_year,
                "divergence": score,
                "n_matched_ages": n_matched,
            })
            print(f"  start={start_year}: divergence={score:.4f} "
                  f"({n_matched} matched age buckets)" if not np.isnan(score)
                  else f"  start={start_year}: no overlapping age buckets -- skipped")

    results_df = pd.DataFrame(results)
    results_df.to_csv(OUTPUT_TABLE, index=False)
    print(f"\nWrote {OUTPUT_TABLE}: {len(results_df)} rows "
          f"({len(available_categories)} categories x {len(CANDIDATE_START_YEARS)} start years)")

    # ---- Plot: divergence vs. candidate start year, one line per category ----
    fig, ax = plt.subplots(figsize=(10, 6))
    for cat in available_categories:
        cat_data = results_df[results_df["category"] == cat].sort_values("start_year")
        ax.plot(cat_data["start_year"], cat_data["divergence"], marker="o", label=cat)

    ax.set_xlabel("Candidate window start year (window runs start_year-2024)")
    ax.set_ylabel(f"Divergence from reference curve ({REFERENCE_START}-{REFERENCE_END})")
    ax.set_title("Curve divergence vs. candidate fitting-window start year")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_CHART, dpi=150)
    print(f"Saved {OUTPUT_CHART}")


if __name__ == "__main__":
    main()
