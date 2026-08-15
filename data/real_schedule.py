"""
Loads the real 2025-26 NBA regular-season schedule as a fixed list of
(home, away) tuples, for use as the FIXED schedule across every Monte
Carlo simulation (only game outcomes vary between sims, not who plays
whom).

Source: scraped from the official NBA schedule API in Oct 2025, before
the season began (github.com/moizk/nba-schedule-2025-26). 7 In-Season
Tournament knockout games were dropped because their participating teams
were still TBD at scrape time, so each team has 80 games here rather
than the full 82. Good enough for testing simulator mechanics against a
real, fixed schedule; not a substitute for a complete dataset later.
"""

import json
import os

DATA_PATH = os.path.join(os.path.dirname(__file__), "real_schedule_2025_26.json")


def load_real_schedule():
    with open(DATA_PATH) as f:
        games = json.load(f)
    return [(g["home"], g["away"]) for g in games]


if __name__ == "__main__":
    from collections import defaultdict
    sched = load_real_schedule()
    print(f"Loaded {len(sched)} games")
    counts = defaultdict(int)
    for home, away in sched:
        counts[home] += 1
        counts[away] += 1
    for t in sorted(counts):
        print(t, counts[t])
