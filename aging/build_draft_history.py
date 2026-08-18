"""
build_draft_history.py

Step 1 of Module 3 (rookie/new-player projection): parse the 77 per-year
draft CSVs in draft_data/ (1950-2026, sourced from Basketball-Reference)
into one clean, combined draft history table.

Each source file is a Basketball-Reference export with some boilerplate
before the real header row (a citation line + a decorative multi-row
header -- inconsistent across years, e.g. 1950 has a leading citation
line that 2026 doesn't), so this script locates the real header row
directly (the line starting with "Rk,Pk,Tm,Player,College") rather than
assuming a fixed number of lines to skip.

Each file also has two columns literally named "MP", two named "PTS",
two named "TRB", and two named "AST" (one set = career TOTALS, the
other = career PER-GAME averages -- Basketball-Reference distinguishes
them with a decorative header row above the real one, which this parser
doesn't rely on). Renamed explicitly below to avoid ambiguity.

IMPORTANT: these career totals/per-game columns are the player's ENTIRE
CAREER as of whenever Basketball-Reference's page was last updated --
NOT rookie-season-specific. They're kept here for reference/future
sanity-checks, but the actual rookie-season z-scores Module 3 needs will
come from a separate join against player_metrics.csv (using each
player's own first season in that dataset), not from these columns.

Output: draft_history.csv -- one row per (draft_year, pick), with
Rk, Pk, Tm, Player, College, Yrs, G, career totals, career per-game
averages, and career advanced stats (WS, WS/48, BPM, VORP).

Run from anywhere with internet access (pulls directly from GitHub raw
content each time -- no local draft_data/ folder needed, though this
can be pointed at a local copy instead by changing SOURCE_MODE below).
"""

import urllib.request
import pandas as pd
import io

START_YEAR = 1950
END_YEAR = 2026
BASE_URL = "https://raw.githubusercontent.com/thomassutton-afk/NBA_Projector/main/draft_data/{year}_Draft.csv"

OUTPUT_FILE = "draft_history.csv"

# Fixed column schema, in order, based on inspecting the real header row
# across multiple years (1950, 2015, 2025, 2026) -- confirmed identical
# 22-column layout throughout, with blank values (not missing columns)
# for stats that didn't exist yet in older eras (3P%, BPM, VORP).
COLUMN_NAMES = [
    "Rk", "Pk", "Tm", "Player", "College", "Yrs", "G",
    "MP_total", "PTS_total", "TRB_total", "AST_total",
    "FG_pct", "3P_pct", "FT_pct",
    "MP_per_game", "PTS_per_game", "TRB_per_game", "AST_per_game",
    "WS", "WS_per48", "BPM", "VORP",
]


def fetch_and_parse_year(year):
    url = BASE_URL.format(year=year)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw_text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARNING: failed to fetch {year}: {e}")
        return None

    lines = raw_text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("Rk,Pk,Tm,Player,College"):
            header_idx = i
            break

    if header_idx is None:
        print(f"  WARNING: could not find the expected header row for {year} -- skipping")
        return None

    # skip the located real header row too -- we assign our own explicit
    # column names below rather than trusting pandas to dedupe the
    # duplicate "MP"/"PTS"/"TRB"/"AST" column names correctly
    data_lines = lines[header_idx + 1:]
    csv_text = "\n".join(data_lines)

    if not csv_text.strip():
        print(f"  {year}: no data rows found (draft not yet played / no picks listed)")
        return None

    df = pd.read_csv(io.StringIO(csv_text), header=None, names=COLUMN_NAMES)
    df = df.dropna(how="all")  # drop any fully-blank trailing lines
    df["draft_year"] = year
    return df


def main():
    print(f"Fetching draft data for {START_YEAR}-{END_YEAR} from "
          f"github.com/thomassutton-afk/NBA_Projector/draft_data ...\n")

    all_years = []
    for year in range(START_YEAR, END_YEAR + 1):
        df = fetch_and_parse_year(year)
        if df is not None:
            print(f"  {year}: {len(df)} picks")
            all_years.append(df)

    if not all_years:
        print("ERROR: no draft years were successfully parsed.")
        return

    combined = pd.concat(all_years, ignore_index=True)

    # Drop rows with no player name. Two distinct causes, both handled
    # the same way since neither can be matched to a player_id anyway:
    #   1. Footer/metadata rows Basketball-Reference includes inline,
    #      e.g. "Milwaukee Bucks forfeited their Second Round pick" --
    #      these parse as fully-blank rows (Rk/Pk/Tm/Player all NaN).
    #   2. A handful of rows where Tm IS populated (a real pick
    #      happened) but Player is blank in the source itself -- a
    #      genuine small gap in the underlying scrape, not a parsing
    #      artifact. Confirmed directly against the raw source: 2024
    #      picks 59-60 and 2025 pick 60.
    blank_name_rows = combined[combined["Player"].isna()]
    real_picks_missing_name = blank_name_rows[blank_name_rows["Tm"].notna()]
    footer_rows = blank_name_rows[blank_name_rows["Tm"].isna()]

    if len(footer_rows) > 0:
        print(f"\nDropped {len(footer_rows)} footer/metadata rows "
              f"(e.g. forfeited-pick notices) -- not real picks.")
    if len(real_picks_missing_name) > 0:
        print(f"\nWARNING: {len(real_picks_missing_name)} real picks have "
              f"no player name in the source data (not a parsing issue --"
              f" confirmed against the raw file). These will be dropped "
              f"since they can't be matched to a player_id:")
        print(real_picks_missing_name[["draft_year", "Pk", "Tm"]].to_string(index=False))

    combined = combined[combined["Player"].notna()].reset_index(drop=True)

    # reorder so draft_year comes first
    cols = ["draft_year"] + [c for c in combined.columns if c != "draft_year"]
    combined = combined[cols]

    combined.to_csv(OUTPUT_FILE, index=False)
    print(f"\nWrote {OUTPUT_FILE}: {len(combined)} rows across "
          f"{combined['draft_year'].nunique()} draft years "
          f"({combined['draft_year'].min()}-{combined['draft_year'].max()})")

    # quick sanity summary
    picks_per_year = combined.groupby("draft_year").size()
    print(f"\nPicks per year -- min: {picks_per_year.min()} "
          f"(year {picks_per_year.idxmin()}), "
          f"max: {picks_per_year.max()} (year {picks_per_year.idxmax()})")
    print(f"Players with a blank name (should be 0): "
          f"{combined['Player'].isna().sum()}")


if __name__ == "__main__":
    main()
