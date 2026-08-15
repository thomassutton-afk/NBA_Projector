"""
Module 2 (Aging Curve) -- Step 1: Build the unified player-season dataset.

Combines two sources into one player-season table spanning 1950-2024:

  1. Historical box scores + advanced metrics, 1950-2017
     Source: github.com/peasant98/TheNBACSV (nbaNew.csv)
     Originally scraped from Basketball-Reference.

  2. Recent per-game box scores, aggregated to season totals, 2017-18 to 2023-24
     Source: github.com/NocturneBear/NBA-Data-2010-2024
     (only 2017-18 onward is used here, to avoid double-counting the
     2010-2017 seasons already covered by source #1)

Run directly:
    python build_player_dataset.py

Outputs (all written to this script's directory):
    historical_clean.csv       -- source 1, deduplicated
    recent_aggregated.csv      -- source 2, aggregated to season totals
    recent_with_age.csv        -- source 2 rows where an age could be
                                   carried forward from source 1
    missing_age_players.csv    -- players with NO age (true 2017+ debuts),
                                   sorted by total minutes -- this is the
                                   file to fill in with real birthdates
                                   (see merge_missing_ages.py)
    unified_player_seasons.csv -- historical_clean + recent_with_age,
                                   concatenated to one common schema.
                                   THIS is Module 2's working dataset.

KNOWN LIMITATIONS (see README for full detail):
  - historical_clean.csv has no unique player ID, only names. ~23
    player-seasons are genuine same-name collisions between two
    different real people (e.g. two different "George Johnson"s).
    Left as-is; not something this script can resolve automatically.
  - Age for 2017-18 onward is carried forward from each player's most
    recent historical row (age increases by exactly 1 per season). Any
    player whose ENTIRE career started in 2017-18 or later has no
    anchor and is excluded here -- see missing_age_players.csv.
  - No height/weight data in either source. Deferred; see README.
"""

import os
import re
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

HISTORICAL_URL = "https://raw.githubusercontent.com/peasant98/TheNBACSV/master/nbaNew.csv"
RECENT_URLS = [
    f"https://raw.githubusercontent.com/NocturneBear/NBA-Data-2010-2024/main/regular_season_box_scores_2010_2024_part_{i}.csv"
    for i in (1, 2, 3)
]

HISTORICAL_RAW = os.path.join(HERE, "_raw_nbaNew.csv")
RECENT_RAW = [os.path.join(HERE, f"_raw_box_scores_part_{i}.csv") for i in (1, 2, 3)]

# The historical file's last covered season, as a "SeasonStart" label
# (label = ending year of the season, e.g. 2017 -> the 2016-17 season).
LAST_HISTORICAL_SEASON = 2017


def _download(url, path):
    if not os.path.exists(path):
        print(f"  downloading {os.path.basename(path)} ...")
        urllib.request.urlretrieve(url, path)
    else:
        print(f"  using cached {os.path.basename(path)}")


def fetch_sources():
    print("Fetching source files (cached after first run)...")
    _download(HISTORICAL_URL, HISTORICAL_RAW)
    for url, path in zip(RECENT_URLS, RECENT_RAW):
        _download(url, path)


def clean_historical():
    """Load nbaNew.csv, strip garbage rows, resolve traded-player duplicate
    rows using the TOT (combined-team) row where present."""
    df = pd.read_csv(HISTORICAL_RAW)
    df = df[df["SeasonStart"].notna()].copy()

    has_tot = df.groupby(["SeasonStart", "PlayerName"])["Tm"].transform(lambda x: "TOT" in x.values)
    multi_row = df.groupby(["SeasonStart", "PlayerName"])["Tm"].transform("size") > 1
    to_drop = multi_row & has_tot & (df["Tm"] != "TOT")
    df_clean = df[~to_drop].copy()

    remaining_dupes = (df_clean.groupby(["SeasonStart", "PlayerName"]).size() > 1).sum()

    out_path = os.path.join(HERE, "historical_clean.csv")
    df_clean.to_csv(out_path, index=False)
    print(f"historical_clean.csv: {len(df_clean)} rows "
          f"({remaining_dupes} residual name-collision player-seasons, left as-is)")
    return df_clean


def _parse_minutes(m):
    if pd.isna(m):
        return 0.0
    mins, secs = m.split(":")
    return int(mins) + int(secs) / 60


def aggregate_recent():
    """Load the 3-part per-game box score files, filter to 2017-18 onward
    and games actually played, and aggregate to season totals per player."""
    parts = [pd.read_csv(p) for p in RECENT_RAW]
    df = pd.concat(parts, ignore_index=True)

    season_cutoff = f"{LAST_HISTORICAL_SEASON}-{str(LAST_HISTORICAL_SEASON + 1)[-2:]}"
    df = df[df["season_year"] >= season_cutoff].copy()
    df = df[df["comment"].isna()].copy()  # only games actually played
    df["MP_dec"] = df["minutes"].apply(_parse_minutes)

    agg = df.groupby(["personId", "personName", "season_year"]).agg(
        G=("gameId", "count"),
        MP=("MP_dec", "sum"),
        FG=("fieldGoalsMade", "sum"),
        FGA=("fieldGoalsAttempted", "sum"),
        threeP=("threePointersMade", "sum"),
        threePA=("threePointersAttempted", "sum"),
        FT=("freeThrowsMade", "sum"),
        FTA=("freeThrowsAttempted", "sum"),
        ORB=("reboundsOffensive", "sum"),
        DRB=("reboundsDefensive", "sum"),
        TRB=("reboundsTotal", "sum"),
        AST=("assists", "sum"),
        STL=("steals", "sum"),
        BLK=("blocks", "sum"),
        TOV=("turnovers", "sum"),
        PF=("foulsPersonal", "sum"),
        PTS=("points", "sum"),
    ).reset_index()

    agg = agg.rename(columns={"threeP": "3P", "threePA": "3PA", "personName": "PlayerName"})
    agg["SeasonStart"] = agg["season_year"].str[:4].astype(int) + 1

    out_path = os.path.join(HERE, "recent_aggregated.csv")
    agg.to_csv(out_path, index=False)
    print(f"recent_aggregated.csv: {len(agg)} player-seasons, "
          f"{agg['SeasonStart'].min()}-{agg['SeasonStart'].max()}")
    return agg


def _strip_suffix(name):
    return re.sub(r"\s+(Jr\.?|Sr\.?|III|IV|II)$", "", str(name)).strip()


def assign_ages(hist, recent):
    """Carry forward age from each player's most recent historical row
    (matched on suffix-stripped name). Rows with no match (true post-2017
    debuts) are split out to missing_age_players.csv instead of being
    silently dropped."""
    hist = hist.copy()
    recent = recent.copy()
    hist["key"] = hist["PlayerName"].apply(_strip_suffix)
    recent["key"] = recent["PlayerName"].apply(_strip_suffix)

    anchor = hist.sort_values("SeasonStart").groupby("key").tail(1)[["key", "SeasonStart", "Age"]]
    anchor = anchor.rename(columns={"SeasonStart": "anchor_season", "Age": "anchor_age"})

    recent = recent.merge(anchor, on="key", how="left")
    recent["Age"] = recent["anchor_age"] + (recent["SeasonStart"] - recent["anchor_season"])

    has_age = recent[recent["Age"].notna()].drop(columns=["anchor_season", "anchor_age", "key"])
    no_age = recent[recent["Age"].isna()]

    total_mp = recent["MP"].sum()
    kept_mp = has_age["MP"].sum()
    print(f"recent_with_age.csv: {len(has_age)} player-seasons "
          f"({kept_mp/total_mp*100:.1f}% of 2018-2024 minutes)")

    missing = no_age.groupby(["personId", "PlayerName"])["MP"].sum().reset_index()
    missing = missing.sort_values("MP", ascending=False)
    missing["MP"] = missing["MP"].round(0).astype(int)
    missing.columns = ["personId", "PlayerName", "total_minutes_2018_2024"]
    print(f"missing_age_players.csv: {len(missing)} players needing external birthdate data "
          f"({(total_mp-kept_mp)/total_mp*100:.1f}% of 2018-2024 minutes)")

    has_age.to_csv(os.path.join(HERE, "recent_with_age.csv"), index=False)
    missing.to_csv(os.path.join(HERE, "missing_age_players.csv"), index=False)
    return has_age


def build_unified(hist, recent_with_age):
    """Concatenate historical + recent (age-known) onto one common schema."""
    common_cols = ["SeasonStart", "PlayerName", "Age", "G", "MP", "FG", "FGA",
                    "3P", "3PA", "FT", "FTA", "ORB", "DRB", "TRB", "AST",
                    "STL", "BLK", "TOV", "PF", "PTS"]

    hist_common = hist[common_cols].copy()
    hist_common["source"] = "historical_1950_2017"

    recent_common = recent_with_age[common_cols].copy()
    recent_common["source"] = "recent_2018_2024"

    unified = pd.concat([hist_common, recent_common], ignore_index=True)
    unified = unified.sort_values(["PlayerName", "SeasonStart"]).reset_index(drop=True)

    out_path = os.path.join(HERE, "unified_player_seasons.csv")
    unified.to_csv(out_path, index=False)
    print(f"unified_player_seasons.csv: {len(unified)} total player-seasons, "
          f"{unified['SeasonStart'].min():.0f}-{unified['SeasonStart'].max():.0f}")
    return unified


if __name__ == "__main__":
    fetch_sources()
    print()
    hist = clean_historical()
    recent = aggregate_recent()
    print()
    recent_with_age = assign_ages(hist, recent)
    print()
    build_unified(hist, recent_with_age)
