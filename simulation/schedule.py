"""
Placeholder schedule generator.

The real 2026-27 schedule isn't out yet, so this builds a *structurally
realistic* 82-game schedule per team using the NBA's actual format:
  - 4 games vs each of the 4 division rivals            = 16 games
  - 4 games vs 6 "primary" same-conference non-division  = 24 games
  - 3 games vs the remaining 4 same-conference teams     = 12 games
  - 2 games vs each of the 15 other-conference teams     = 30 games
  Total                                                   = 82 games

Which 6 same-conference teams get the extra 4th game is picked
deterministically (rotates by division) since the real assignment isn't
public yet. Swap this module out for a real schedule loader once the
league releases it -- nothing downstream needs to change, since the
simulator just consumes a list of (home, away) games.
"""

from teams import TEAMS, TEAM_LIST


def _division_rivals(team):
    div = TEAMS[team]["division"]
    return [t for t in TEAM_LIST if TEAMS[t]["division"] == div and t != team]


def _other_conference(team):
    conf = TEAMS[team]["conference"]
    return [t for t in TEAM_LIST if TEAMS[t]["conference"] != conf]


def _divisions_by_conference():
    """{conference: {division: [team, team, ...]}} with teams ordered consistently."""
    out = {}
    for t in TEAM_LIST:
        conf = TEAMS[t]["conference"]
        div = TEAMS[t]["division"]
        out.setdefault(conf, {}).setdefault(div, []).append(t)
    for conf in out:
        for div in out[conf]:
            out[conf][div] = sorted(out[conf][div])
    return out


def build_matchup_counts():
    """
    Returns dict: {team: {opponent: num_games}} satisfying the real NBA
    82-game structure (see module docstring), with symmetric counts
    (counts[a][b] == counts[b][a] for every pair).

    Same-conference, different-division opponents (5 teams in each of the
    other two divisions = 10 total) are split 6-at-4-games / 4-at-3-games
    using a symmetric circulant rule between each pair of divisions: for
    team at index i in division X and team at index j in division Y (each
    division has exactly 5 teams, indices 0-4), the pair gets 4 games if
    (j - i) mod 5 is in {0, 1, 4} (i.e. circular distance <= 1), else 3
    games. This relation is symmetric by construction, and gives each
    team exactly 3 "four-game" + 2 "three-game" opponents per adjacent
    division = 6 fours + 4 threes across both adjacent divisions.
    """
    counts = {t: {} for t in TEAM_LIST}
    divs_by_conf = _divisions_by_conference()

    for team in TEAM_LIST:
        for opp in _division_rivals(team):
            counts[team][opp] = 4
        for opp in _other_conference(team):
            counts[team][opp] = 2

    for conf, divisions in divs_by_conf.items():
        div_names = list(divisions.keys())
        assert len(div_names) == 3, f"Expected 3 divisions in {conf}, got {len(div_names)}"
        for d_idx_x in range(3):
            for d_idx_y in range(d_idx_x + 1, 3):
                div_x = divisions[div_names[d_idx_x]]
                div_y = divisions[div_names[d_idx_y]]
                assert len(div_x) == 5 and len(div_y) == 5
                for i, team_x in enumerate(div_x):
                    for j, team_y in enumerate(div_y):
                        dist = (j - i) % 5
                        games = 4 if dist in (0, 1, 4) else 3
                        counts[team_x][team_y] = games
                        counts[team_y][team_x] = games

    for team in TEAM_LIST:
        total = sum(counts[team].values())
        assert total == 82, f"{team} has {total} games, expected 82"
        assert set(counts[team].keys()) == set(t for t in TEAM_LIST if t != team)

    return counts


def build_schedule(seed=None):
    """
    Builds a full season schedule as a list of (home_team, away_team) tuples.
    Home/away for each pairing is split as evenly as possible.
    """
    import random
    rng = random.Random(seed)
    counts = build_matchup_counts()
    games = []
    seen_pairs = set()

    for team_a in TEAM_LIST:
        for team_b, n_games in counts[team_a].items():
            pair = tuple(sorted((team_a, team_b)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            # n_games is symmetric (team_a's count vs b == b's count vs a)
            home_games_for_a = n_games // 2
            home_games_for_b = n_games - home_games_for_a
            # Randomize which side gets the extra home game when n_games is odd
            if n_games % 2 == 1 and rng.random() < 0.5:
                home_games_for_a, home_games_for_b = home_games_for_b, home_games_for_a

            for _ in range(home_games_for_a):
                games.append((team_a, team_b))  # team_a is home
            for _ in range(home_games_for_b):
                games.append((team_b, team_a))  # team_b is home

    rng.shuffle(games)  # placeholder ordering; not modeling schedule-day density yet
    return games


if __name__ == "__main__":
    sched = build_schedule(seed=42)
    print(f"Total games: {len(sched)} (expect 1230 = 30*82/2)")
    game_counts = {t: 0 for t in TEAM_LIST}
    for home, away in sched:
        game_counts[home] += 1
        game_counts[away] += 1
    for t in TEAM_LIST:
        assert game_counts[t] == 82, f"{t} has {game_counts[t]} games"
    print("All 30 teams confirmed at 82 games each.")
