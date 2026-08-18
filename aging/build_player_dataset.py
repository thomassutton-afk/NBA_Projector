"""
Module 2 (Aging Curve) -- Step 1: Build the unified player-season dataset.

Combines two sources into one player-season table spanning 1950-2026:

  1. Historical box scores + advanced metrics, 1950-2017
     Source: github.com/peasant98/TheNBACSV (nbaNew.csv)
     Originally scraped from Basketball-Reference.

  2. Recent per-game box scores, aggregated to season totals, 2017-18 onward
     Source: github.com/NocturneBear/NBA-Data-2010-2024
     (only 2017-18 onward is used here, to avoid double-counting the
     2010-2017 seasons already covered by source #1)

Age for every 2017-18+ row is looked up DIRECTLY (name + season -> age)
against AllPlayerDataforIDs.txt, a full-history (1947-2026) name/age/team
roster file. This replaces the old carry-forward-from-history approach,
which could only assign an age to a 2018+ player if that same player also
had a pre-2018 row to anchor from -- leaving every player whose entire
career started in 2018+ (753 players, ~1.7M minutes) unplaced. Direct
lookup covers 2018+ debuts too, since the reference file itself spans
back to 1947.

Run directly:
    python build_player_dataset.py

Outputs (all written to this script's directory):
    historical_clean.csv        -- source 1, deduplicated
    recent_aggregated.csv       -- source 2, aggregated to season totals
    recent_with_age.csv         -- source 2 rows with age attached via
                                    direct lookup against the reference file
    residual_gap_players.csv    -- source 2 rows that could NOT be matched
                                    to the reference file (should be ~0;
                                    flagged here rather than silently
                                    dropped -- see NAME_ALIAS_BY_PERSON_ID
                                    below for known nickname-mismatch fixes)
    unified_player_seasons.csv  -- historical_clean + recent_with_age,
                                    concatenated to one common schema.
                                    THIS is Module 2's working dataset.

KNOWN LIMITATIONS (see README for full detail):
  - historical_clean.csv has no unique player ID, only names. ~23
    player-seasons are genuine same-name collisions between two
    different real people (e.g. two different "George Johnson"s).
    Left as-is; not something this script can resolve automatically.
  - No height/weight data in either source. Deferred; see README.
"""

import os
import re
import urllib.request

import pandas as pd
from unidecode import unidecode

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

HISTORICAL_URL = "https://raw.githubusercontent.com/peasant98/TheNBACSV/master/nbaNew.csv"
RECENT_URLS = [
    f"https://raw.githubusercontent.com/NocturneBear/NBA-Data-2010-2024/main/regular_season_box_scores_2010_2024_part_{i}.csv"
    for i in (1, 2, 3)
]

HISTORICAL_RAW = os.path.join(HERE, "_raw_nbaNew.csv")
RECENT_RAW = [os.path.join(HERE, f"_raw_box_scores_part_{i}.csv") for i in (1, 2, 3)]

# Full-history name/age/team roster file (1947-2026), used to look up age
# directly for every 2017-18+ row. Lives at the project root.
AGE_REFERENCE_PATH = os.path.join(PROJECT_ROOT, "AllPlayerDataforIDs.txt")

# The historical file's last covered season, as a "SeasonStart" label
# (label = ending year of the season, e.g. 2017 -> the 2016-17 season).
LAST_HISTORICAL_SEASON = 2017

# Known nickname/short-name mismatches between recent_aggregated.csv (NBA
# stats official name) and AllPlayerDataforIDs.txt (informal name), found
# via manual review of the ~0.4% of rows a straight name+season match
# missed. Keyed by personId (unambiguous) -> the name to look up instead.
# Confirmed by cross-checking team + season + age for a unique match.
NAME_ALIAS_BY_PERSON_ID = {
    1629244: "Cameron Reynolds",
    1630693: "Jaime Echenique",
    1630562: "Matthew Hurt",
    1628249: "Mitch Creek",
    1629053: "Vince Edwards",
    1626205: "Vince Hunter",
    # Nene Hilario is listed in the reference file under his stage mononym.
    2403: "Nene",
    # Nate Williams == Jeenathan Williams Jr. -- previously identified via
    # manual research (see README); the reference file itself confirms
    # this, using "Jeenathan Williams" for 2023-2025 rows and switching to
    # "Nate Williams" for the 2026 row, all under one consistent identity.
    1631466: "Jeenathan Williams",
}


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


def _normalize_name(name):
    """Normalize a player name for matching: transliterate accents,
    strip periods (so 'A.J. Green' matches 'AJ Green'), strip the
    reference file's own '(YY)' debut-year disambiguation tag (used when
    two different players share a name, e.g. 'Johnny Davis (23)' vs the
    1977 'Johnny Davis (77)'), then strip generational suffixes
    (Jr./Sr./III/IV/II)."""
    n = unidecode(str(name))
    n = re.sub(r"\.", "", n)
    n = re.sub(r"\s*\(\d{2}\)$", "", n)
    return _strip_suffix(n)


def load_age_reference():
    """Load AllPlayerDataforIDs.txt: a tab-separated, full-history
    (1947-2026) name/age/team/season roster with no header row. Returns
    a (normalized_name, SeasonStart) -> Age lookup table.

    The reference file disambiguates repeat names with a '(YY)' debut-year
    tag (e.g. 'Johnny Davis (23)' vs the 1977 'Johnny Davis (77)'), which
    _normalize_name() strips. Stripping it is only safe when the two
    same-named players' seasons don't overlap -- if they do, collapsing
    them onto one key could silently assign the wrong age. So: group by
    the un-stripped PlayerName first (this keeps distinct taggeded players
    apart), and only merge two same-key groups together if their season
    ranges don't overlap. Any (key, season) pair that's still ambiguous
    after that is dropped from the lookup table entirely and reported --
    a downstream row that needed it will land in residual_gap_players.csv
    rather than silently getting the wrong age."""
    ref = pd.read_csv(
        AGE_REFERENCE_PATH, sep="\t",
        names=["PlayerName", "Age", "Team", "SeasonStart"],
        encoding="utf-8",
    )
    ref["PlayerName"] = ref["PlayerName"].str.strip()
    ref["key"] = ref["PlayerName"].apply(_normalize_name)
    ref = ref.drop_duplicates(subset=["PlayerName", "SeasonStart", "Age"])

    # Per normalized key, check whether the underlying distinct PlayerName
    # variants (e.g. "Johnny Davis (77)" and "Johnny Davis (23)") have
    # overlapping season ranges.
    rows = []
    n_dropped_seasons = 0
    for key, grp in ref.groupby("key"):
        variants = grp["PlayerName"].unique()
        if len(variants) == 1:
            rows.append(grp[["key", "SeasonStart", "Age"]])
            continue

        # Multiple raw names collapse to this key. Check pairwise season
        # overlap between variants.
        ranges = {v: (grp.loc[grp["PlayerName"] == v, "SeasonStart"].min(),
                       grp.loc[grp["PlayerName"] == v, "SeasonStart"].max())
                  for v in variants}
        overlap = False
        vlist = list(ranges.items())
        for i in range(len(vlist)):
            for j in range(i + 1, len(vlist)):
                (v1, (lo1, hi1)), (v2, (lo2, hi2)) = vlist[i], vlist[j]
                if lo1 <= hi2 and lo2 <= hi1:
                    overlap = True

        if not overlap:
            # Safe to collapse -- no real ambiguity introduced.
            rows.append(grp[["key", "SeasonStart", "Age"]])
        else:
            # Genuinely ambiguous once tags are stripped -- drop these
            # seasons from the lookup table rather than guess.
            dup_seasons = grp.groupby("SeasonStart")["Age"].nunique()
            bad_seasons = dup_seasons[dup_seasons > 1].index
            safe = grp[~grp["SeasonStart"].isin(bad_seasons)]
            rows.append(safe[["key", "SeasonStart", "Age"]])
            n_dropped_seasons += len(bad_seasons)

    if n_dropped_seasons:
        print(f"  NOTE: {n_dropped_seasons} (name, season) pairs dropped "
              f"from the age reference lookup -- two different players "
              f"share a name AND overlap in that season after tag-"
              f"stripping, so no safe automatic match exists. Any 2018+ "
              f"row needing one of these will show up in "
              f"residual_gap_players.csv.")

    out = pd.concat(rows, ignore_index=True).drop_duplicates(subset=["key", "SeasonStart"])
    return out


def assign_ages(hist, recent):
    """Assign age to every 2017-18+ row via DIRECT lookup against the
    full-history age reference file (name + season -> age), rather than
    carrying an age forward from a pre-2018 historical row. This covers
    players whose entire career started in 2018+, since the reference
    file itself spans back to 1947.

    A small set of known nickname mismatches (NAME_ALIAS_BY_PERSON_ID) are
    resolved by personId before lookup. Any row still unmatched after that
    is written to residual_gap_players.csv rather than silently dropped."""
    recent = recent.copy()

    alias_name = recent["personId"].map(NAME_ALIAS_BY_PERSON_ID)
    lookup_name = alias_name.fillna(recent["PlayerName"])
    recent["key"] = lookup_name.apply(_normalize_name)

    age_ref = load_age_reference()
    recent = recent.merge(age_ref, on=["key", "SeasonStart"], how="left")

    has_age = recent[recent["Age"].notna()].drop(columns=["key"])
    no_age = recent[recent["Age"].isna()].drop(columns=["key"])

    total_mp = recent["MP"].sum()
    kept_mp = has_age["MP"].sum()
    print(f"recent_with_age.csv: {len(has_age)} player-seasons "
          f"({kept_mp/total_mp*100:.1f}% of 2018-2026 minutes)")

    if len(no_age):
        residual = no_age.groupby(["personId", "PlayerName"])["MP"].sum().reset_index()
        residual = residual.sort_values("MP", ascending=False)
        residual["MP"] = residual["MP"].round(0).astype(int)
        residual.columns = ["personId", "PlayerName", "total_minutes_unmatched"]
        residual.to_csv(os.path.join(HERE, "residual_gap_players.csv"), index=False)
        print(f"  residual_gap_players.csv: {len(residual)} players still "
              f"unmatched ({(total_mp-kept_mp)/total_mp*100:.2f}% of minutes) "
              f"-- review before treating the dataset as complete")
    else:
        print("  residual_gap_players.csv: none -- 100% matched")

    has_age.to_csv(os.path.join(HERE, "recent_with_age.csv"), index=False)
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
