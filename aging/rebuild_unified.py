"""
Module 2 (Aging Curve) -- Recovery step: rebuild unified_player_seasons.csv

WHY THIS SCRIPT EXISTS:
The unified_player_seasons.csv that was uploaded turned out to actually
be a copy of source_age_data_1947_2026.csv under the wrong filename
(same row count -- 28,811 -- same 3-column schema, same literal '?'
Balkan-name corruption documented in the README). The real unified
dataset -- the one with actual box score columns -- never made it into
this chat under any name.

This script does NOT change any methodology. It's the exact same final
step as build_unified() in build_player_dataset.py: concatenate
historical_clean.csv + recent_with_age.csv onto one common schema. It
just re-runs that one step using the two upstream files, which ARE
intact (confirmed: valid UTF-8, full box-score columns, expected row
counts).

Run this from the same folder as historical_clean.csv and
recent_with_age.csv (i.e. your aging/ folder):

    python rebuild_unified.py

Expected output: unified_player_seasons.csv with 22,092 data rows
(20,310 from historical_clean.csv + 1,782 from recent_with_age.csv)
and the full column set: SeasonStart, PlayerName, Age, G, MP, FG, FGA,
3P, 3PA, FT, FTA, ORB, DRB, TRB, AST, STL, BLK, TOV, PF, PTS, source.
"""

import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

COMMON_COLS = ["SeasonStart", "PlayerName", "Age", "G", "MP", "FG", "FGA",
               "3P", "3PA", "FT", "FTA", "ORB", "DRB", "TRB", "AST",
               "STL", "BLK", "TOV", "PF", "PTS"]


def main():
    hist_path = os.path.join(HERE, "historical_clean.csv")
    recent_path = os.path.join(HERE, "recent_with_age.csv")

    for p in (hist_path, recent_path):
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"Expected {os.path.basename(p)} in {HERE} -- "
                "run this script from your aging/ folder."
            )

    hist = pd.read_csv(hist_path)
    recent = pd.read_csv(recent_path)

    print(f"historical_clean.csv:  {len(hist)} rows")
    print(f"recent_with_age.csv:   {len(recent)} rows")
    print(f"expected unified rows: {len(hist) + len(recent)}")

    missing_hist_cols = set(COMMON_COLS) - set(hist.columns)
    missing_recent_cols = set(COMMON_COLS) - set(recent.columns)
    if missing_hist_cols:
        raise ValueError(f"historical_clean.csv missing columns: {missing_hist_cols}")
    if missing_recent_cols:
        raise ValueError(f"recent_with_age.csv missing columns: {missing_recent_cols}")

    hist_common = hist[COMMON_COLS].copy()
    hist_common["source"] = "historical_1950_2017"

    recent_common = recent[COMMON_COLS].copy()
    recent_common["source"] = "recent_2018_2024"

    unified = pd.concat([hist_common, recent_common], ignore_index=True)
    unified = unified.sort_values(["PlayerName", "SeasonStart"]).reset_index(drop=True)

    out_path = os.path.join(HERE, "unified_player_seasons.csv")
    unified.to_csv(out_path, index=False)

    print()
    print(f"Wrote unified_player_seasons.csv: {len(unified)} rows, "
          f"{unified['SeasonStart'].min():.0f}-{unified['SeasonStart'].max():.0f}")
    print(f"Age coverage: {unified['Age'].notna().mean() * 100:.2f}%")
    print(f"Columns ({len(unified.columns)}): {list(unified.columns)}")
    print()
    print("source breakdown:")
    print(unified["source"].value_counts())


if __name__ == "__main__":
    main()
