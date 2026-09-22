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

# Manually verified overrides for (draft_year, Pk) picks the automatic
# matching correctly refused to guess at (multiple real same-named
# players within the 9-year gap window). Each was confirmed against a
# real biography, not just picked as "the nearest year" -- several are
# deliberately NOT the nearest-gap candidate, because the nearest one
# was already the correct match for a DIFFERENT draft pick of the same
# name in the same research pass. See git history / conversation log
# for the case-by-case research behind each entry.
DRAFT_PICK_OVERRIDES = {
    (1954, 8): "turneja55",     # Jack Turner, Western Kentucky
    (1961, 10): "turneja62",    # Jack Turner, Louisville
    (1970, 9): "johnsge71",     # George Johnson, Stephen F. Austin
    (1970, 79): "johnsge73",    # George Johnson, Dillard -- debut delayed to 1972-73;
                                 # NOT the nearest-gap candidate (that's johnsge71,
                                 # already correctly claimed by the 1970 Pk9 above)
    (1977, 49): "johnsed78",    # Eddie Johnson, Auburn
    (1978, 12): "johnsge79",    # George Johnson, St. John's
    (1978, 4): "richami79",     # Michael Ray Richardson, Montana -- hand-sourced,
                                 # see recover_michael_ray_richardson.py
    (1979, 165): "jonesch84",   # Charles Jones ("Gadget"), Albany State
    (1981, 29): "johnsed82",    # Eddie Johnson, Illinois
    (1984, 36): "jonesch85",    # Charles Jones, Louisville -- NOT the nearest-gap
                                 # candidate (jonesch84, gap=0); his real rookie
                                 # season is 1984-85, already correctly identified
                                 # once recover_collision_rows.py restored his
                                 # dropped rookie row
    (1988, 3): "smithch89",     # Charles Smith, Pittsburgh
    (1989, 13): "smithmi90",    # Michael Smith, BYU
    (1994, 35): "smithmi95",    # Michael Smith, Providence
    (1995, 48): "davisma96",    # Mark Davis, Texas Tech
    (1997, 26): "smithch98",    # Charles Smith, New Mexico
    (2006, 22): "willima07",    # Marcus Williams, UConn
    (2007, 33): "willima08",    # Marcus Williams, Arizona -- NOT the nearest-gap
                                 # candidate (willima07, gap=0); waived by the
                                 # Spurs before playing, real NBA debut was 2008
                                 # with the Clippers
    # Nickname / name-form mismatches the two-source name matching
    # didn't catch -- verified real players with a real NBA career,
    # just filed under a different name than either source uses:
    (1951, 56): "mcguial52",    # Al McGuire -- listed as "Alfred McGuire*"
    (1962, 1): "mcgilbi63",     # Billy McGill -- listed as "Bill McGill"
    (2018, 52): "edwarvi19",    # Vince Edwards -- row existed but never got a
                                 # player_id from attach_player_ids.py; direct override
    (2020, 52): "martike21",    # KJ Martin -- listed everywhere as "Kenyon Martin Jr."
}

# Confirmed via draft_history.csv's own blank career-stat columns: these
# picks never played a single NBA game. The generic matching correctly
# has no candidate for them (there IS no career to match), but they were
# being mislabeled "ambiguous candidates" because that branch never
# checked games-played before flagging ambiguity -- see has_no_career().
CONFIRMED_NO_CAREER_OVERRIDES = {
    (1976, 125),  # Mike Davis, Bradley
    (1983, 104),  # Charles Jones, Oklahoma
    (1983, 196),  # Charles Jones, Marshall
}

# Confirmed via direct research: these picks have a real NBA career, but
# it started well after our player_metrics.csv's SeasonStart 2024
# coverage ceiling -- international "draft-and-stash" picks or an
# injury that wiped out what would have been their first eligible
# season. The generic ceiling check only catches this when draft_year
# itself is 2024+; these were drafted earlier but genuinely debuted
# late, so they need a direct override to get the right reason label.
CONFIRMED_DELAYED_DEBUT_OVERRIDES = {
    (2022, 52): "Karlo Matković debuted 2024-25 after two extra years in Europe",
    (2022, 56): "Luke Travers debuted 2024-25 after two extra years in the Australian NBL",
    (2023, 53): "Jaylen Clark missed all of 2023-24 with a torn Achilles; debut Jan 2025",
}


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
    overrides_applied = 0

    def has_no_career(pick):
        return pd.isna(pick.get("G")) or pick.get("G", 0) == 0

    def build_matched_row(pick, player_id, rookie_row):
        row = {**pick.to_dict(), **{
            "player_id": player_id,
            "rookie_season": rookie_row["SeasonStart"],
            "rookie_age": rookie_row["Age"],
        }}
        extra_cols = [c for c in metrics.columns
                      if c not in ("SeasonStart", "PlayerName", "player_id", "source")]
        for c in extra_cols:
            row[c] = rookie_row.get(c)
        return row

    rookies_by_id = rookies.set_index("player_id")

    for _, pick in draft.iterrows():
        pick_key = (int(pick["draft_year"]), int(pick["Pk"]) if pd.notna(pick["Pk"]) else None)

        # Manually verified overrides take priority over everything else.
        if pick_key in DRAFT_PICK_OVERRIDES:
            player_id = DRAFT_PICK_OVERRIDES[pick_key]
            if player_id in rookies_by_id.index:
                matched_rows.append(build_matched_row(pick, player_id, rookies_by_id.loc[player_id]))
                overrides_applied += 1
                continue
            # Player_id doesn't exist yet (e.g. Michael Ray Richardson's
            # rows haven't been added to this run's player_metrics.csv) --
            # fall through to normal handling rather than silently drop.

        if pick_key in CONFIRMED_NO_CAREER_OVERRIDES:
            unmatched_rows.append({**pick.to_dict(), "reason": "no career"})
            continue

        if pick_key in CONFIRMED_DELAYED_DEBUT_OVERRIDES:
            unmatched_rows.append({**pick.to_dict(), "reason": "no data yet (delayed NBA debut beyond 2024)"})
            continue

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
            matched_rows.append(build_matched_row(pick, match["player_id"], match))
        elif len(within_gap) == 0:
            if pick["draft_year"] >= DATA_COVERAGE_CEILING:
                reason = "no data yet (post-2024 draft class)"
            elif has_no_career(pick):
                reason = "no career"
            else:
                reason = "gap exceeds threshold"
            unmatched_rows.append({**pick.to_dict(), "reason": reason})
        elif has_no_career(pick):
            # Multiple same-named candidates exist, but THIS specific
            # draft pick never actually played -- there's nothing to
            # disambiguate, since no career means no rookie season to
            # match at all.
            unmatched_rows.append({**pick.to_dict(), "reason": "no career"})
        else:
            unmatched_rows.append({**pick.to_dict(), "reason": "ambiguous candidates"})

    matched_df = pd.DataFrame(matched_rows).drop(columns=["_norm_name"], errors="ignore")
    unmatched_df = pd.DataFrame(unmatched_rows).drop(columns=["_norm_name"], errors="ignore")

    matched_df.to_csv(os.path.join(HERE, "draft_rookie_seasons.csv"), index=False)
    unmatched_df.to_csv(os.path.join(HERE, "draft_unmatched.csv"), index=False)

    print(f"\n{overrides_applied} manually-verified overrides applied "
          f"(see DRAFT_PICK_OVERRIDES)")
    print(f"draft_rookie_seasons.csv: {len(matched_df)} matched picks "
          f"(of {len(draft)}, {len(matched_df)/len(draft)*100:.1f}%)")
    print(f"draft_unmatched.csv: {len(unmatched_df)} unmatched picks")
    if len(unmatched_df):
        print("\nUnmatched breakdown by reason:")
        print(unmatched_df["reason"].value_counts().to_string())


if __name__ == "__main__":
    main()

