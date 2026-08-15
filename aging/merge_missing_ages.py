"""
Module 2 (Aging Curve) -- Step 1b: fold in externally-sourced birthdates
for the players build_player_dataset.py couldn't assign an age to
(true 2017-18+ debuts -- see missing_age_players.csv).

WHAT THIS SCRIPT NEEDS FROM YOU:
    A CSV named "recovered_birthdates.csv" in this same folder, with
    exactly two columns:

        personId,birth_date
        1628369,1998-03-03
        203468,1991-09-19
        ...

    personId must match the personId column in missing_age_players.csv
    (these are the NBA's own stable player IDs -- e.g. Jayson Tatum's
    personId 1628369 is also his nba.com/stats/player/1628369 ID, so
    you can use that page, Basketball-Reference, or any source you like
    as long as you key it back to this same personId).

    birth_date should be an ISO date (YYYY-MM-DD).

    You don't need every one of the 752 players in missing_age_players.csv
    -- partial coverage is fine, this script will just recover whichever
    ones you provide and leave the rest documented as a residual gap.

Run directly:
    python merge_missing_ages.py

This will:
  1. Compute each covered player's age per season, using the same age
     convention as the historical file (age as of Feb 1 of that season
     -- e.g. the 2017-18 season's age is age as of Feb 1, 2018).
  2. Add those rows to recent_with_age.csv.
  3. Rebuild unified_player_seasons.csv with the expanded data.
  4. Print an updated minutes-retention summary.
"""

import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RECOVERED_PATH = os.path.join(HERE, "recovered_birthdates.csv")


def main():
    if not os.path.exists(RECOVERED_PATH):
        print(f"No recovered_birthdates.csv found in {HERE}.")
        print("See this script's docstring for the exact format needed.")
        return

    recovered = pd.read_csv(RECOVERED_PATH)
    assert {"personId", "birth_date"}.issubset(recovered.columns), \
        "recovered_birthdates.csv must have columns: personId, birth_date"
    recovered["birth_date"] = pd.to_datetime(recovered["birth_date"])

    recent_all = pd.read_csv(os.path.join(HERE, "recent_aggregated.csv"))
    recent_with_age = pd.read_csv(os.path.join(HERE, "recent_with_age.csv"))
    hist = pd.read_csv(os.path.join(HERE, "historical_clean.csv"))

    # Only pull rows for personIds we didn't already have an age for
    already_covered_ids = set(recent_with_age.get("personId", []))
    newly_covered = recent_all[
        recent_all["personId"].isin(recovered["personId"])
        & ~recent_all["personId"].isin(already_covered_ids)
    ].copy()

    newly_covered = newly_covered.merge(recovered, on="personId", how="left")

    # Age as of Feb 1 of the season (SeasonStart label = the season's ending year)
    ref_date = pd.to_datetime(newly_covered["SeasonStart"].astype(int).astype(str) + "-02-01")
    newly_covered["Age"] = ((ref_date - newly_covered["birth_date"]).dt.days / 365.25).apply(int)
    newly_covered = newly_covered.drop(columns=["birth_date"])

    updated_recent = pd.concat([recent_with_age, newly_covered], ignore_index=True)
    updated_recent.to_csv(os.path.join(HERE, "recent_with_age.csv"), index=False)

    total_mp = recent_all["MP"].sum()
    kept_mp = updated_recent["MP"].sum()
    print(f"Recovered {len(newly_covered)} additional player-seasons "
          f"({newly_covered['MP'].sum():,.0f} minutes)")
    print(f"New total coverage: {kept_mp/total_mp*100:.1f}% of 2018-2024 minutes "
          f"(was {(kept_mp - newly_covered['MP'].sum())/total_mp*100:.1f}%)")

    # Rebuild the unified dataset
    common_cols = ["SeasonStart", "PlayerName", "Age", "G", "MP", "FG", "FGA",
                    "3P", "3PA", "FT", "FTA", "ORB", "DRB", "TRB", "AST",
                    "STL", "BLK", "TOV", "PF", "PTS"]
    hist_common = hist[common_cols].copy()
    hist_common["source"] = "historical_1950_2017"
    recent_common = updated_recent[common_cols].copy()
    recent_common["source"] = "recent_2018_2024"
    unified = pd.concat([hist_common, recent_common], ignore_index=True)
    unified = unified.sort_values(["PlayerName", "SeasonStart"]).reset_index(drop=True)
    unified.to_csv(os.path.join(HERE, "unified_player_seasons.csv"), index=False)
    print(f"unified_player_seasons.csv rebuilt: {len(unified)} total player-seasons")


if __name__ == "__main__":
    main()
