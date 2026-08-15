"""
Player ID system builder.

Reads the raw name/age/team/year export (AllPlayerDataforIDs.txt) and
produces a standalone player_id lookup table -- NOT yet wired into
unified_player_seasons.csv (that join happens later, once TJ decides
the two datasets agree well enough).

ID FORMAT
---------
    <last5><first2><debutYY>[tiebreaker]

  e.g. Bob Duffy, debuted 1947  ->  duffybo47
       Bob Duffy, debuted 1963  ->  duffybo63

This mirrors the Basketball-Reference-style ID (readable, first 5 of
last name + first 2 of first name) but replaces BR's arbitrary
"01/02/03" counter with the player's real NBA debut year. That's a
deliberate choice: the debut year is meaningful and already known
(rather than depending on ingestion order), and doing it this way lets
us reuse the SAME (YY) tags this source file already carries for
disambiguating same-name players -- e.g. "George Johnson (71)" vs
"George Johnson (73)" -- which is the exact collision TJ already
manually resolved during Module 2. No new disambiguation logic is
being invented; we're just formalizing what's already in the data.

If two different players happen to share both the last5+first2 stem
AND the same debut year (rare), a trailing letter tiebreaker (a, b, c)
is appended.

NAME CLEANING RULES
--------------------
- Strip a trailing "(YY)" disambiguation tag before computing the ID
  or storing the display name.
- Strip suffixes (Jr., Sr., II, III, IV, V) before picking the "last
  name" token, so e.g. "Gary Trent Jr." keys off "Trent", not "Jr".
- Fold accented/non-ASCII characters to plain ASCII (e.g. Bogdanović
  -> Bogdanovic) for the ID stem only -- the display name keeps the
  original accented spelling.
- Strip apostrophes/periods; hyphens are kept as letters removed (i.e.
  "Dejean-Jones" -> "dejeanjones") when building the stem.

OUTPUTS
-------
  player_id_lookup.csv   one row per unique player: id, display name,
                          debut year, last active year, career team
                          count, total season-rows
  player_id_seasons.csv  one row per player-team-season instance
                          (preserves in-season trades), with player_id
                          attached -- this is the piece a future join
                          into unified_player_seasons.csv would use
"""

import csv
import os
import re
import unicodedata
from collections import defaultdict

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}

SOURCE_PATH = os.path.join(os.path.dirname(__file__), "AllPlayerDataforIDs.txt")
LOOKUP_OUT = os.path.join(os.path.dirname(__file__), "player_id_lookup.csv")
SEASONS_OUT = os.path.join(os.path.dirname(__file__), "player_id_seasons.csv")

# ---------------------------------------------------------------------------
# KNOWN ALIASES / RENAMES
#
# TJ compiled the 1947-2023 seasons in one pass, then added 2024, 2025, and
# 2026 in later, separate collection passes. That gap is where a handful of
# real players ended up split across two different name-strings (a
# nickname/legal-name change, an accent-mark encoding difference, or a
# (YY) disambiguation tag that wasn't re-applied to the later rows). These
# were found via a targeted scan (last-name stem + age-continuity match)
# restricted to that 2024-2026 window, then manually verified one by one --
# NOT auto-applied, since the same heuristic also throws up false positives
# (different real players who happen to share a surname and a plausible
# age, e.g. "Kobe Brown" vs "Chaundee Brown Jr.").
#
# Rule used for picking the canonical name: prefer whichever name-string
# was already present in the original 1947-2023 compilation over the one
# introduced in a later patch, since the original pass is the more
# carefully-vetted one.
#
# Format: {raw name-string as it appears in the source file: canonical
# name-string to merge its rows into}. The canonical name's own tag/debut
# handling is unaffected; the alias's rows are simply folded in before ID
# assignment.
NAME_ALIASES = {
    "KJ Martin": "Kenyon Martin Jr.",         # rebranded display name
    "Lester Quiñones": "Lester Quinones",     # accent-mark encoding difference
    "Johnny Davis": "Johnny Davis (23)",      # (YY) tag not re-applied in later rows
    "Jeff Dowtin Jr.": "Jeff Dowtin",         # Jr. suffix not applied consistently
    "Brandon Williams": "Brandon Williams (22)",  # (YY) tag not re-applied in later rows
}

# Special case: a single row got filed under a DIFFERENT (and already
# occupied) name-string rather than a variant of its own name. The 2026
# Golden State Warriors row logged as "Nate Williams" actually belongs to
# the same player as "Jeenathan Williams" (2023-2025) -- he was already
# also known as "Nate Williams", and the source file's existing "Nate
# Williams" bucket happens to belong to an unrelated 1970s player. This
# needs a row-level split rather than a whole-name-string merge, since the
# "Nate Williams" bucket contains rows from BOTH real players.
SPLIT_ROWS = [
    {
        "from_name": "Nate Williams",
        "row": (2026, 26, "Golden State Warriors"),  # (year, age, team)
        "to_name": "Jeenathan Williams",
    },
]


def strip_debut_tag(raw_name):
    """
    'George Johnson (71)' -> ('George Johnson', 71)
    'Al Brightman'        -> ('Al Brightman', None)
    Returns the tag as a 2-digit int (as found in the source file) or
    None if the name has no tag.
    """
    m = re.match(r"^(.*)\s\((\d{2})\)$", raw_name.strip())
    if m:
        return m.group(1).strip(), int(m.group(2))
    return raw_name.strip(), None


def fold_ascii(s):
    """Fold accented characters to plain ASCII (Bogdanović -> Bogdanovic)."""
    normalized = unicodedata.normalize("NFKD", s)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def clean_stem_token(token):
    """Lowercase, ASCII-fold, and strip anything that isn't a-z."""
    token = fold_ascii(token)
    token = re.sub(r"[^A-Za-z]", "", token)
    return token.lower()


def split_first_last(display_name):
    """
    Splits a cleaned display name into (first_name_token, last_name_token)
    for ID-stem purposes, dropping trailing suffixes like Jr./III.
    """
    parts = display_name.split()
    # Drop a trailing suffix token (Jr., II, III, ...) if present
    while len(parts) > 1 and parts[-1].strip(".").lower() in SUFFIXES:
        parts = parts[:-1]
    if len(parts) == 1:
        # Single-token name (rare) -- use it for both slots
        return parts[0], parts[0]
    first = parts[0]
    last = parts[-1]  # last token of what remains (handles multi-word
    # surnames like "van Breda Kolff" reasonably -- takes "Kolff")
    return first, last


def compute_id_stem(display_name):
    first, last = split_first_last(display_name)
    last5 = clean_stem_token(last)[:5]
    first2 = clean_stem_token(first)[:2]
    return f"{last5}{first2}"


def load_raw_rows():
    with open(SOURCE_PATH, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        rows = [r for r in reader if r]
    return rows


def build_players():
    """
    Groups raw rows by the source file's name string (which already
    encodes same-name disambiguation via the (YY) tag). Returns:
      players: dict keyed by raw_name_string -> {
          display_name, tagged_debut_year, season_rows: [(age, team, year), ...]
      }
    """
    rows = load_raw_rows()
    players = defaultdict(lambda: {"season_rows": []})

    for name_raw, age, team, year in rows:
        display_name, tag_year = strip_debut_tag(name_raw)
        p = players[name_raw]
        p["display_name"] = display_name
        p["tag_year"] = tag_year
        p["season_rows"].append((int(age), team, int(year)))

    # --- Apply row-level splits first (peel specific rows out of a
    # name-string bucket that actually contains two different players) ---
    for split in SPLIT_ROWS:
        from_name, target_row, to_name = split["from_name"], split["row"], split["to_name"]
        year, age, team = target_row
        bucket = players[from_name]["season_rows"]
        match = (age, team, year)
        assert match in bucket, (
            f"Expected row {match} not found in '{from_name}' -- source "
            f"file may have changed, re-check SPLIT_ROWS."
        )
        bucket.remove(match)
        players[to_name]["season_rows"].append(match)
        # Re-derive display_name/tag_year for the "to" bucket in case this
        # is the first row ever added to it under this key (not the case
        # here, but keeps this general).
        display_name, tag_year = strip_debut_tag(to_name)
        players[to_name]["display_name"] = display_name
        players[to_name]["tag_year"] = tag_year

    # --- Apply whole-name-string aliases (fold an alias's rows into its
    # canonical name-string, then drop the alias as a standalone player) ---
    for alias_name, canonical_name in NAME_ALIASES.items():
        if alias_name not in players:
            continue
        alias_rows = players[alias_name]["season_rows"]
        players[canonical_name]["season_rows"].extend(alias_rows)
        display_name, tag_year = strip_debut_tag(canonical_name)
        players[canonical_name]["display_name"] = display_name
        players[canonical_name]["tag_year"] = tag_year
        del players[alias_name]

    return players


def resolve_debut_year(p):
    """
    Prefer the source file's own (YY) tag when present (it's a real
    2-digit year -- need to decide the century). Otherwise fall back to
    the earliest season year seen for this player.
    """
    years_seen = [r[2] for r in p["season_rows"]]
    min_year = min(years_seen)

    if p["tag_year"] is not None:
        # Resolve 2-digit tag to a full year using the closest century
        # to the years actually observed for this player.
        candidates = []
        for century_base in (1900, 2000):
            candidates.append(century_base + p["tag_year"])
        debut_year = min(candidates, key=lambda y: abs(y - min_year))
        return debut_year
    return min_year


def assign_player_id(display_name, debut_year, taken_ids):
    """
    Reusable going forward: given a player's display name and debut
    year, returns a player_id guaranteed not to collide with anything
    in `taken_ids` (a set that should include all previously-assigned
    IDs -- pass the loaded lookup table's ID column for new players).
    """
    stem = compute_id_stem(display_name)
    yy = debut_year % 100
    base_id = f"{stem}{yy:02d}"

    if base_id not in taken_ids:
        return base_id

    for letter in "abcdefghijklmnopqrstuvwxyz":
        candidate = f"{base_id}{letter}"
        if candidate not in taken_ids:
            return candidate

    raise RuntimeError(f"Exhausted tiebreaker letters for {display_name} ({base_id})")


def main():
    players = build_players()

    taken_ids = set()
    lookup_rows = []
    season_rows_out = []

    # Sort for deterministic tiebreaker assignment (by debut year, then name)
    resolved = []
    for name_raw, p in players.items():
        debut_year = resolve_debut_year(p)
        resolved.append((debut_year, p["display_name"], name_raw, p))
    resolved.sort(key=lambda x: (x[0], x[1], x[2]))

    for debut_year, display_name, name_raw, p in resolved:
        pid = assign_player_id(display_name, debut_year, taken_ids)
        taken_ids.add(pid)

        seasons = sorted(p["season_rows"], key=lambda r: r[2])
        teams = sorted(set(t for _, t, _ in seasons))
        last_year = max(y for _, _, y in seasons)

        lookup_rows.append({
            "player_id": pid,
            "display_name": display_name,
            "source_name_tag": name_raw,
            "debut_year": debut_year,
            "last_active_year": last_year,
            "num_teams": len(teams),
            "num_season_rows": len(seasons),
        })

        for age, team, year in seasons:
            season_rows_out.append({
                "player_id": pid,
                "display_name": display_name,
                "age": age,
                "team": team,
                "year": year,
            })

    with open(LOOKUP_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "player_id", "display_name", "source_name_tag",
            "debut_year", "last_active_year", "num_teams", "num_season_rows",
        ])
        writer.writeheader()
        writer.writerows(lookup_rows)

    with open(SEASONS_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "player_id", "display_name", "age", "team", "year",
        ])
        writer.writeheader()
        writer.writerows(season_rows_out)

    print(f"Unique players (per source file's own disambiguation): {len(lookup_rows)}")
    print(f"Total player-team-season rows: {len(season_rows_out)}")
    print(f"Unique player_ids assigned: {len(taken_ids)}")
    assert len(taken_ids) == len(lookup_rows), "ID count mismatch -- collision bug"
    print(f"\nWrote: {LOOKUP_OUT}")
    print(f"Wrote: {SEASONS_OUT}")


if __name__ == "__main__":
    main()
