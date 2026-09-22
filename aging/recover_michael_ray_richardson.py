"""
Module 2 (Aging Curve) -- Recovery: add Michael Ray Richardson's 8 NBA
seasons, which are entirely absent from the project's historical source
(github.com/peasant98/TheNBACSV/master/nbaNew.csv).

CONFIRMED SCOPE: this is the only player in the entire dataset missing
this way. Checked directly against the raw source file (every row
containing "Richard" was inspected) -- he simply isn't there, under any
spelling. This is a gap in that third-party GitHub source itself, not a
bug in this project's own pipeline, and not fixable by any code change
here. He IS present in player_id_seasons.csv (the separate, full
1947-2026 ID reference file, as "Micheal Ray Richardson" -- the
well-documented historical misspelling of his first name -- under
player_id "richami79"), so attach_player_ids.py should match these rows
to that ID automatically via its normal 5-pass matching once they exist
in historical_clean.csv.

SOURCE: hand-transcribed from his official Basketball-Reference page
(basketball-reference.com/players/r/richami01.html), regular-season
Totals and Advanced tables. He played 1978-79 through 1985-86 (8
seasons); the 1986-87 season is correctly excluded -- he was suspended
by the NBA for violating its drug policy and never played that season.

VERIFIED: every counting-stat column below (G, MP, FG, FGA, 3P, FT,
ORB, TRB, AST, STL, BLK, TOV, PF, PTS) sums exactly to the career
totals row on his Basketball-Reference page (556 games, 18,589
minutes, 8,253 points, etc.) -- transcription checked against that
independent total, not just copied once.

This player is the ONE row in this entire dataset sourced by hand
rather than from the bulk GitHub source everyone else comes from --
noted here and in the README so his provenance is clear.

Run from your aging/ folder, after historical_clean.csv already exists:

    python recover_michael_ray_richardson.py
"""

import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HIST_PATH = os.path.join(HERE, "historical_clean.csv")

# Hand-transcribed from Basketball-Reference, regular season only.
# 3PAr/FTr/ORB%/DRB%/TRB%/AST%/STL%/BLK%/TOV%/USG% are left blank --
# consistent with this project's compute_metrics.py, which deliberately
# does not use those pre-built shooting-profile columns for anything
# (only PER/TS%/WS/BPM feed its cross-check step, and those ARE
# included below in full).
RICHARDSON_ROWS = [
    {
        "SeasonStart": 1979.0, "PlayerName": "Michael Ray Richardson", "Age": 23.0, "Tm": "NYK",
        "Pos": "PG", "G": 72.0, "GS": 5.0, "MP": 1218.0, "PER": 12.4, "TS%": "43.50%",
        "OWS": -1.4, "DWS": 1.7, "WS": 0.3, "WS/48": 0.013, "OBPM": -2.7, "DBPM": 1.6,
        "BPM": -1.1, "VORP": 0.3, "FG": 200.0, "FGA": 483.0, "FG%": "41.40%",
        "3P": 0.0, "3PA": 0.0, "3P%": "", "2P": 200.0, "2PA": 483.0, "2P%": "41.40%",
        "eFG%": "41.40%", "FT": 69.0, "FTA": 128.0, "FT%": "53.90%",
        "ORB": 78.0, "DRB": 155.0, "TRB": 233.0, "AST": 213.0, "STL": 100.0,
        "BLK": 18.0, "TOV": 141.0, "PF": 188.0, "PTS": 469.0,
    },
    {
        "SeasonStart": 1980.0, "PlayerName": "Michael Ray Richardson", "Age": 24.0, "Tm": "NYK",
        "Pos": "SG", "G": 82.0, "GS": 82.0, "MP": 3060.0, "PER": 17.8, "TS%": "51.70%",
        "OWS": 2.4, "DWS": 3.7, "WS": 6.0, "WS/48": 0.094, "OBPM": 1.7, "DBPM": 1.3,
        "BPM": 3.1, "VORP": 3.9, "FG": 502.0, "FGA": 1063.0, "FG%": "47.20%",
        "3P": 27.0, "3PA": 110.0, "3P%": "24.50%", "2P": 475.0, "2PA": 953.0, "2P%": "49.80%",
        "eFG%": "48.50%", "FT": 223.0, "FTA": 338.0, "FT%": "66.00%",
        "ORB": 151.0, "DRB": 388.0, "TRB": 539.0, "AST": 832.0, "STL": 265.0,
        "BLK": 35.0, "TOV": 359.0, "PF": 260.0, "PTS": 1254.0,
    },
    {
        "SeasonStart": 1981.0, "PlayerName": "Michael Ray Richardson", "Age": 25.0, "Tm": "NYK",
        "Pos": "SG", "G": 79.0, "GS": 79.0, "MP": 3175.0, "PER": 17.1, "TS%": "51.10%",
        "OWS": 2.2, "DWS": 4.7, "WS": 6.9, "WS/48": 0.104, "OBPM": 1.4, "DBPM": 1.9,
        "BPM": 3.2, "VORP": 4.2, "FG": 523.0, "FGA": 1116.0, "FG%": "46.90%",
        "3P": 23.0, "3PA": 102.0, "3P%": "22.50%", "2P": 500.0, "2PA": 1014.0, "2P%": "49.30%",
        "eFG%": "47.90%", "FT": 224.0, "FTA": 338.0, "FT%": "66.30%",
        "ORB": 173.0, "DRB": 372.0, "TRB": 545.0, "AST": 627.0, "STL": 232.0,
        "BLK": 35.0, "TOV": 302.0, "PF": 258.0, "PTS": 1293.0,
    },
    {
        "SeasonStart": 1982.0, "PlayerName": "Michael Ray Richardson", "Age": 26.0, "Tm": "NYK",
        "Pos": "PG", "G": 82.0, "GS": 79.0, "MP": 3044.0, "PER": 17.7, "TS%": "49.80%",
        "OWS": 1.6, "DWS": 3.8, "WS": 5.5, "WS/48": 0.086, "OBPM": 1.3, "DBPM": 1.4,
        "BPM": 2.7, "VORP": 3.6, "FG": 619.0, "FGA": 1343.0, "FG%": "46.10%",
        "3P": 19.0, "3PA": 101.0, "3P%": "18.80%", "2P": 600.0, "2PA": 1242.0, "2P%": "48.30%",
        "eFG%": "46.80%", "FT": 212.0, "FTA": 303.0, "FT%": "70.00%",
        "ORB": 177.0, "DRB": 388.0, "TRB": 565.0, "AST": 572.0, "STL": 213.0,
        "BLK": 41.0, "TOV": 291.0, "PF": 317.0, "PTS": 1469.0,
    },
    {
        # Combined 2-team season (traded mid-year, GSW + NJN) -- matches
        # the "2TM" convention already used elsewhere in this source.
        "SeasonStart": 1983.0, "PlayerName": "Michael Ray Richardson", "Age": 27.0, "Tm": "TOT",
        "Pos": "PG", "G": 64.0, "GS": 51.0, "MP": 2076.0, "PER": 13.9, "TS%": "45.40%",
        "OWS": -1.1, "DWS": 3.2, "WS": 2.0, "WS/48": 0.047, "OBPM": -1.2, "DBPM": 1.6,
        "BPM": 0.4, "VORP": 1.3, "FG": 346.0, "FGA": 815.0, "FG%": "42.50%",
        "3P": 8.0, "3PA": 51.0, "3P%": "15.70%", "2P": 338.0, "2PA": 764.0, "2P%": "44.20%",
        "eFG%": "42.90%", "FT": 106.0, "FTA": 163.0, "FT%": "65.00%",
        "ORB": 113.0, "DRB": 182.0, "TRB": 295.0, "AST": 432.0, "STL": 182.0,
        "BLK": 24.0, "TOV": 244.0, "PF": 240.0, "PTS": 806.0,
    },
    {
        "SeasonStart": 1984.0, "PlayerName": "Michael Ray Richardson", "Age": 28.0, "Tm": "NJN",
        "Pos": "PG", "G": 48.0, "GS": 25.0, "MP": 1285.0, "PER": 15.1, "TS%": "50.00%",
        "OWS": 0.3, "DWS": 2.1, "WS": 2.4, "WS/48": 0.090, "OBPM": -0.4, "DBPM": 2.2,
        "BPM": 1.8, "VORP": 1.2, "FG": 243.0, "FGA": 528.0, "FG%": "46.00%",
        "3P": 14.0, "3PA": 58.0, "3P%": "24.10%", "2P": 229.0, "2PA": 470.0, "2P%": "48.70%",
        "eFG%": "47.30%", "FT": 76.0, "FTA": 108.0, "FT%": "70.40%",
        "ORB": 56.0, "DRB": 116.0, "TRB": 172.0, "AST": 214.0, "STL": 103.0,
        "BLK": 20.0, "TOV": 118.0, "PF": 156.0, "PTS": 576.0,
    },
    {
        "SeasonStart": 1985.0, "PlayerName": "Michael Ray Richardson", "Age": 29.0, "Tm": "NJN",
        "Pos": "PG", "G": 82.0, "GS": 82.0, "MP": 3127.0, "PER": 19.8, "TS%": "51.30%",
        "OWS": 4.5, "DWS": 4.2, "WS": 8.7, "WS/48": 0.134, "OBPM": 2.5, "DBPM": 1.6,
        "BPM": 4.1, "VORP": 4.8, "FG": 690.0, "FGA": 1470.0, "FG%": "46.90%",
        "3P": 29.0, "3PA": 115.0, "3P%": "25.20%", "2P": 661.0, "2PA": 1355.0, "2P%": "48.80%",
        "eFG%": "47.90%", "FT": 240.0, "FTA": 313.0, "FT%": "76.70%",
        "ORB": 156.0, "DRB": 301.0, "TRB": 457.0, "AST": 669.0, "STL": 243.0,
        "BLK": 22.0, "TOV": 249.0, "PF": 277.0, "PTS": 1649.0,
    },
    {
        "SeasonStart": 1986.0, "PlayerName": "Michael Ray Richardson", "Age": 30.0, "Tm": "NJN",
        "Pos": "PG", "G": 47.0, "GS": 39.0, "MP": 1604.0, "PER": 16.9, "TS%": "49.80%",
        "OWS": 1.0, "DWS": 2.3, "WS": 3.3, "WS/48": 0.099, "OBPM": 0.8, "DBPM": 2.1,
        "BPM": 2.8, "VORP": 1.9, "FG": 296.0, "FGA": 661.0, "FG%": "44.80%",
        "3P": 4.0, "3PA": 27.0, "3P%": "14.80%", "2P": 292.0, "2PA": 634.0, "2P%": "46.10%",
        "eFG%": "45.10%", "FT": 141.0, "FTA": 179.0, "FT%": "78.80%",
        "ORB": 77.0, "DRB": 173.0, "TRB": 250.0, "AST": 340.0, "STL": 125.0,
        "BLK": 11.0, "TOV": 150.0, "PF": 163.0, "PTS": 737.0,
    },
]

# Cross-check every counting stat against his official career totals
# (Basketball-Reference "8 Yrs" row) before writing anything.
CAREER_TOTALS = {
    "G": 556, "MP": 18589, "FG": 3419, "FGA": 7479, "3P": 124,
    "FT": 1291, "ORB": 981, "TRB": 3056, "AST": 3899, "STL": 1463,
    "BLK": 206, "TOV": 1854, "PF": 1859, "PTS": 8253,
}


def main():
    if not os.path.exists(HIST_PATH):
        raise FileNotFoundError(f"Expected historical_clean.csv in {HERE}")

    df = pd.DataFrame(RICHARDSON_ROWS)
    for col, expected in CAREER_TOTALS.items():
        actual = df[col].sum()
        if actual != expected:
            raise ValueError(
                f"Transcription check failed: {col} sums to {actual}, "
                f"expected {expected} (Basketball-Reference career total). "
                f"Refusing to write -- fix the row data above before "
                f"re-running."
            )
    print(f"Transcription check passed: all {len(CAREER_TOTALS)} counting "
          f"stats sum exactly to his official career totals.")

    hist = pd.read_csv(HIST_PATH, low_memory=False)
    print(f"Loaded historical_clean.csv: {len(hist)} rows")

    already_present = (
        hist["PlayerName"] == "Michael Ray Richardson"
    ).any()
    if already_present:
        print("Michael Ray Richardson rows already present -- nothing to do.")
        return

    for col in hist.columns:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[hist.columns]

    updated = pd.concat([hist, df], ignore_index=True)
    updated = updated.sort_values(["PlayerName", "SeasonStart"]).reset_index(drop=True)
    updated.to_csv(HIST_PATH, index=False)

    print(f"Added {len(df)} seasons for Michael Ray Richardson "
          f"(1978-79 through 1985-86; 1986-87 correctly excluded -- "
          f"suspended, did not play)")
    print(f"\nWrote historical_clean.csv: {len(updated)} rows "
          f"(was {len(hist)})")
    print("\nIMPORTANT: unified_player_seasons.csv was built from the old "
          "historical_clean.csv and does NOT yet include these rows. "
          "Re-run rebuild_unified.py (and the rest of the pipeline) now.")


if __name__ == "__main__":
    main()
