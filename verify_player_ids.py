"""
Standalone verification script for the player ID system.

Run directly:  python verify_player_ids.py

Checks performed:
  1. Row-count integrity -- every raw row in the source file made it
     into player_id_seasons.csv, nothing dropped or duplicated.
  2. player_id uniqueness -- no two different players ended up sharing
     an ID.
  3. Age-jump scan -- for names WITHOUT a (YY) tag (i.e. the source
     file is claiming there's only one real player behind that name
     across all 80 years), check whether the age sequence across
     seasons is plausible for a single human being. A big unexplained
     age jump or an age going backwards over time is a red flag that
     a same-name collision may have been missed by the tagging.
  4. Tag-year sanity -- for names WITH a (YY) tag, confirm the
     resolved debut year is reasonably close to that player's earliest
     season row (catches century-resolution mistakes, e.g. tag "07"
     meaning 2007 vs 1907).
"""

import csv
import os
from collections import defaultdict

SOURCE_PATH = os.path.join(os.path.dirname(__file__), "AllPlayerDataforIDs.txt")
LOOKUP_PATH = os.path.join(os.path.dirname(__file__), "player_id_lookup.csv")
SEASONS_PATH = os.path.join(os.path.dirname(__file__), "player_id_seasons.csv")


def main():
    print("=" * 70)
    print("PLAYER ID SYSTEM VERIFICATION")
    print("=" * 70)

    with open(SOURCE_PATH, encoding="utf-8") as f:
        raw_rows = [r for r in csv.reader(f, delimiter="\t") if r]

    with open(LOOKUP_PATH, encoding="utf-8") as f:
        lookup_rows = list(csv.DictReader(f))

    with open(SEASONS_PATH, encoding="utf-8") as f:
        season_rows = list(csv.DictReader(f))

    checks_passed = True

    # --- Check 1: row count integrity ---
    print(f"\n[1] Row count integrity")
    print(f"    Raw source rows:        {len(raw_rows)}")
    print(f"    player_id_seasons rows: {len(season_rows)}")
    ok = len(raw_rows) == len(season_rows)
    checks_passed &= ok
    print(f"    {'PASS' if ok else 'FAIL'}: counts match")

    # --- Check 2: player_id uniqueness ---
    print(f"\n[2] player_id uniqueness")
    ids = [r["player_id"] for r in lookup_rows]
    ok = len(ids) == len(set(ids))
    checks_passed &= ok
    print(f"    {len(ids)} rows, {len(set(ids))} unique IDs")
    print(f"    {'PASS' if ok else 'FAIL'}: no duplicate IDs")

    # --- Check 3: age-jump scan for UNTAGGED names ---
    print(f"\n[3] Age-plausibility scan (untagged names only)")
    by_player = defaultdict(list)
    for r in season_rows:
        by_player[r["player_id"]].append((int(r["year"]), int(r["age"])))

    tag_lookup = {r["player_id"]: r["source_name_tag"] for r in lookup_rows}

    suspicious = []
    for pid, rows in by_player.items():
        name_tag = tag_lookup[pid]
        is_tagged = "(" in name_tag and name_tag.strip().endswith(")")
        if is_tagged:
            continue  # already explicitly disambiguated, skip
        rows_sorted = sorted(set(rows))
        if len(rows_sorted) < 2:
            continue
        # Check age is (roughly) monotonic non-decreasing year over year,
        # allowing for the same age across adjacent years but flagging
        # any backwards jump or a jump of 3+ years between consecutive
        # seasons on record (real players don't skip that much unless
        # there's a multi-year data gap, which we allow for loosely).
        for (y1, a1), (y2, a2) in zip(rows_sorted, rows_sorted[1:]):
            year_gap = y2 - y1
            age_gap = a2 - a1
            if age_gap < 0:
                suspicious.append((pid, tag_lookup[pid], y1, a1, y2, a2, "age decreased"))
            elif age_gap > year_gap + 1:
                suspicious.append((pid, tag_lookup[pid], y1, a1, y2, a2, "age jumped faster than years elapsed"))

    print(f"    Untagged players scanned: {sum(1 for pid in by_player if '(' not in tag_lookup[pid])}")
    print(f"    Suspicious cases found:   {len(suspicious)}")
    if suspicious:
        print(f"    (These MAY indicate a same-name collision the source file's")
        print(f"     (YY) tags didn't catch -- worth a manual look.)")
        for pid, name, y1, a1, y2, a2, reason in suspicious[:25]:
            print(f"      {name:<25} {y1} age {a1}  ->  {y2} age {a2}   [{reason}]")
        if len(suspicious) > 25:
            print(f"      ... and {len(suspicious) - 25} more")
    else:
        print(f"    PASS: no suspicious age patterns among untagged names")

    # --- Check 4: tag-year sanity for TAGGED names ---
    print(f"\n[4] Debut-year resolution sanity (tagged names only)")
    bad_resolution = []
    for r in lookup_rows:
        if "(" not in r["source_name_tag"]:
            continue
        debut = int(r["debut_year"])
        pid = r["player_id"]
        years = [y for y, a in by_player[pid]]
        min_year = min(years)
        if abs(debut - min_year) > 5:
            bad_resolution.append((r["source_name_tag"], debut, min_year))
    print(f"    Tagged players checked: {sum(1 for r in lookup_rows if '(' in r['source_name_tag'])}")
    print(f"    Debut year far (>5) from earliest season row: {len(bad_resolution)}")
    if bad_resolution:
        for name, debut, min_year in bad_resolution[:15]:
            print(f"      {name}: resolved debut {debut}, earliest row seen {min_year}")
    else:
        print(f"    PASS: all tagged debut years resolve sensibly")

    print("\n" + "=" * 70)
    if checks_passed and not suspicious and not bad_resolution:
        print("ALL CHECKS PASSED.")
    else:
        print("Some checks need a look -- see flagged rows above.")
        print("(Checks 1 and 2 are structural and must pass; checks 3 and 4")
        print(" are advisory flags for manual review, not hard failures.)")


if __name__ == "__main__":
    main()
