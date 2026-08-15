"""
Module 2 (Aging Curve) -- Step 2: Metric computation.

Takes unified_player_seasons.csv (raw box score + minutes + age) and
computes, uniformly across the full 1950-2024 range from raw box score
data only (see README's "Raw box score as uniform foundation" design
decision -- deliberately NOT using the pre-built advanced-stat columns
for this, only for the cross-check at the end):

  1. Per-36 rate stats for every counting stat (PTS, TRB, ORB, DRB,
     AST, STL, BLK, TOV, PF, FG, FGA, 3P, 3PA, FT, FTA).
  2. True Shooting % = PTS / (2 * (FGA + 0.44 * FTA)).
  3. Era normalization for 8 core stat categories (PTS, TRB, AST, STL,
     BLK, TOV, PF, TS%): both a z-score (player value vs. that
     season's minutes-weighted mean/stdev) and a simpler ratio-to-
     league-average, computed per SeasonStart.
  4. A cross-check of our computed TS% and per-36 scoring against the
     pre-built PER / TS% / WS / BPM columns already present in
     historical_clean.csv, as a sanity check on our formulas (NOT an
     attempt to reproduce those metrics -- they use different
     weightings/inputs we don't have. The bar here is agreement/
     correlation, not an exact match, except for TS% itself, which
     uses the identical formula and SHOULD match almost exactly).

KNOWN, EXPECTED GAP -- 1950 and 1951 seasons (358 rows): the NBA did
not track individual player minutes at all until the 1951-52 season.
100% of 1950 and 1951 rows have MP = NaN in the source data itself --
confirmed, not a pipeline bug. These rows are kept in the output (all
other columns intact) but every per-36/TS%/z-score/ratio column is
NaN for them, since per-36 is undefined without minutes. This doesn't
affect the primary aging-curve fit, which starts at 1976/1980 per the
README, and the raw 1950-2024 file is kept only as a robustness check.

MINUTES WEIGHTING, NOT A MINUTES FLOOR: no player-seasons are dropped
for being low-minute. Every league mean/stdev used for era
normalization is minutes-weighted (a player who played 40 minutes for
the season pulls almost no weight on the league average; a player who
played 3000 does), so low-minute noise is naturally down-weighted
rather than needing an arbitrary cutoff. The MP column itself is
carried through unchanged, for use as an explicit weight later during
curve-fitting.

Run from your aging/ folder, after unified_player_seasons.csv exists:

    python compute_metrics.py

Outputs:
    player_metrics.csv -- unified_player_seasons.csv + all computed
                           columns described above.
Also prints a validation report to the console (no separate file --
short enough to read directly).
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
UNIFIED_PATH = os.path.join(HERE, "unified_player_seasons.csv")
HISTORICAL_PATH = os.path.join(HERE, "historical_clean.csv")
OUT_PATH = os.path.join(HERE, "player_metrics.csv")

# Counting stats we compute per-36 for. TS% is handled separately since
# it's a ratio, not a simple counting stat.
COUNTING_STATS = ["PTS", "TRB", "ORB", "DRB", "AST", "STL", "BLK", "TOV",
                   "PF", "FG", "FGA", "3P", "3PA", "FT", "FTA"]

# The subset we treat as "core stat categories" for era normalization
# (z-score + ratio-to-average). Matches the README's stated categories
# (scoring, rebounding, playmaking, etc.) rather than normalizing every
# single per-36 column, to avoid redundant/highly-correlated z-scores
# (e.g. FG/FGA/PTS all move together).
CORE_CATEGORIES = ["PTS_per36", "TRB_per36", "AST_per36", "STL_per36",
                    "BLK_per36", "TOV_per36", "PF_per36", "TS_pct"]


def compute_per36(df):
    for stat in COUNTING_STATS:
        df[f"{stat}_per36"] = np.where(
            df["MP"].notna() & (df["MP"] > 0),
            df[stat] / df["MP"] * 36,
            np.nan,
        )
    return df


def compute_ts_pct(df):
    denom = 2 * (df["FGA"] + 0.44 * df["FTA"])
    df["TS_pct"] = np.where(denom > 0, df["PTS"] / denom, np.nan)
    return df


def era_normalize(df):
    """
    For each core category, compute this season's minutes-weighted
    league mean/stdev, then each player-season's z-score and simple
    ratio-to-average against that season's distribution.

    Weighted mean/stdev use MP as the weight (a player's influence on
    "what's normal this season" scales with how much they played).
    """
    for col in CORE_CATEGORIES:
        mean_col = f"{col}_league_mean"
        std_col = f"{col}_league_std"
        z_col = f"{col}_z"
        ratio_col = f"{col}_ratio"

        df[mean_col] = np.nan
        df[std_col] = np.nan

        valid = df["MP"].notna() & (df["MP"] > 0) & df[col].notna()

        for season, idx in df[valid].groupby("SeasonStart").groups.items():
            sub = df.loc[idx]
            w = sub["MP"]
            x = sub[col]
            w_mean = np.average(x, weights=w)
            w_var = np.average((x - w_mean) ** 2, weights=w)
            w_std = np.sqrt(w_var)
            df.loc[idx, mean_col] = w_mean
            df.loc[idx, std_col] = w_std

        df[z_col] = np.where(
            valid & (df[std_col] > 0),
            (df[col] - df[mean_col]) / df[std_col],
            np.nan,
        )
        df[ratio_col] = np.where(
            valid & (df[mean_col] != 0),
            df[col] / df[mean_col],
            np.nan,
        )

    return df


def cross_check(df):
    """
    Sanity-check our computed metrics against the pre-built PER/TS%/WS/BPM
    columns in historical_clean.csv (1950-2017 only -- these columns
    don't exist for the 2018-2024 portion). Two checks:

      1. TS% direct comparison: our TS_pct should nearly EXACTLY match
         their 'TS%' column, since it's the identical formula. Large
         disagreement here would mean a real bug in our TS% formula or
         in FGA/FTA/PTS itself.
      2. Rank correlation (Spearman): our PTS_per36 and TS_pct vs. their
         PER/WS/BPM. These use different formulas/inputs, so we're NOT
         expecting a close numeric match -- only that players who rate
         well on our simple metrics also tend to rate well on theirs.

    IMPORTANT: rows with a (SeasonStart, PlayerName) key that appears
    more than once in historical_clean.csv are excluded from this
    comparison. Those are the ~23 documented real name-collision cases
    (two different actual players sharing a name in the same season --
    e.g. two different George Johnsons). Matching on name+season alone
    cross-joins their rows, comparing player A's computed stats against
    player B's pre-built stats -- a spurious mismatch that has nothing
    to do with whether our formulas are correct. Excluding them isn't
    hiding a problem; it's removing a known, already-documented
    matching limitation so this check measures what it's meant to
    measure.
    """
    if not os.path.exists(HISTORICAL_PATH):
        print("historical_clean.csv not found -- skipping cross-check.")
        return

    hist = pd.read_csv(HISTORICAL_PATH)

    hist["TS_pct_theirs"] = (
        hist["TS%"].astype(str).str.rstrip("%").astype(float) / 100
    )

    merge_cols = ["SeasonStart", "PlayerName"]
    check_cols = ["PER", "TS_pct_theirs", "WS", "BPM"]

    dupe_keys = hist.groupby(merge_cols).size()
    dupe_keys = dupe_keys[dupe_keys > 1].index
    hist_indexed = hist.set_index(merge_cols)
    hist_clean = hist_indexed[~hist_indexed.index.isin(dupe_keys)].reset_index()
    n_excluded = len(hist) - len(hist_clean)

    merged = df.merge(
        hist_clean[merge_cols + check_cols],
        on=merge_cols,
        how="inner",
    )

    print("=" * 70)
    print("CROSS-CHECK: computed metrics vs. pre-built advanced stats")
    print(f"(historical_clean.csv rows matched: {len(merged)} of "
          f"{len(hist_clean)} eligible historical rows -- {n_excluded} "
          f"rows excluded as known name-collision duplicates, see "
          f"docstring)")
    print("=" * 70)

    valid_ts = merged[["TS_pct", "TS_pct_theirs"]].dropna()
    diff = (valid_ts["TS_pct"] - valid_ts["TS_pct_theirs"]).abs()
    print(f"\n1. TS% direct comparison ({len(valid_ts)} rows compared):")
    print(f"   mean absolute difference: {diff.mean():.5f}")
    print(f"   max absolute difference:  {diff.max():.5f}")
    print(f"   rows differing by > 0.01: {(diff > 0.01).sum()} "
          f"({(diff > 0.01).mean() * 100:.3f}%)")
    if diff.mean() < 0.005:
        print("   -> PASS: near-exact agreement, formula confirmed correct.")
    else:
        print("   -> CONCERN: larger-than-expected disagreement, investigate.")

    print(f"\n2. Rank correlation (Spearman) vs. pre-built advanced stats:")
    for our_col in ["PTS_per36", "TS_pct"]:
        for their_col in ["PER", "WS", "BPM"]:
            sub = merged[[our_col, their_col]].dropna()
            if len(sub) < 30:
                continue
            corr = sub[our_col].corr(sub[their_col], method="spearman")
            print(f"   {our_col:12s} vs {their_col:4s}: "
                  f"Spearman r = {corr:+.3f}  (n={len(sub)})")


def main():
    if not os.path.exists(UNIFIED_PATH):
        raise FileNotFoundError(
            f"Expected unified_player_seasons.csv in {HERE} -- "
            "run rebuild_unified.py (and patch_pre1958_ages.py) first."
        )

    df = pd.read_csv(UNIFIED_PATH)
    print(f"Loaded unified_player_seasons.csv: {len(df)} rows")

    no_mp = df["MP"].isna()
    print(f"Rows with no MP data (1950/1951, no per-36 possible): "
          f"{no_mp.sum()}")
    assert set(df.loc[no_mp, "SeasonStart"].unique()) <= {1950, 1951}, (
        "Found MP-missing rows outside 1950/1951 -- this doesn't match "
        "the known/expected gap, investigate before proceeding."
    )

    df = compute_per36(df)
    df = compute_ts_pct(df)
    df = era_normalize(df)

    df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote player_metrics.csv: {len(df)} rows, "
          f"{len(df.columns)} columns")

    print()
    cross_check(df)


if __name__ == "__main__":
    main()
