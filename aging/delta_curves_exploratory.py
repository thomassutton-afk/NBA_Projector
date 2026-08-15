"""
Module 2 (Aging Curve) -- EXPLORATORY, not final curve-fitting.

Builds delta-method aging curves for the 8 core stat categories two
ways -- with no sample-size cutoff, and with a minimum-n cutoff per
age-transition bucket -- so we can see exactly what the cutoff changes
before deciding whether/where to use one.

METHOD (delta method, see chat writeup for the full explanation):
  1. For each player, find consecutive-age season pairs (age X this
     season, age X+1 next season, same player, no gap year).
  2. For each pair, compute delta = z_score(age X+1) - z_score(age X)
     for each of the 8 core stat categories (using the z-scores
     already computed in player_metrics.csv, i.e. era-normalized).
  3. Weight each delta by the average of the two seasons' minutes
     (a delta between two 3000-minute seasons is more reliable than one
     between two 50-minute seasons).
  4. Group by age-transition (e.g. "24->25") and take the
     minutes-weighted mean delta, plus n = number of player-transitions
     in that bucket.
  5. Reconstruct a relative curve by cumulatively summing the average
     deltas from a fixed starting age.

This script does NOT decide anything -- it's meant to show you the
raw age-transition table (deltas + sample sizes) and a chart comparing
the reconstructed curve with vs. without a minimum-n filter, so you can
see where the filter actually changes the shape before committing.

Scope note: uses the FULL 1950-2024 dataset for this exploration (not
yet restricted to the 1976/1980+ primary fitting window) -- so the
sample-size and shape questions can be seen across the whole history
first. The primary-window decision is separate and still to be made.

Run from your aging/ folder, after compute_metrics.py has produced
player_metrics.csv:

    python delta_curves_exploratory.py

Outputs:
    delta_table.csv          -- every age-transition x category, with
                                 weighted mean delta and sample size n
    delta_curves_compare.png -- chart: raw vs. min-n-filtered curves
                                 for 3 representative categories
                                 (PTS, TRB, AST), plus sample size shown
                                 underneath each
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS_PATH = os.path.join(HERE, "player_metrics.csv")
TABLE_OUT = os.path.join(HERE, "delta_table.csv")
CHART_OUT = os.path.join(HERE, "delta_curves_compare.png")

CORE_CATEGORIES = ["PTS_per36", "TRB_per36", "AST_per36", "STL_per36",
                    "BLK_per36", "TOV_per36", "PF_per36", "TS_pct"]

# The candidate minimum-n cutoff to compare against "no cutoff".
MIN_N_CUTOFF = 20

# Categories to actually chart (all 8 would be a lot to look at for a
# first pass -- these 3 map to the README's "scoring, rebounding,
# playmaking" example categories).
CHART_CATEGORIES = ["PTS_per36", "TRB_per36", "AST_per36"]

STARTING_AGE = 22  # curve reconstruction starts here (delta = 0 at this age)


def build_deltas(df):
    """Returns a long dataframe: one row per (player, age_from, age_to,
    category) with the delta and the weight (avg MP of the two seasons)."""
    z_cols = {cat: f"{cat}_z" for cat in CORE_CATEGORIES}
    needed = ["PlayerName", "SeasonStart", "Age", "MP"] + list(z_cols.values())
    d = df[needed].dropna(subset=["Age", "MP"]).copy()
    d = d.sort_values(["PlayerName", "SeasonStart"])

    rows = []
    for name, group in d.groupby("PlayerName"):
        group = group.reset_index(drop=True)
        for i in range(len(group) - 1):
            this_row = group.iloc[i]
            next_row = group.iloc[i + 1]
            # must be consecutive age AND consecutive season (no gap year)
            if next_row["Age"] != this_row["Age"] + 1:
                continue
            if next_row["SeasonStart"] != this_row["SeasonStart"] + 1:
                continue
            weight = (this_row["MP"] + next_row["MP"]) / 2
            for cat in CORE_CATEGORIES:
                z1 = this_row[z_cols[cat]]
                z2 = next_row[z_cols[cat]]
                if pd.isna(z1) or pd.isna(z2):
                    continue
                rows.append({
                    "age_from": int(this_row["Age"]),
                    "age_to": int(next_row["Age"]),
                    "category": cat,
                    "delta": z2 - z1,
                    "weight": weight,
                })
    return pd.DataFrame(rows)


def aggregate_by_transition(deltas):
    """Weighted mean delta + n per (age_from, category)."""
    def wmean(g):
        return np.average(g["delta"], weights=g["weight"])

    agg = deltas.groupby(["category", "age_from"]).apply(
        lambda g: pd.Series({
            "age_to": g["age_to"].iloc[0],
            "n": len(g),
            "weighted_mean_delta": wmean(g),
        })
    ).reset_index()
    return agg


def reconstruct_curve(agg_cat, min_n=None):
    """
    Given one category's age-transition table (sorted by age_from),
    cumulatively sum deltas starting from STARTING_AGE to build a
    relative curve. If min_n is set, transitions with n < min_n are
    excluded (curve just skips that step -- treated as no data rather
    than assumed zero).
    Returns a dict {age: cumulative_value}.
    """
    agg_cat = agg_cat.sort_values("age_from")
    if min_n is not None:
        agg_cat = agg_cat[agg_cat["n"] >= min_n]

    curve = {STARTING_AGE: 0.0}

    # walk upward from STARTING_AGE
    ages_up = sorted(a for a in agg_cat["age_from"].unique() if a >= STARTING_AGE)
    running = 0.0
    current_age = STARTING_AGE
    for age_from in ages_up:
        if age_from != current_age:
            break  # gap in transitions -- stop extending (no data to bridge it)
        row = agg_cat[agg_cat["age_from"] == age_from].iloc[0]
        running += row["weighted_mean_delta"]
        curve[int(row["age_to"])] = running
        current_age = int(row["age_to"])

    # walk downward from STARTING_AGE
    ages_down = sorted((a for a in agg_cat["age_from"].unique() if a < STARTING_AGE),
                        reverse=True)
    running = 0.0
    current_age = STARTING_AGE
    for age_from in ages_down:
        row = agg_cat[agg_cat["age_from"] == age_from].iloc[0]
        if row["age_to"] != current_age:
            break
        running -= row["weighted_mean_delta"]
        curve[int(age_from)] = running
        current_age = int(age_from)

    return curve


def main():
    if not os.path.exists(METRICS_PATH):
        raise FileNotFoundError(
            f"Expected player_metrics.csv in {HERE} -- run compute_metrics.py first."
        )

    df = pd.read_csv(METRICS_PATH)
    print(f"Loaded player_metrics.csv: {len(df)} rows")

    deltas = build_deltas(df)
    print(f"Built {len(deltas)} (player, age-transition, category) delta rows "
          f"from {deltas['category'].nunique()} categories")

    agg = aggregate_by_transition(deltas)
    agg.to_csv(TABLE_OUT, index=False)
    print(f"Wrote {TABLE_OUT}: {len(agg)} rows "
          f"(age-transition x category combinations)")

    # Print the sample-size picture for one representative category
    # so it's visible directly in the console, not just the CSV.
    print(f"\nSample sizes (n) for PTS_per36 by age-transition "
          f"(cutoff at n={MIN_N_CUTOFF} marked):")
    pts = agg[agg["category"] == "PTS_per36"].sort_values("age_from")
    for _, row in pts.iterrows():
        flag = "  <-- below cutoff" if row["n"] < MIN_N_CUTOFF else ""
        print(f"  {int(row['age_from']):3d} -> {int(row['age_to']):3d}   "
              f"n={int(row['n']):4d}   delta={row['weighted_mean_delta']:+.4f}{flag}")

    # Chart: raw vs. filtered curves for the 3 representative categories
    fig, axes = plt.subplots(len(CHART_CATEGORIES), 2, figsize=(13, 4 * len(CHART_CATEGORIES)),
                               gridspec_kw={"width_ratios": [3, 1]})

    for i, cat in enumerate(CHART_CATEGORIES):
        cat_agg = agg[agg["category"] == cat]
        curve_raw = reconstruct_curve(cat_agg, min_n=None)
        curve_filtered = reconstruct_curve(cat_agg, min_n=MIN_N_CUTOFF)

        ax_curve, ax_n = axes[i]

        ages_raw = sorted(curve_raw.keys())
        ax_curve.plot(ages_raw, [curve_raw[a] for a in ages_raw],
                       label="no cutoff (all data)", color="#7f8c8d", linewidth=1.5, alpha=0.8)

        ages_filt = sorted(curve_filtered.keys())
        ax_curve.plot(ages_filt, [curve_filtered[a] for a in ages_filt],
                       label=f"n >= {MIN_N_CUTOFF} only", color="#2980b9", linewidth=2)

        ax_curve.axhline(0, color="black", linewidth=0.5)
        ax_curve.set_title(f"{cat}: reconstructed curve (z-score units, "
                             f"relative to age {STARTING_AGE})")
        ax_curve.set_xlabel("Age")
        ax_curve.set_ylabel("Cumulative z-score delta")
        ax_curve.legend(fontsize=8)
        ax_curve.grid(alpha=0.3)

        cat_sorted = cat_agg.sort_values("age_from")
        ax_n.bar(cat_sorted["age_from"], cat_sorted["n"], color="#95a5a6")
        ax_n.axhline(MIN_N_CUTOFF, color="red", linestyle="--", linewidth=1)
        ax_n.set_title("Sample size (n) per transition")
        ax_n.set_xlabel("Age (from)")
        ax_n.set_ylabel("n")

    plt.tight_layout()
    plt.savefig(CHART_OUT, dpi=150)
    print(f"\nSaved {CHART_OUT}")


if __name__ == "__main__":
    main()
