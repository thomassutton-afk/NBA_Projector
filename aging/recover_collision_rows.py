"""
Module 2 (Aging Curve) -- Recovery: restore 4 player-seasons silently
dropped from historical_clean.csv by a real bug in clean_historical()
(build_player_dataset.py).

ROOT CAUSE (confirmed against the raw source, re-fetched directly from
github.com/peasant98/TheNBACSV/master/nbaNew.csv):

clean_historical()'s original logic was:
    has_tot = 'TOT' in the group's Tm values
    multi_row = group has more than 1 row
    drop non-TOT rows IF has_tot AND multi_row

This assumes that whenever a (SeasonStart, PlayerName) group contains a
TOT row, every other row in that group is a team-stint FRAGMENT of that
same TOT (i.e. a mid-season trade for one player). That assumption
breaks when a completely different, unrelated real player happens to
share the exact same name in the exact same season -- their single
legitimate row gets swept up and deleted, because the code has no way
to tell "fragment of this TOT" apart from "unrelated same-name player"
without checking whether the stats actually reconcile.

VERIFIED SCOPE: every (SeasonStart, PlayerName) group containing a TOT
row was checked -- do the non-TOT rows' stats actually SUM to the TOT
row's stats? (The correct test for "these really are fragments of one
person's season".) Exactly 4 groups fail this test, out of 2,123 TOT
groups checked. All 4 are the same known name-collision players already
documented in the README:

    Charles Jones    1985 -- lost jonesch85's PHO row (age 23)
    Charles Smith    1996 -- lost smithch90's MIN row (age 28)
    Eddie Johnson    1986 -- lost johnsed82's SAC row (age 26)
    Marcus Williams  2008 -- lost willima07's NJN row (age 22)

The surviving TOT row in each case is NOT wrong -- it correctly
represents the OTHER player's (the one who was actually traded)
combined season. Only the unrelated single-team player's row was
incorrectly deleted. The 4 rows recovered below are the exact original
raw rows for each, re-fetched from the same source, with the correct
player_id attached (matched via player_id_seasons.csv, cross-checking
age: e.g. jonesch85's age 23 in 1985 matches the raw PHO row's age 23
exactly).

This is a narrow, targeted recovery of 4 specific known rows, NOT a
general reprocessing of the full raw source -- run it once, after
historical_clean.csv already exists.

Run from your aging/ folder:

    python recover_collision_rows.py
"""

import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HIST_PATH = os.path.join(HERE, "historical_clean.csv")

# Exact raw rows for the 4 confirmed missing player-seasons, re-fetched
# directly from the original source (github.com/peasant98/TheNBACSV).
# player_id cross-checked against player_id_seasons.csv by matching age.
RECOVERED_ROWS = [
    {
        "SeasonStart": 1985.0, "PlayerName": "Charles Jones", "Age": 23.0, "Tm": "PHO",
        "Pos": "C", "G": 78.0, "GS": 14.0, "MP": 1565.0, "PER": 14.4, "TS%": "56.60%",
        "3PAr": 0.009, "FTr": 0.619, "ORB%": 10.2, "DRB%": 18.2, "TRB%": 14.3,
        "AST%": 11.1, "STL%": 1.3, "BLK%": 2.2, "TOV%": 19.8, "USG%": 18.7,
        "OWS": 0.8, "DWS": 2.1, "WS": 2.9, "WS/48": 0.089, "OBPM": -1.4, "DBPM": 1.4,
        "BPM": 0.0, "VORP": 0.8, "FG": 236.0, "FGA": 454.0, "FG%": "52.00%",
        "3P": 0.0, "3PA": 4.0, "3P%": "0.0%", "2P": 236.0, "2PA": 450.0, "2P%": "52.40%",
        "eFG%": "52.00%", "FT": 182.0, "FTA": 281.0, "FT%": "64.80%",
        "ORB": 139.0, "DRB": 255.0, "TRB": 394.0, "AST": 128.0, "STL": 45.0,
        "BLK": 61.0, "TOV": 143.0, "PF": 149.0, "PTS": 654.0,
        "player_id": "jonesch85",
    },
    {
        "SeasonStart": 1996.0, "PlayerName": "Charles Smith", "Age": 28.0, "Tm": "MIN",
        "Pos": "PG", "G": 8.0, "GS": 0.0, "MP": 39.0, "PER": -2.2, "TS%": "27.60%",
        "3PAr": 0.3, "FTr": 0.2, "ORB%": 0.0, "DRB%": 15.3, "TRB%": 7.7,
        "AST%": 22.8, "STL%": 1.3, "BLK%": 0.0, "TOV%": 31.5, "USG%": 18.0,
        "OWS": -0.2, "DWS": 0.0, "WS": -0.2, "WS/48": -0.212, "OBPM": -10.6, "DBPM": -2.1,
        "BPM": -12.7, "VORP": -0.1, "FG": 3.0, "FGA": 10.0, "FG%": "30.00%",
        "3P": 0.0, "3PA": 3.0, "3P%": "0.0%", "2P": 3.0, "2PA": 7.0, "2P%": "42.90%",
        "eFG%": "30.00%", "FT": 0.0, "FTA": 2.0, "FT%": "0.00%",
        "ORB": 0.0, "DRB": 5.0, "TRB": 5.0, "AST": 6.0, "STL": 1.0,
        "BLK": 0.0, "TOV": 5.0, "PF": 7.0, "PTS": 6.0,
        "player_id": "smithch90",
    },
    {
        "SeasonStart": 1986.0, "PlayerName": "Eddie Johnson", "Age": 26.0, "Tm": "SAC",
        "Pos": "SF", "G": 82.0, "GS": 30.0, "MP": 2514.0, "PER": 15.8, "TS%": "52.30%",
        "3PAr": 0.015, "FTr": 0.262, "ORB%": 7.8, "DRB%": 11.0, "TRB%": 9.4,
        "AST%": 13.2, "STL%": 1.0, "BLK%": 0.4, "TOV%": 11.6, "USG%": 26.6,
        "OWS": 2.7, "DWS": 1.4, "WS": 4.0, "WS/48": 0.077, "OBPM": 0.6, "DBPM": -1.8,
        "BPM": -1.2, "VORP": 0.5, "FG": 623.0, "FGA": 1311.0, "FG%": "47.50%",
        "3P": 4.0, "3PA": 20.0, "3P%": "20.0%", "2P": 619.0, "2PA": 1291.0, "2P%": "47.90%",
        "eFG%": "47.70%", "FT": 280.0, "FTA": 343.0, "FT%": "81.60%",
        "ORB": 173.0, "DRB": 246.0, "TRB": 419.0, "AST": 214.0, "STL": 54.0,
        "BLK": 17.0, "TOV": 191.0, "PF": 237.0, "PTS": 1530.0,
        "player_id": "johnsed82",
    },
    {
        "SeasonStart": 2008.0, "PlayerName": "Marcus Williams", "Age": 22.0, "Tm": "NJN",
        "Pos": "PG", "G": 53.0, "GS": 7.0, "MP": 854.0, "PER": 11.0, "TS%": "49.90%",
        "3PAr": 0.485, "FTr": 0.16, "ORB%": 1.9, "DRB%": 11.8, "TRB%": 6.9,
        "AST%": 27.8, "STL%": 1.5, "BLK%": 0.3, "TOV%": 19.3, "USG%": 20.8,
        "OWS": -0.4, "DWS": 0.5, "WS": 0.2, "WS/48": 0.009, "OBPM": -1.6, "DBPM": -2.3,
        "BPM": -3.9, "VORP": -0.4, "FG": 111.0, "FGA": 293.0, "FG%": "37.90%",
        "3P": 54.0, "3PA": 142.0, "3P%": "38.0%", "2P": 57.0, "2PA": 151.0, "2P%": "37.70%",
        "eFG%": "47.10%", "FT": 37.0, "FTA": 47.0, "FT%": "78.70%",
        "ORB": 14.0, "DRB": 87.0, "TRB": 101.0, "AST": 140.0, "STL": 25.0,
        "BLK": 3.0, "TOV": 75.0, "PF": 52.0, "PTS": 313.0,
        "player_id": "willima07",
    },
]


def main():
    if not os.path.exists(HIST_PATH):
        raise FileNotFoundError(f"Expected historical_clean.csv in {HERE}")

    hist = pd.read_csv(HIST_PATH)
    print(f"Loaded historical_clean.csv: {len(hist)} rows")

    # Guard: don't double-add if this script is run twice.
    already_present = 0
    rows_to_add = []
    for r in RECOVERED_ROWS:
        exists = (
            (hist["SeasonStart"] == r["SeasonStart"])
            & (hist["PlayerName"] == r["PlayerName"])
            & (hist["Tm"] == r["Tm"])
        ).any()
        if exists:
            already_present += 1
        else:
            rows_to_add.append(r)

    if already_present == len(RECOVERED_ROWS):
        print("All 4 recovered rows already present -- nothing to do.")
        return

    recovered_df = pd.DataFrame(rows_to_add)
    # match historical_clean.csv's column set exactly; leave any columns
    # not specified above (e.g. 'PlayerSalary ', '#', 'blanl', 'blank2')
    # as NaN, consistent with how sparse those columns already are.
    for col in hist.columns:
        if col not in recovered_df.columns:
            recovered_df[col] = pd.NA
    recovered_df = recovered_df[hist.columns.tolist() + ["player_id"]] if "player_id" not in hist.columns else recovered_df[hist.columns]

    # historical_clean.csv doesn't have a player_id column of its own --
    # that gets attached later by attach_player_ids.py. Keep it off here
    # for schema consistency, attach_player_ids.py's normal name+season
    # matching will pick these rows up correctly on its own now that
    # they exist.
    if "player_id" in recovered_df.columns and "player_id" not in hist.columns:
        recovered_df = recovered_df.drop(columns=["player_id"])

    updated = pd.concat([hist, recovered_df], ignore_index=True)
    updated = updated.sort_values(["PlayerName", "SeasonStart"]).reset_index(drop=True)
    updated.to_csv(HIST_PATH, index=False)

    print(f"Recovered {len(rows_to_add)} previously-dropped player-seasons "
          f"({already_present} were already present)")
    for r in rows_to_add:
        print(f"  + {r['PlayerName']}, {int(r['SeasonStart'])}, age {int(r['Age'])}, {r['Tm']}")
    print(f"\nWrote historical_clean.csv: {len(updated)} rows "
          f"(was {len(hist)})")
    print("\nIMPORTANT: unified_player_seasons.csv was built from the old "
          "historical_clean.csv and does NOT yet include these rows. "
          "Re-run rebuild_unified.py (and the rest of the pipeline) now.")


if __name__ == "__main__":
    main()
