"""
Module 3 (Rookie/New-Player Projection) -- Step 2: match draft picks to
player_id.

For each player_id in player_metrics.csv, extracts their rookie season
(earliest SeasonStart). Matches draft_history.csv's Player name against
that rookie-season lookup, trying TWO name sources per candidate:

  1. PlayerName from player_metrics.csv itself (the original name as it
     appears in the historical box score source -- occasionally
     truncated, e.g. "Dick Van" for "Dick Van Arsdale", since the raw
     historical source does this for some multi-word surnames).
  2. display_name from player_id_lookup.csv (the canonical current name
     from the full-history ID reference) -- catches players whose
     historical PlayerName predates a legal name change or uses an
     old/anglicized spelling the draft file doesn't (e.g. "Enes Kanter"
     -> draft file has "Enes Freedom"; "Nene Hilario" -> draft file has
     "Nenê"; "Efthimi Rentzias" -> draft file has "Efthimios Rentzias").

Draft-year proximity to the rookie season disambiguates players who
share a name after normalization.

NAME NORMALIZATION: lowercase, diacritics stripped via unidecode,
Jr./Sr./II/III/IV suffixes dropped, punctuation stripped -- including
the trailing "*" Basketball-Reference (and this project's own
player_metrics.csv) uses to mark Hall of Famers, e.g. "Bob Cousy*".

DRAFT-TO-ROOKIE GAP THRESHOLD: 9 years. A name match is only accepted
if the candidate's rookie season is within 9 years of their draft year.
This was widened from an initial 3-year threshold after investigation
found legitimate 4-9 year draft-to-debut gaps are common in the
1950s-1970s (military service, extended college eligibility, playing
overseas). A small number of much longer gaps (20-30 years) were
confirmed to be two different players sharing a name decades apart, NOT
real gaps -- 9 years was chosen to catch the former while staying clear
of the latter. Some real players exceed even this (Arvydas Sabonis:
drafted 1985/86, NBA debut 1995-96, an 11-year gap caused by being
unable to leave the Soviet/Lithuanian system) -- these are correctly
NAME-matched but flagged separately as "gap exceeds threshold" rather
than silently forced through, since loosening the threshold further to
catch them would risk re-introducing false collisions elsewhere (see
README on the 9-year choice).

DATA COVERAGE CEILING: player_metrics.csv's box-score source currently
only extends through SeasonStart 2024 (the 2023-24 season). Draft picks
from 2024 and 2025 have no possible rookie-season row yet -- flagged as
"no data yet (post-2024 draft class)", not a matching failure.

Run from a folder containing draft_history.csv, player_metrics.csv, and
player_id_lookup.csv:

    python match_draft_to_player_ids.py

Outputs:
    draft_rookie_seasons.csv -- successfully-matched picks, with the
                                 matched player_id and their rookie-season
                                 z-scores/ratios from player_metrics.csv
    draft_unmatched.csv      -- remaining unmatched picks, with a reason
                                 column: "no career", "no data yet
                                 (post-2024 draft class)", "no name
                                 match", "gap exceeds threshold", or
                                 "ambiguous candidates"
"""

import os
import re

import pandas as pd
from unidecode import unidecode

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DRAFT_PATH = os.path.join(HERE, "draft_history.csv")
METRICS_PATH = os.path.join(HERE, "player_metrics.csv")
ID_LOOKUP_PATH = os.path.join(PROJECT_ROOT, "player_id_lookup.csv")

GAP_THRESHOLD_YEARS = 9
DATA_COVERAGE_CEILING = 2024  # last SeasonStart in player_metrics.csv


def normalize_name(name):
    """Lowercase, strip diacritics, strip the '*' HOF marker and other
    punctuation, strip generational suffixes."""
    n = unidecode(str(name))
    n = n.rstrip("*").strip()
    n = re.sub(r"[.,']", "", n)
    n = re.sub(r"\s+(Jr|Sr|III|IV|II)$", "", n, flags=re.IGNORECASE)
    return n.lower().strip()


def main():
    for p in (DRAFT_PATH, METRICS_PATH, ID_LOOKUP_PATH):
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"Expected {os.path.basename(p)} at {p} -- run "
                "build_draft_history.py and compute_metrics.py first "
                "(and make sure player_metrics.csv was generated AFTER "
                "attach_player_ids.py added the player_id column -- "
                "re-run compute_metrics.py if in doubt). "
                "player_id_lookup.csv is expected at the project root."
            )

    draft = pd.read_csv(DRAFT_PATH)
    metrics = pd.read_csv(METRICS_PATH)
    id_lookup = pd.read_csv(ID_LOOKUP_PATH)
    print(f"Loaded draft_history.csv: {len(draft)} picks")
    print(f"Loaded player_metrics.csv: {len(metrics)} rows")
    print(f"Loaded player_id_lookup.csv: {len(id_lookup)} players")

    if "player_id" not in metrics.columns:
        raise ValueError(
            "player_metrics.csv has no player_id column -- run "
            "attach_player_ids.py, then re-run compute_metrics.py, "
            "before running this script."
        )

    # Rookie season = each player_id's earliest SeasonStart row.
    with_id = metrics[metrics["player_id"].notna()].copy()
    rookies = (
        with_id.sort_values("SeasonStart")
        .groupby("player_id", as_index=False)
        .first()
    )
    print(f"Rookie seasons extracted: {len(rookies)} unique player_ids")

    # Attach the canonical display_name from player_id_lookup.csv as a
    # second name candidate.
    rookies = rookies.merge(
        id_lookup[["player_id", "display_name"]], on="player_id", how="left"
    )

    rookies["_norm_metrics_name"] = rookies["PlayerName"].apply(normalize_name)
    rookies["_norm_lookup_name"] = rookies["display_name"].apply(normalize_name)
    draft["_norm_name"] = draft["Player"].apply(normalize_name)

    # Build a name -> candidates index covering BOTH name sources. A
    # given rookie row is indexed under both its metrics-name key and
    # its lookup-name key (often identical; the two-source approach only
    # matters when they differ).
    by_metrics_name = {name: grp for name, grp in rookies.groupby("_norm_metrics_name")}
    by_lookup_name = {name: grp for name, grp in rookies.groupby("_norm_lookup_name")}

    def get_candidates(norm_name):
        a = by_metrics_name.get(norm_name)
        b = by_lookup_name.get(norm_name)
        if a is None:
            return b
        if b is None:
            return a
        return pd.concat([a, b]).drop_duplicates(subset="player_id")

    matched_rows = []
    unmatched_rows = []

    def has_no_career(pick):
        return pd.isna(pick.get("G")) or pick.get("G", 0) == 0

    for _, pick in draft.iterrows():
        candidates = get_candidates(pick["_norm_name"])

        if candidates is None or len(candidates) == 0:
            if pick["draft_year"] >= DATA_COVERAGE_CEILING:
                reason = "no data yet (post-2024 draft class)"
            elif has_no_career(pick):
                reason = "no career"
            else:
                reason = "no name match"
            unmatched_rows.append({**pick.to_dict(), "reason": reason})
            continue

        gap = (candidates["SeasonStart"] - pick["draft_year"]).abs()
        within_gap = candidates[gap <= GAP_THRESHOLD_YEARS]

        if len(within_gap) == 1:
            match = within_gap.iloc[0]
            row = {**pick.to_dict(), **{
                "player_id": match["player_id"],
                "rookie_season": match["SeasonStart"],
                "rookie_age": match["Age"],
            }}
            extra_cols = [c for c in metrics.columns
                          if c not in ("SeasonStart", "PlayerName", "player_id", "source")]
            for c in extra_cols:
                row[c] = match.get(c)
            matched_rows.append(row)
        elif len(within_gap) == 0:
            if pick["draft_year"] >= DATA_COVERAGE_CEILING:
                reason = "no data yet (post-2024 draft class)"
            elif has_no_career(pick):
                reason = "no career"
            else:
                reason = "gap exceeds threshold"
            unmatched_rows.append({**pick.to_dict(), "reason": reason})
        else:
            unmatched_rows.append({**pick.to_dict(), "reason": "ambiguous candidates"})

    matched_df = pd.DataFrame(matched_rows).drop(columns=["_norm_name"], errors="ignore")
    unmatched_df = pd.DataFrame(unmatched_rows).drop(columns=["_norm_name"], errors="ignore")

    matched_df.to_csv(os.path.join(HERE, "draft_rookie_seasons.csv"), index=False)
    unmatched_df.to_csv(os.path.join(HERE, "draft_unmatched.csv"), index=False)

    print(f"\ndraft_rookie_seasons.csv: {len(matched_df)} matched picks "
          f"(of {len(draft)}, {len(matched_df)/len(draft)*100:.1f}%)")
    print(f"draft_unmatched.csv: {len(unmatched_df)} unmatched picks")
    if len(unmatched_df):
        print("\nUnmatched breakdown by reason:")
        print(unmatched_df["reason"].value_counts().to_string())


if __name__ == "__main__":
    main()

