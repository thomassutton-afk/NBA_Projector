"""
Module 2 (Aging Curve) -- Player ID attachment + authoritative age fix.

Uses player_id_seasons.csv (a full 1947-2026 player-season ID+age
lookup, provided directly by the project owner) to:

  1. Attach a stable player_id to every unified_player_seasons.csv row.
  2. Override Age with this source's age -- shown to be more reliable
     than the historical-anchor projection method in
     build_player_dataset.py's assign_ages(), which produced the
     "70-year-old rookie" bug (post-2017 debuts whose stripped name
     collided with an unrelated historical player, silently locking
     onto the wrong anchor and projecting an absurd age forward).

MATCHING, in five passes:
  Pass 1: (PlayerName, SeasonStart) -- resolves ~89% of rows directly.
  Pass 2: (PlayerName, SeasonStart, Age) -- resolves the ~26 known
          name-collision combos (two different real players, same
          name, same season), since every one of them has different
          ages.
  Pass 3: strip a trailing "*" (historical_clean.csv's Hall-of-Fame
          marker) and transliterate accents via unidecode (handles
          both simple accents AND non-Latin-derived letters like
          Icelandic eth/thorn, e.g. "Gudmundsson" for "Guðmundsson"),
          then retry (name, season).
  Pass 4: the raw historical source was found to TRUNCATE some player
          names -- either dropping a generational suffix entirely
          (e.g. "Larry Nance" for "Larry Nance Jr.") or cutting off
          after 2 words for longer names (e.g. "Dick Van" for "Dick
          Van Arsdale"). Retries as a case-insensitive, accent-
          normalized, word-boundary PREFIX match against the ID
          source (catches truncation) and separately as a first-word +
          last-word match ignoring any middle words (catches inserted
          middle names, e.g. "Kiwane Garris" vs "Kiwane Lemorris
          Garris"), each disambiguated by Age when multiple candidates
          exist for the same season.
  Pass 5: a small explicit alias table for confirmed genuine nickname/
          name-change cases that no automated rule can safely catch
          without risking a wrong match (e.g. "Luigi Datome" is known
          in the NBA as "Gigi Datome"; "Enes Kanter" legally changed
          his name to "Enes Kanter Freedom" -- the ID source uses his
          later name throughout). Each entry below was individually
          verified against age before being added -- this table is
          deliberately small and explicit rather than a fuzzy-matching
          rule, to avoid silently mismatching two different real
          people the way the original assign_ages() bug did.
  Anything left unmatched after all five passes is printed out
  explicitly.

Run from your aging/ folder, after rebuild_unified.py (and, if you've
run it, patch_pre1958_ages.py) have already produced
unified_player_seasons.csv, and with player_id_seasons.csv also
present in this folder:

    python attach_player_ids.py

Edits unified_player_seasons.csv in place: adds a `player_id` column,
overwrites `Age` wherever matched. Prints a full report.
"""

import os
import re
import pandas as pd
from unidecode import unidecode

HERE = os.path.dirname(os.path.abspath(__file__))
UNIFIED_PATH = os.path.join(HERE, "unified_player_seasons.csv")
ID_SEASONS_PATH = os.path.join(HERE, "player_id_seasons.csv")

# Pass 5: verified nickname / legal-name-change aliases. Each entry maps
# the historical_clean.csv name to the ID source's display_name.
# Individually verified against age before being added -- see docstring.
VERIFIED_ALIASES = {
    "Luigi Datome": "Gigi Datome",
    "Walter Tavares": "Edy Tavares",
    "Enes Kanter": "Enes Freedom",
    "Didier Ilunga-Mbenga": "D.J. Mbenga",
    "Efthimi Rentzias": "Efthimios Rentzias",
    "Taurean Waller-Prince": "Taurean Prince",
    "Vitor Faverani": "Vítor Luiz Faverani",
    "Mike Holton": "Michael Holton",
    "Jeffery Taylor": "Jeff Taylor",
    "Jeffrey Sheppard": "Jeff Sheppard",
    "James Phelan": "Jim Phelan",
    "C.J. McCollum": "CJ McCollum",
    "Juan Hernangomez": "Juancho Hernangómez",
    "Nene Hilario": "Nenê",
    "LaMark Baker": "Mark Baker",
    "Maury King": "Maurice King",
    "Robert Hawkins": "Bubbles Hawkins",
    "Wayne Englestad": "Wayne Engelstad",
    "Sheldon McClellan": "Sheldon Mac",
    "Nate Williams": "Jeenathan Williams",
}

# Rows confirmed to carry a KNOWN-WRONG age from the assign_ages() bug
# (same root cause as Kevin Porter Jr. etc.), where the ID source has no
# entry under this exact name for this season to auto-correct it from.
# Nulled out below rather than silently shipped -- a wrong age that
# LOOKS plausible (unlike the obvious 70+ cases) is more dangerous left
# in than flagged as missing. (SeasonStart, PlayerName) -> reason.
KNOWN_WRONG_UNRESOLVED = {}


def normalize_name(name):
    """Strip a trailing '*' (Hall-of-Fame marker) and transliterate
    accents/special letters via unidecode (handles simple accents AND
    non-Latin-derived letters like Icelandic eth/thorn)."""
    name = str(name).rstrip("*").strip()
    return unidecode(name)


def strip_suffix(name):
    return re.sub(r"\s+(Jr\.?|Sr\.?|III|IV|II)$", "", name).strip()


def main():
    for p in (UNIFIED_PATH, ID_SEASONS_PATH):
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"Expected {os.path.basename(p)} in {HERE} -- "
                "make sure rebuild_unified.py has run and "
                "player_id_seasons.csv is in this folder."
            )

    unified = pd.read_csv(UNIFIED_PATH)
    if "player_id" in unified.columns:
        unified = unified.drop(columns=["player_id"])  # allow safe re-run

    id_seasons = pd.read_csv(ID_SEASONS_PATH)
    print(f"Loaded unified_player_seasons.csv: {len(unified)} rows")
    print(f"Loaded player_id_seasons.csv: {len(id_seasons)} rows "
          f"({id_seasons['player_id'].nunique()} unique players)")

    # Collapse mid-season-trade duplicate (player_id, year) rows -- age
    # is already confirmed identical across a player's team-stint rows
    # within a season, so this collapse loses no information.
    id_collapsed = id_seasons.drop_duplicates(subset=["player_id", "year"]).copy()
    id_collapsed = id_collapsed.rename(
        columns={"display_name": "PlayerName", "year": "SeasonStart", "age": "Age"}
    )[["player_id", "PlayerName", "SeasonStart", "Age"]]

    # --- Pass 1: (PlayerName, SeasonStart) ---
    name_season_counts = id_collapsed.groupby(["PlayerName", "SeasonStart"])["player_id"].transform("nunique")
    pass1_lookup = id_collapsed[name_season_counts == 1]

    result = unified.merge(
        pass1_lookup.rename(columns={"Age": "matched_age"}),
        on=["PlayerName", "SeasonStart"], how="left"
    )
    pass1_hits = result["player_id"].notna()
    print(f"\nPass 1 (name + season) matched: {pass1_hits.sum()} of "
          f"{len(result)} ({pass1_hits.mean()*100:.1f}%)")

    # --- Pass 2: (PlayerName, SeasonStart, Age), for pass-1 leftovers ---
    ambiguous_pool = id_collapsed[name_season_counts > 1]
    n_ambiguous_combos = ambiguous_pool[["PlayerName", "SeasonStart"]].drop_duplicates().shape[0]
    print(f"Ambiguous name+season combos (2+ real players): {n_ambiguous_combos}")

    age_counts = ambiguous_pool.groupby(["PlayerName", "SeasonStart", "Age"])["player_id"].transform("nunique")
    pass2_lookup = ambiguous_pool[age_counts == 1]

    unmatched_mask = result["player_id"].isna()
    to_retry = result[unmatched_mask][["PlayerName", "SeasonStart", "Age"]]
    pass2_result = to_retry.merge(
        pass2_lookup, on=["PlayerName", "SeasonStart", "Age"], how="left"
    )
    n_pass2 = pass2_result["player_id"].notna().sum()
    print(f"Pass 2 (+ age) resolved an additional: {n_pass2} rows")

    pass2_ids = pass2_result["player_id"].values
    result.loc[unmatched_mask, "player_id"] = pass2_ids
    # pass 2 matched on Age directly (3-key match), so the "matched age"
    # for these rows is just their existing Age -- no change, by
    # construction. Only set it where a pass-2 match was actually found.
    pass2_found = pd.notna(pass2_ids)
    idx_unmatched = result.index[unmatched_mask]
    result.loc[idx_unmatched[pass2_found], "matched_age"] = result.loc[idx_unmatched[pass2_found], "Age"]

    got_id = result["player_id"].notna()
    print(f"\nTotal rows matched to a player_id (passes 1-2): "
          f"{got_id.sum()} of {len(result)} ({got_id.mean()*100:.1f}%)")

    # --- Pass 3: normalized name (strip '*', strip diacritics) + season ---
    id_collapsed["_norm_name"] = id_collapsed["PlayerName"].apply(normalize_name)
    norm_counts = id_collapsed.groupby(["_norm_name", "SeasonStart"])["player_id"].transform("nunique")
    pass3_lookup = id_collapsed[norm_counts == 1][["_norm_name", "SeasonStart", "player_id", "Age"]]

    unmatched_mask_3 = result["player_id"].isna()
    to_retry_3 = result[unmatched_mask_3][["PlayerName", "SeasonStart"]].copy()
    to_retry_3["_norm_name"] = to_retry_3["PlayerName"].apply(normalize_name)
    pass3_result = to_retry_3.merge(
        pass3_lookup, on=["_norm_name", "SeasonStart"], how="left"
    )
    n_pass3 = pass3_result["player_id"].notna().sum()
    print(f"Pass 3 (strip '*' + diacritics) resolved an additional: {n_pass3} rows")

    idx3 = result.index[unmatched_mask_3]
    result.loc[idx3, "player_id"] = pass3_result["player_id"].values
    result.loc[idx3, "matched_age"] = pass3_result["Age"].values

    got_id = result["player_id"].notna()
    print(f"\nTotal rows matched to a player_id (passes 1-3): "
          f"{got_id.sum()} of {len(result)} ({got_id.mean()*100:.1f}%)")

    # --- Pass 4: prefix match + first/last-word match (case-insensitive,
    # accent-normalized), disambiguated by Age when needed ---
    id_collapsed["_norm_lower"] = id_collapsed["_norm_name"].str.lower()
    id_collapsed["_norm_stripped_lower"] = id_collapsed["_norm_name"].apply(strip_suffix).str.lower()
    id_words = id_collapsed["_norm_name"].str.split()
    id_collapsed["_first_word"] = id_words.str[0].str.lower()
    id_collapsed["_last_word"] = id_words.str[-1].str.lower()

    def resolve_row(player_name, season, age, candidates_pool):
        norm = normalize_name(player_name)
        norm_stripped = strip_suffix(norm)
        norm_lower = norm.lower()
        norm_stripped_lower = norm_stripped.lower()
        words = norm.split()
        first, last = words[0].lower(), words[-1].lower()

        season_pool = candidates_pool[candidates_pool["SeasonStart"] == season]

        # (a) their name starts with ours (truncation case, e.g. Dick Van -> Dick Van Arsdale)
        prefix_hits = season_pool[season_pool["_norm_lower"].str.startswith(norm_lower)]
        # (b) our suffix-stripped name equals their suffix-stripped name
        #     (e.g. Wade Baldwin IV <-> Wade Baldwin, Marcus Morris Sr. <-> Marcus Morris)
        suffix_hits = season_pool[season_pool["_norm_stripped_lower"] == norm_stripped_lower]
        # (c) first word + last word match, ignoring inserted middle words
        #     (e.g. Kiwane Garris <-> Kiwane Lemorris Garris)
        word_hits = season_pool[(season_pool["_first_word"] == first) & (season_pool["_last_word"] == last)]

        candidates = pd.concat([prefix_hits, suffix_hits, word_hits]).drop_duplicates(subset=["player_id"])

        if len(candidates) == 0:
            return None, None
        if len(candidates) == 1:
            row = candidates.iloc[0]
            return row["player_id"], row["Age"]
        age_match = candidates[candidates["Age"] == age]
        if len(age_match) == 1:
            row = age_match.iloc[0]
            return row["player_id"], row["Age"]
        return None, None  # still ambiguous -- don't guess

    unmatched_mask_4 = result["player_id"].isna()
    n_pass4 = 0
    for idx in result.index[unmatched_mask_4]:
        pid, age = resolve_row(result.at[idx, "PlayerName"], result.at[idx, "SeasonStart"],
                                result.at[idx, "Age"], id_collapsed)
        if pid is not None:
            result.at[idx, "player_id"] = pid
            result.at[idx, "matched_age"] = age
            n_pass4 += 1
    print(f"Pass 4 (prefix / first+last word match) resolved an additional: {n_pass4} rows")

    # --- Pass 5: verified alias table ---
    unmatched_mask_5 = result["player_id"].isna()
    n_pass5 = 0
    alias_lookup = id_collapsed.copy()
    for idx in result.index[unmatched_mask_5]:
        pname = result.at[idx, "PlayerName"]
        if pname not in VERIFIED_ALIASES:
            continue
        alias_target = VERIFIED_ALIASES[pname]
        season = result.at[idx, "SeasonStart"]
        candidates = alias_lookup[
            (alias_lookup["PlayerName"] == alias_target) & (alias_lookup["SeasonStart"] == season)
        ]
        if len(candidates) == 1:
            row = candidates.iloc[0]
            result.at[idx, "player_id"] = row["player_id"]
            result.at[idx, "matched_age"] = row["Age"]
            n_pass5 += 1
    print(f"Pass 5 (verified alias table) resolved an additional: {n_pass5} rows")

    got_id = result["player_id"].notna()
    print(f"\nTotal rows matched to a player_id (all 5 passes): "
          f"{got_id.sum()} of {len(result)} ({got_id.mean()*100:.1f}%)")

    # --- Apply the age override ---
    age_changed = got_id & (result["Age"] != result["matched_age"])
    n_changed = age_changed.sum()
    print(f"Rows where Age actually changed as a result: {n_changed}")

    if n_changed > 0:
        changed = result[age_changed].copy()
        changed["age_diff"] = (changed["Age"] - changed["matched_age"]).abs()
        print(f"\nBiggest corrections (top 15 by size of change):")
        top = changed.sort_values("age_diff", ascending=False).head(15)
        print(top[["SeasonStart", "PlayerName", "Age", "matched_age", "age_diff"]]
              .rename(columns={"Age": "old_age", "matched_age": "new_age"})
              .to_string(index=False))

    result["Age"] = result["matched_age"].combine_first(result["Age"])
    result = result.drop(columns=["matched_age"])

    # Null out any row with a confirmed-wrong, unresolvable age rather
    # than silently ship a value known to be incorrect.
    for (season, name), reason in KNOWN_WRONG_UNRESOLVED.items():
        mask = (result["SeasonStart"] == season) & (result["PlayerName"] == name)
        if mask.any():
            result.loc[mask, "Age"] = pd.NA
            print(f"\nNulled out Age for {name} {int(season)}: {reason}")

    result.to_csv(UNIFIED_PATH, index=False)
    print(f"\nWrote unified_player_seasons.csv: {len(result)} rows, "
          f"now with player_id column "
          f"({result['player_id'].notna().sum()} rows have an ID)")
    print(f"Age coverage: {result['Age'].notna().mean()*100:.2f}%")

    # --- Anything STILL unmatched after both passes ---
    still_unmatched = result[result["player_id"].isna()]
    if len(still_unmatched) > 0:
        print(f"\n{'='*70}")
        print(f"STILL UNMATCHED after both passes ({len(still_unmatched)} rows) "
              f"-- these need manual research, name+season+age wasn't "
              f"enough to resolve them (or they're not in the ID source "
              f"at all):")
        print(f"{'='*70}")
        cols = ["SeasonStart", "PlayerName", "Age", "source"]
        print(still_unmatched[cols].drop_duplicates()
              .sort_values(["PlayerName", "SeasonStart"]).to_string(index=False))
    else:
        print("\nNo rows left unmatched after both passes.")


if __name__ == "__main__":
    main()
