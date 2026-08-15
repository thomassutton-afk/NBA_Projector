"""
Module 2 (Aging Curve) -- Small patch: fill in 5 recovered pre-1958
birthdates, closing the last age gap in unified_player_seasons.csv.

These 5 players (6 player-seasons -- Bob Schafer appears in both 1956
and 1957) had no age because they predate the historical source file's
own age data. Birthdates were manually looked up and provided directly
(not sourced from an external file like recovered_birthdates.csv /
merge_missing_ages.py, since this is only 5 people):

    Bob Schafer     1933-03-29
    Don Bielke      1932-05-10
    Frank Reddout   1931-03-04
    Ken McBride     1929-05-23
    Mike O'Neill    1928-08-11

Age convention matches the rest of the pipeline (see
merge_missing_ages.py): age as of Feb 1 of the season (SeasonStart
label = the season's ending year).

Run this from your aging/ folder, AFTER rebuild_unified.py has already
produced unified_player_seasons.csv:

    python patch_pre1958_ages.py

This edits unified_player_seasons.csv in place (only the Age column,
only for these exact 6 rows) and prints the new age-coverage figure,
which should come out to exactly 100.00%.
"""

import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
UNIFIED_PATH = os.path.join(HERE, "unified_player_seasons.csv")

BIRTHDATES = {
    "Bob Schafer": "1933-03-29",
    "Don Bielke": "1932-05-10",
    "Frank Reddout": "1931-03-04",
    "Ken McBride": "1929-05-23",
    "Mike O'Neill": "1928-08-11",
}


def main():
    if not os.path.exists(UNIFIED_PATH):
        raise FileNotFoundError(
            f"Expected unified_player_seasons.csv in {HERE} -- "
            "run rebuild_unified.py first."
        )

    df = pd.read_csv(UNIFIED_PATH)

    before_missing = df["Age"].isna().sum()
    missing_rows = df[df["Age"].isna()]
    print(f"Rows missing age before patch: {before_missing}")
    print(missing_rows[["SeasonStart", "PlayerName", "source"]].to_string(index=False))
    print()

    unmatched = set(missing_rows["PlayerName"]) - set(BIRTHDATES.keys())
    if unmatched:
        raise ValueError(
            f"Found missing-age rows with no birthdate on file: {unmatched}. "
            "This patch script only covers the 5 known pre-1958 names -- "
            "stopping rather than silently leaving them unfilled."
        )

    patched = 0
    for idx, row in missing_rows.iterrows():
        birth = pd.to_datetime(BIRTHDATES[row["PlayerName"]])
        ref_date = pd.to_datetime(f"{int(row['SeasonStart'])}-02-01")
        age = int((ref_date - birth).days / 365.25)
        df.at[idx, "Age"] = age
        patched += 1
        print(f"  {row['PlayerName']:15s} {int(row['SeasonStart'])}  ->  age {age}")

    df.to_csv(UNIFIED_PATH, index=False)

    after_missing = df["Age"].isna().sum()
    coverage = df["Age"].notna().mean() * 100
    print()
    print(f"Patched {patched} rows.")
    print(f"Rows missing age after patch: {after_missing}")
    print(f"Age coverage: {coverage:.2f}%")


if __name__ == "__main__":
    main()
