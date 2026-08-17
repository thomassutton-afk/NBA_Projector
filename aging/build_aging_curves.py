"""
build_aging_curves.py

THE actual curve-fitting step -- not exploratory. Builds one full aging
curve per stat category (age 18 through 45), using:
  - each category's own selected fitting-window start year (from
    category_fitting_windows_selected_smoothed.csv / the README table),
    running through the present (2024) -- NOT capped at 2004 like the
    window-selection scans were, since this is the real fit, not a
    comparison against a reference.
  - the same delta-method logic and n>=20 sample-size floor already
    locked in (delta_curves_exploratory.py).
  - for age-transition buckets below the n>=20 floor (mostly ages 18-19
    and late-30s/40s), the reliable "core" curve is extrapolated rather
    than fit directly on noisy tiny samples (per TJ's earlier call):
      * YOUNG tail (below the youngest reliable age): linear
        extrapolation, anchored on the average of the youngest 3
        reliable age-transition deltas (not just the single youngest
        one) with the slope estimated via a linear fit across those
        same points.
      * OLD tail (above the oldest reliable age): decay-toward-zero
        extrapolation -- starting from the average of the oldest 3
        reliable deltas (not just the single oldest one), each
        additional age-transition delta beyond that is the prior delta
        multiplied by DECAY_RATE (< 1), so the decline itself slows and
        asymptotes rather than continuing in a straight line forever.
        Averaging the last few reliable points (rather than anchoring on
        just one) matters because the single point right at the n>=20
        cutoff boundary is often the noisiest -- smallest sample,
        most survivorship-biased -- and a decay/extrapolation built off
        one noisy point can produce an unrepresentative tail (caught
        during review: PF_per36's single oldest reliable delta was
        nearly 2x any nearby value, producing a tail that kept climbing
        instead of leveling off).

Deltas are then converted into an actual curve via cumulative sum,
anchored at age 22 = 0.0 (same anchor used in the earlier exploratory
delta_curves_compare.png chart, kept for consistency).

Outputs:
  - aging_curves.csv: one row per (category, age) with the age-to-next-age
    delta, the cumulative z-score curve value, whether that row was
    extrapolated, and the underlying sample size (NaN if extrapolated).
  - aging_curves.png: one subplot per category, reliable core in solid
    line, extrapolated tails in dashed line, so it's visually obvious
    which parts of the curve are real data vs. extrapolation.

Run from aging/, after player_metrics.csv exists:
    python build_aging_curves.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---- Config ----
INPUT_FILE = "player_metrics.csv"
N_CUTOFF = 20           # sample-size floor per age-transition bucket (locked in step 2)
ANCHOR_AGE = 22          # cumulative curve is defined as 0.0 at this age
MIN_AGE = 18
MAX_AGE = 45
DECAY_RATE = 0.7         # old-tail extrapolation: each step beyond the reliable
                          # range shrinks the delta by this factor (asymptotes to 0)
FIT_END_YEAR = 2024       # curves use each category's selected start year through
                          # the present -- NOT capped at 2004 (that cap only applied
                          # to the earlier reference-vs-candidate comparison, not the
                          # final fit)

# Each category's selected fitting-window start year, from
# category_fitting_windows_selected_smoothed.csv (also documented in README.md).
CATEGORY_START_YEARS = {
    "TRB_per36": 1958,
    "PF_per36": 1958,
    "AST_per36": 1963,
    "TS_pct": 1961,
    "TOV_per36": 1970,
    "STL_per36": 1974,
    "BLK_per36": 1976,
    "PTS_per36": 1977,
}

OUTPUT_TABLE = "aging_curves.csv"
OUTPUT_CHART = "aging_curves.png"


def build_delta_curve(df, start_year, end_year, category_z_col, n_cutoff):
    """
    Age-transition deltas (mean z-score change, age -> age+1) for one
    category within [start_year, end_year], applying the n_cutoff
    sample-size floor. Returns two dicts: {age: mean_delta}, {age: count}
    -- both restricted to buckets meeting n_cutoff.
    """
    sub = df[(df["SeasonStart"] >= start_year) & (df["SeasonStart"] <= end_year)].copy()
    sub = sub.dropna(subset=[category_z_col, "Age", "player_id"])

    sub = sub.sort_values(["player_id", "Age"])
    sub["next_age"] = sub.groupby("player_id")["Age"].shift(-1)
    sub["next_z"] = sub.groupby("player_id")[category_z_col].shift(-1)

    transitions = sub[sub["next_age"] == sub["Age"] + 1].copy()
    transitions["delta"] = transitions["next_z"] - transitions[category_z_col]

    grouped = transitions.groupby("Age")["delta"].agg(["mean", "count"])
    reliable = grouped[grouped["count"] >= n_cutoff]

    return reliable["mean"].to_dict(), reliable["count"].to_dict()


def extrapolate_young_tail(deltas, min_reliable_age, target_min_age, anchor_n=3):
    """
    Linear extrapolation below min_reliable_age. To avoid anchoring on a
    single noisy edge value (small samples near the n_cutoff boundary are
    the noisiest), the extrapolation's starting point is the AVERAGE of
    the youngest `anchor_n` reliable deltas (not just the single youngest
    one), and the slope is estimated via a simple linear fit across those
    same anchor_n points. Returns a dict of newly-added {age: delta}
    entries (does not mutate the input).
    """
    reliable_ages = sorted(a for a in deltas if a >= min_reliable_age)
    anchor_ages = reliable_ages[:anchor_n]

    if len(anchor_ages) < 2:
        slope = 0.0
    else:
        # simple linear regression slope across the anchor points
        xs = np.array(anchor_ages, dtype=float)
        ys = np.array([deltas[a] for a in anchor_ages], dtype=float)
        slope = np.polyfit(xs, ys, 1)[0]

    base_age = anchor_ages[0]
    base_delta = float(np.mean([deltas[a] for a in anchor_ages]))
    base_center_age = float(np.mean(anchor_ages))  # anchor the fitted line at the group's center

    new_entries = {}
    age = base_age - 1
    while age >= target_min_age:
        new_entries[age] = base_delta + slope * (age - base_center_age)
        age -= 1
    return new_entries


def extrapolate_old_tail(deltas, max_reliable_age, target_max_age, decay_rate, anchor_n=3):
    """
    Decay-toward-zero extrapolation above max_reliable_age. To avoid
    anchoring on a single noisy edge value (the point right at the
    n_cutoff boundary is often the noisiest -- smallest sample, most
    survivorship-biased), the starting delta for the decay is the
    AVERAGE of the oldest `anchor_n` reliable deltas, not just the
    single oldest one. Each additional transition beyond that anchor
    decays by decay_rate per step, same as before. Returns a dict of
    newly-added {age: delta} entries.
    """
    reliable_ages = sorted(a for a in deltas if a <= max_reliable_age)
    anchor_ages = reliable_ages[-anchor_n:]
    anchor_delta = float(np.mean([deltas[a] for a in anchor_ages]))

    new_entries = {}
    age = max_reliable_age + 1
    current_delta = anchor_delta
    while age <= target_max_age:
        current_delta = current_delta * decay_rate
        new_entries[age] = current_delta
        age += 1
    return new_entries


def build_full_curve(df, category, start_year, end_year, n_cutoff,
                      min_age, max_age, anchor_age, decay_rate):
    """
    Builds the complete delta curve (reliable core + extrapolated tails)
    and the cumulative z-score curve for one category. Returns a list of
    row dicts: age, delta_to_next, cumulative_z, is_extrapolated, n.
    """
    z_col = f"{category}_z"
    reliable_deltas, reliable_counts = build_delta_curve(df, start_year, end_year, z_col, n_cutoff)

    if not reliable_deltas:
        return None  # no reliable data at all for this category/window

    reliable_ages = sorted(reliable_deltas.keys())
    min_reliable_age = reliable_ages[0]
    max_reliable_age = reliable_ages[-1]

    all_deltas = dict(reliable_deltas)  # age -> delta, transition age -> age+1

    if min_reliable_age > min_age:
        young_extrap = extrapolate_young_tail(all_deltas, min_reliable_age, min_age)
        all_deltas.update(young_extrap)

    if max_reliable_age < max_age:
        old_extrap = extrapolate_old_tail(all_deltas, max_reliable_age, max_age, decay_rate)
        all_deltas.update(old_extrap)

    # ---- Cumulative z-score curve, anchored at anchor_age = 0.0 ----
    cumulative = {anchor_age: 0.0}

    age = anchor_age + 1
    while age <= max_age:
        prev_transition_delta = all_deltas.get(age - 1)
        if prev_transition_delta is None:
            break  # shouldn't happen given full range built above
        cumulative[age] = cumulative[age - 1] + prev_transition_delta
        age += 1

    age = anchor_age - 1
    while age >= min_age:
        transition_delta = all_deltas.get(age)  # transition age -> age+1
        if transition_delta is None:
            break
        cumulative[age] = cumulative[age + 1] - transition_delta
        age -= 1

    # ---- Assemble output rows ----
    rows = []
    for age in sorted(cumulative.keys()):
        # a row's delta_to_next is the transition FROM this age (undefined at max_age)
        delta_to_next = all_deltas.get(age)
        is_extrapolated = age not in reliable_deltas if delta_to_next is not None else None
        n = reliable_counts.get(age, np.nan)
        rows.append({
            "category": category,
            "age": age,
            "delta_to_next": delta_to_next,
            "cumulative_z": cumulative[age],
            "is_extrapolated": is_extrapolated,
            "n": n,
            "fit_start_year": start_year,
            "fit_end_year": end_year,
        })
    return rows


def main():
    print(f"Loading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} rows\n")

    available_categories = []
    for cat in CATEGORY_START_YEARS:
        z_col = f"{cat}_z"
        if z_col in df.columns:
            available_categories.append(cat)
        else:
            print(f"  WARNING: '{z_col}' not found -- skipping {cat}.")

    all_rows = []
    for cat in available_categories:
        start_year = CATEGORY_START_YEARS[cat]
        print(f"{cat}: fitting {start_year}-{FIT_END_YEAR} "
              f"(decay_rate={DECAY_RATE} for old-tail extrapolation)")
        rows = build_full_curve(
            df, cat, start_year, FIT_END_YEAR, N_CUTOFF,
            MIN_AGE, MAX_AGE, ANCHOR_AGE, DECAY_RATE
        )
        if rows is None:
            print(f"  WARNING: no reliable data for {cat} in this window -- skipped\n")
            continue

        n_reliable = sum(1 for r in rows if r["is_extrapolated"] is False)
        n_extrap = sum(1 for r in rows if r["is_extrapolated"] is True)
        print(f"  {n_reliable} reliable age-transitions, {n_extrap} extrapolated\n")
        all_rows.extend(rows)

    results_df = pd.DataFrame(all_rows)
    results_df.to_csv(OUTPUT_TABLE, index=False)
    print(f"Wrote {OUTPUT_TABLE}: {len(results_df)} rows "
          f"({len(available_categories)} categories x ages {MIN_AGE}-{MAX_AGE})")

    # ---- Plot: one subplot per category, solid=reliable, dashed=extrapolated ----
    n_cats = len(available_categories)
    n_cols = 2
    n_rows = (n_cats + 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(13, 3.2 * n_rows))
    axes = axes.flatten()

    for i, cat in enumerate(available_categories):
        ax = axes[i]
        cat_data = results_df[results_df["category"] == cat].sort_values("age")

        reliable = cat_data[cat_data["is_extrapolated"] == False]
        extrap_young = cat_data[(cat_data["is_extrapolated"] == True) & (cat_data["age"] < reliable["age"].min())] if not reliable.empty else cat_data
        extrap_old = cat_data[(cat_data["is_extrapolated"] == True) & (cat_data["age"] > reliable["age"].max())] if not reliable.empty else pd.DataFrame()

        # connect segments so the line doesn't have gaps at the boundary
        if not reliable.empty:
            ax.plot(reliable["age"], reliable["cumulative_z"], color="tab:blue", linewidth=2, label="reliable (n>=20)")
        if not extrap_young.empty:
            boundary = pd.concat([extrap_young, reliable.head(1)]) if not reliable.empty else extrap_young
            ax.plot(boundary["age"], boundary["cumulative_z"], color="tab:blue", linewidth=1.5, linestyle="--")
        if not extrap_old.empty:
            boundary = pd.concat([reliable.tail(1), extrap_old]) if not reliable.empty else extrap_old
            ax.plot(boundary["age"], boundary["cumulative_z"], color="tab:blue", linewidth=1.5, linestyle="--",
                    label="extrapolated (n<20)")

        start_year = CATEGORY_START_YEARS[cat]
        ax.set_title(f"{cat} (fit: {start_year}-{FIT_END_YEAR})", fontsize=10)
        ax.axhline(0, color="black", linewidth=0.6)
        ax.axvline(ANCHOR_AGE, color="gray", linewidth=0.6, linestyle=":")
        ax.set_xlabel("Age")
        ax.set_ylabel("Cumulative z")
        ax.legend(fontsize=7, loc="lower left")
        ax.grid(alpha=0.25)

    # hide any unused subplot axes
    for j in range(n_cats, len(axes)):
        axes[j].axis("off")

    plt.tight_layout()
    plt.savefig(OUTPUT_CHART, dpi=150)
    print(f"Saved {OUTPUT_CHART}")


if __name__ == "__main__":
    main()
