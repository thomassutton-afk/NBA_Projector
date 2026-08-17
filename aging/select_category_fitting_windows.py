"""
select_category_fitting_windows.py

Builds on delta_curves_era_compare.py's fixed-window divergence approach,
but:
  1. Scans in 1-year steps (instead of 2) across full history, for a much
     smoother per-category divergence curve.
  2. Uses a 15-year fixed window length (instead of 10), per TJ's call.
  3. Automatically selects a "primary fitting window start year" PER
     CATEGORY, using one transparent, consistent rule -- not 8 separate
     eyeballed judgment calls.

Selection rule (UPDATED):
  Raw divergence scores bounce up and down noisily from one candidate start
  year to the next -- a single low point can be a real stable era, or just
  a lucky fluke sandwiched between worse years on either side. To avoid
  locking onto noise, divergence is first smoothed with a centered rolling
  average (SMOOTHING_WINDOW_YEARS) across neighboring candidate start
  years, and the selection rule below is applied to the SMOOTHED values,
  not the raw ones. Both raw and smoothed divergence are kept in the
  output CSV for comparison.

  For each category, find the best (lowest SMOOTHED divergence) candidate
  window. Then walk backward through history (earlier start years) and
  find the EARLIEST start year whose smoothed divergence is still within
  TOLERANCE_PCT of that best score. That's the category's selected start
  year: "how far back can we reach while staying close to modern behavior,
  based on a stable stretch rather than an isolated dip."

This does NOT overwrite any prior outputs (delta_table.csv,
delta_curves_compare.png, era_divergence_*.png/csv) -- it writes its own
files, listed below.

Run from aging/, after player_metrics.csv exists:
    python select_category_fitting_windows.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---- Config ----
INPUT_FILE = "player_metrics.csv"
CATEGORIES = [
    "PTS_per36", "TRB_per36",
    "AST_per36", "STL_per36", "BLK_per36", "TOV_per36", "PF_per36", "TS_pct",
]
# NOTE: ORB_per36 / DRB_per36 have raw per-36 columns in player_metrics.csv
# but no _z (z-score) columns -- compute_metrics.py only z-scored the 8
# core categories above (ORB/DRB folded into combined TRB_per36_z).

N_CUTOFF = 20            # sample-size floor per age-transition bucket (locked in step 2)
REFERENCE_START = 2005   # reference window: 2005-2024
REFERENCE_END = 2024

WINDOW_LENGTH_YEARS = 15  # fixed window length (per TJ's call)
WINDOW_STEP_YEARS = 1     # fine-grained: 1-year steps
TOLERANCE_PCT = 0.25      # a candidate is "close enough" to the best if its
                           # divergence <= best_divergence * (1 + TOLERANCE_PCT)
SMOOTHING_WINDOW_YEARS = 5  # centered rolling average applied to divergence
                             # before selection, to avoid locking onto an
                             # isolated noisy dip rather than a stable era

CANDIDATE_END_CAP = REFERENCE_START - 1  # 2004: last year with zero overlap vs. reference
EARLIEST_START_YEAR = 1955  # earliest data reasonably usable (per era_trends.py: MP data starts 1952)

# Candidate start years: every year such that [start, start+WINDOW_LENGTH_YEARS-1]
# fits before REFERENCE_START, going back to EARLIEST_START_YEAR.
LATEST_START = CANDIDATE_END_CAP - WINDOW_LENGTH_YEARS + 1  # e.g. 1990 for 15yr windows ending 2004
CANDIDATE_START_YEARS = list(range(EARLIEST_START_YEAR, LATEST_START + 1, WINDOW_STEP_YEARS))

OUTPUT_CHART = "category_divergence_fine_scan_smoothed.png"
OUTPUT_TABLE = "category_divergence_fine_scan_smoothed.csv"
OUTPUT_SELECTION = "category_fitting_windows_selected_smoothed.csv"


def build_delta_curve(df, start_year, end_year, category_z_col, n_cutoff):
    """
    Given a player-season dataframe, build age-transition deltas for one
    z-scored category within [start_year, end_year], applying the n_cutoff
    sample-size floor. Returns a dict {age_from: delta}.
    """
    sub = df[(df["SeasonStart"] >= start_year) & (df["SeasonStart"] <= end_year)].copy()
    sub = sub.dropna(subset=[category_z_col, "Age", "player_id"])

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


def select_start_year(cat_results_df, tolerance_pct, smoothing_window_years):
    """
    Given a per-category dataframe of (start_year, divergence), first
    applies a centered rolling average to smooth out noisy year-to-year
    fluctuations, then finds the best (lowest) SMOOTHED divergence score,
    then walks backward (earliest start years first) to find the earliest
    start year still within tolerance_pct of that best SMOOTHED score.

    Adds a 'divergence_smoothed' column to cat_results_df (in place) for
    reference/export.

    Returns (selected_start_year, selected_smoothed_divergence,
             best_smoothed_divergence).
    Returns (None, None, None) if no valid rows.
    """
    valid = cat_results_df.dropna(subset=["divergence"]).sort_values("start_year").copy()
    if valid.empty:
        cat_results_df["divergence_smoothed"] = np.nan
        return None, None, None

    valid["divergence_smoothed"] = (
        valid["divergence"]
        .rolling(window=smoothing_window_years, center=True, min_periods=1)
        .mean()
    )

    # write smoothed values back into the original (unfiltered) dataframe
    cat_results_df["divergence_smoothed"] = np.nan
    cat_results_df.loc[valid.index, "divergence_smoothed"] = valid["divergence_smoothed"]

    best_smoothed = valid["divergence_smoothed"].min()
    threshold = best_smoothed * (1 + tolerance_pct)

    within_tolerance = valid[valid["divergence_smoothed"] <= threshold]
    selected_row = within_tolerance.sort_values("start_year").iloc[0]

    return selected_row["start_year"], selected_row["divergence_smoothed"], best_smoothed


def main():
    print(f"Loading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} rows")
    print(f"Window length: {WINDOW_LENGTH_YEARS} years | step: {WINDOW_STEP_YEARS} year | "
          f"tolerance: {TOLERANCE_PCT*100:.0f}% | smoothing: {SMOOTHING_WINDOW_YEARS}yr rolling avg\n")

    available_categories = []
    for cat in CATEGORIES:
        z_col = f"{cat}_z"
        if z_col in df.columns:
            available_categories.append(cat)
        else:
            print(f"  WARNING: '{z_col}' not found -- skipping {cat}.")

    if not available_categories:
        print("ERROR: none of the expected z-score columns were found.")
        return

    all_results = []
    selections = []

    for cat in available_categories:
        z_col = f"{cat}_z"
        print(f"{cat}:")

        ref_curve = build_delta_curve(df, REFERENCE_START, REFERENCE_END, z_col, N_CUTOFF)

        cat_rows = []
        for start_year in CANDIDATE_START_YEARS:
            end_year = start_year + WINDOW_LENGTH_YEARS - 1
            if end_year > CANDIDATE_END_CAP:
                continue  # safety; shouldn't trigger given LATEST_START calc
            cand_curve = build_delta_curve(df, start_year, end_year, z_col, N_CUTOFF)
            score, n_matched = divergence(cand_curve, ref_curve)
            row = {
                "category": cat,
                "start_year": start_year,
                "end_year": end_year,
                "divergence": score,
                "n_matched_ages": n_matched,
            }
            cat_rows.append(row)
            all_results.append(row)

        cat_df = pd.DataFrame(cat_rows)
        sel_start, sel_div_smoothed, best_div_smoothed = select_start_year(
            cat_df, TOLERANCE_PCT, SMOOTHING_WINDOW_YEARS
        )
        # cat_df now has a divergence_smoothed column filled in place; pull
        # matching rows back into all_results for this category
        for row in cat_rows:
            match = cat_df[cat_df["start_year"] == row["start_year"]]
            if not match.empty:
                row["divergence_smoothed"] = match.iloc[0]["divergence_smoothed"]

        if sel_start is not None:
            sel_end = sel_start + WINDOW_LENGTH_YEARS - 1
            raw_at_sel = cat_df.loc[cat_df["start_year"] == sel_start, "divergence"].iloc[0]
            print(f"  Best (lowest SMOOTHED divergence, {SMOOTHING_WINDOW_YEARS}yr rolling avg): "
                  f"{best_div_smoothed:.4f}")
            print(f"  Selected start year (earliest within {TOLERANCE_PCT*100:.0f}% "
                  f"of best, on smoothed curve): {int(sel_start)}-{int(sel_end)} "
                  f"(smoothed={sel_div_smoothed:.4f}, raw={raw_at_sel:.4f})")
            print(f"  --> Recommended: fit {cat} using data from {int(sel_start)} onward\n")
            selections.append({
                "category": cat,
                "selected_start_year": int(sel_start),
                "selected_window_end_year": int(sel_end),
                "selected_divergence_smoothed": sel_div_smoothed,
                "selected_divergence_raw": raw_at_sel,
                "best_possible_divergence_smoothed": best_div_smoothed,
            })
        else:
            print(f"  No valid windows found for {cat}\n")
            selections.append({
                "category": cat,
                "selected_start_year": None,
                "selected_window_end_year": None,
                "selected_divergence_smoothed": None,
                "selected_divergence_raw": None,
                "best_possible_divergence_smoothed": None,
            })

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(OUTPUT_TABLE, index=False)
    print(f"Wrote {OUTPUT_TABLE}: {len(results_df)} rows")

    selections_df = pd.DataFrame(selections)
    selections_df.to_csv(OUTPUT_SELECTION, index=False)
    print(f"Wrote {OUTPUT_SELECTION}: {len(selections_df)} rows (one per category)")

    # ---- Plot: divergence vs. start year, one line per category, with
    # a marker at each category's selected start year ----
    fig, ax = plt.subplots(figsize=(11, 6.5))
    colors = plt.cm.tab10(np.linspace(0, 1, len(available_categories)))

    for cat, color in zip(available_categories, colors):
        cat_data = results_df[results_df["category"] == cat].sort_values("start_year")
        ax.plot(cat_data["start_year"], cat_data["divergence"],
                color=color, linewidth=0.8, alpha=0.35)
        ax.plot(cat_data["start_year"], cat_data["divergence_smoothed"], label=cat,
                color=color, linewidth=2.0)

        sel_row = selections_df[selections_df["category"] == cat].iloc[0]
        if pd.notna(sel_row["selected_start_year"]):
            ax.scatter([sel_row["selected_start_year"]], [sel_row["selected_divergence_smoothed"]],
                       color=color, s=130, zorder=5, edgecolor="black", linewidth=1.2)

    ax.set_xlabel(f"Candidate window start year (each window is {WINDOW_LENGTH_YEARS} years long)")
    ax.set_ylabel(f"Divergence from reference curve ({REFERENCE_START}-{REFERENCE_END})")
    ax.set_title(f"Per-category divergence scan -- faded=raw, bold={SMOOTHING_WINDOW_YEARS}yr "
                 f"smoothed (markers = selected start year, {TOLERANCE_PCT*100:.0f}% tolerance)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_CHART, dpi=150)
    print(f"Saved {OUTPUT_CHART}")


if __name__ == "__main__":
    main()
