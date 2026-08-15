"""
Module 2 (Aging Curve) -- Verification script.

Run this after build_player_dataset.py to sanity-check the unified
dataset against known, real facts -- independent of anything Claude
reports.

    python verify_player_dataset.py
"""

import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
AGING_DIR = os.path.join(HERE, "aging")


def main():
    print("=" * 70)
    print("PLAYER DATASET VERIFICATION")
    print("=" * 70)

    hist = pd.read_csv(os.path.join(AGING_DIR, "historical_clean.csv"))
    recent_with_age = pd.read_csv(os.path.join(AGING_DIR, "recent_with_age.csv"))
    recent_all = pd.read_csv(os.path.join(AGING_DIR, "recent_aggregated.csv"))
    unified = pd.read_csv(os.path.join(AGING_DIR, "unified_player_seasons.csv"))

    checks = []

    # 1. Season ranges are what we expect, no overlap
    checks.append((
        "Historical file covers 1950-2017, no later",
        hist["SeasonStart"].min() == 1950 and hist["SeasonStart"].max() == 2017
    ))
    checks.append((
        "Recent file covers 2018-2024, no earlier (no overlap w/ historical)",
        recent_all["SeasonStart"].min() == 2018
    ))

    # 2. Known real box score line: LeBron James, 2017-18 season
    #    (82 GP, 3026 total minutes, 2251 total points -- public record)
    lebron = recent_with_age[(recent_with_age.PlayerName == "LeBron James")
                              & (recent_with_age.SeasonStart == 2018)]
    lebron_ok = (
        len(lebron) == 1
        and lebron.iloc[0]["G"] == 82
        and abs(lebron.iloc[0]["MP"] - 3026) < 2
        and lebron.iloc[0]["PTS"] == 2251
    )
    checks.append(("LeBron James 2017-18 box score matches public record", lebron_ok))

    # 3. Age carried forward correctly increments by exactly 1 per season
    #    for a player spanning the historical/recent boundary
    curry_hist = hist[(hist.PlayerName == "Stephen Curry") & (hist.SeasonStart == 2017)]
    curry_recent = recent_with_age[(recent_with_age.PlayerName == "Stephen Curry")
                                    & (recent_with_age.SeasonStart == 2018)]
    age_increment_ok = (
        len(curry_hist) == 1 and len(curry_recent) == 1
        and curry_recent.iloc[0]["Age"] - curry_hist.iloc[0]["Age"] == 1
    )
    checks.append(("Age increments by exactly 1 across the 2017/2018 boundary (Curry)", age_increment_ok))

    # 4. No unexpected duplicate player-seasons in historical beyond the
    #    23 documented real name-collisions
    dupes = (hist.groupby(["SeasonStart", "PlayerName"]).size() > 1).sum()
    checks.append((f"Historical duplicate player-seasons == 23 (documented name collisions), got {dupes}",
                    dupes == 23))

    # 5. Minutes retention is in the expected ballpark (not a silent regression)
    total_mp = recent_all["MP"].sum()
    kept_mp = recent_with_age["MP"].sum()
    retention_pct = kept_mp / total_mp * 100
    checks.append((f"2018-2024 minutes retention is 95-100% (currently {retention_pct:.1f}%), "
                    f"consistent with the Balkan/Slavic-name birthdate recovery",
                    95 <= retention_pct <= 100))

    # 7. Spot-check the highest-profile recovered player: Luka Doncic's
    #    2018-19 rookie season age should be 19 (born Feb 28, 1999; Feb 1
    #    reference date -> still 19)
    luka = recent_with_age[(recent_with_age.PlayerName == "Luka Doncic")
                            & (recent_with_age.SeasonStart == 2019)]
    luka_ok = len(luka) == 1 and luka.iloc[0]["Age"] == 19
    checks.append(("Luka Doncic 2018-19 rookie season age == 19 (recovered via manual birthdate)", luka_ok))

    # 6. Unified dataset row count = historical + recent_with_age exactly
    checks.append((
        "Unified dataset row count == historical + recent_with_age",
        len(unified) == len(hist) + len(recent_with_age)
    ))

    print()
    all_passed = True
    for description, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status}] {description}")

    print()
    if all_passed:
        print("ALL CHECKS PASSED.")
    else:
        print("SOME CHECKS FAILED -- investigate before trusting this dataset further.")

    print()
    print("Summary:")
    print(f"  Historical (1950-2017): {len(hist):,} player-seasons")
    print(f"  Recent, age known (2018-2024): {len(recent_with_age):,} player-seasons "
          f"({retention_pct:.1f}% of available minutes)")
    print(f"  Recent, age missing: {len(recent_all) - len(recent_with_age):,} player-seasons "
          f"-- see missing_age_players.csv")
    print(f"  Unified total: {len(unified):,} player-seasons, "
          f"{unified['SeasonStart'].min():.0f}-{unified['SeasonStart'].max():.0f}")


if __name__ == "__main__":
    main()
