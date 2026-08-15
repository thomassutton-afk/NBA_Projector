# NBA Standings Projector

A from-scratch system to project next season's NBA standings using
historical aging/minutes curves, offseason transactions, and Monte Carlo
season simulation.

Built piece-by-piece, module by module, with each piece validated on its
own before being wired into the next. This file tracks what's been
built, why we made the choices we made, and how to re-run everything.

---

## Project structure

```
NBA_Projector/
├── README.md                      <- this file
├── verify_simulation.py           <- run: sanity-check the simulator w/ fake ratings
├── verify_pythagorean.py          <- run: validate simulator vs. Pythagorean formula
├── simulation/
│   ├── teams.py                   <- 30 teams, conferences, divisions
│   ├── schedule.py                <- synthetic placeholder schedule generator (fallback only)
│   └── simulator.py               <- Monte Carlo season simulation engine
├── data/
│   ├── real_schedule.py           <- loader for the real 2025-26 schedule
│   ├── real_schedule_2025_26.json <- real 2025-26 schedule data (1,200 games)
│   └── real_pfpa_2025_26.py       <- real 2025-26 points-for/points-against per team
└── aging/                         <- Module 2's code + data
    ├── build_player_dataset.py       <- from-scratch build (TOT-collapse bug fixed this session)
    ├── merge_missing_ages.py
    ├── recover_collision_rows.py     <- patches historical_clean.csv (TOT-collapse fix)
    ├── rebuild_unified.py            <- regenerates unified_player_seasons.csv
    ├── patch_pre1958_ages.py         <- fills the 6 pre-1958 missing ages
    ├── attach_player_ids.py          <- attaches player_id, corrects ages (3-pass match)
    ├── compute_metrics.py            <- per-36 rates, TS%, era z-scores/ratios
    ├── historical_clean.csv
    ├── recent_aggregated.csv
    ├── recent_with_age.csv
    ├── missing_age_players.csv
    ├── unified_player_seasons.csv    <- the actual working dataset
    ├── player_metrics.csv            <- unified + all computed metric columns
    ├── player_id_lookup.csv          <- full 1947-2026 player ID lookup (project owner-provided)
    ├── player_id_seasons.csv         <- full 1947-2026 player-season ID+age+team data
    ├── source_age_data_1947_2026.csv
    └── recovered_birthdates_balkan_names.csv
```

---

## Status: Module 1 complete, Module 2 (Aging Curve) in progress

The overall project is being built in this order (see full reasoning
in the "Build order" section below):

- [x] **1. Simulation engine (Monte Carlo)** -- DONE, validated
- [ ] **2. Aging curve model** -- IN PROGRESS. Data foundation (unified
      player-season dataset, 1950-2024, 22,094 player-seasons) built
      and verified -- 100.00% age coverage achieved, 100.00% of rows have
      a stable player_id (see "Player ID attachment" below). Metric
      computation (per-36 rate stats, era normalization) DONE and
      validated against pre-built advanced stats -- see below. Curve
      fitting is the next actual step.
- [ ] 3. Rookie / new-player projection model
- [ ] 4. Data foundation (rosters, transactions, current stats)
- [ ] 5. Minutes / rotation model
- [ ] 6. Team aggregation model (player values -> team point differential)
- [ ] 7. Individual player projection engine (combines 2+3+5)
- [ ] 8. Full integration + calibration / backtesting

---

## How to re-run the verification scripts

Both scripts are self-contained -- just run them from the top-level
`NBA_Projector` folder:

```
python verify_simulation.py
python verify_pythagorean.py
```

Each takes about 8-10 seconds (running 10,000 simulated seasons) and
prints an automated PASS/FAIL summary so you don't have to eyeball the
numbers yourself.

- **`verify_simulation.py`** -- assigns a few teams fake strength ratings
  (very strong, very weak, neutral) and confirms the simulator produces
  sensible results: stronger teams win more, weaker teams win less, a
  neutral team lands near .500, and results show real game-to-game
  variance rather than repeating the same season.

- **`verify_pythagorean.py`** -- feeds the simulator last season's REAL,
  already-known point differential for all 30 teams, and compares the
  result against the standard Pythagorean win expectation formula. This
  validates the simulation engine's math against a trusted, established
  formula (not a projection of a future season).

---

## Module 1: Simulation Engine

### What it does
Given a "rating" (point differential) for each of the 30 teams and a
schedule, runs a full 80-to-82-game season thousands of times and
reports the resulting win-total distribution per team (mean, median,
10th/90th percentile, min/max).

### Key design decisions

**Direct point-differential simulation, not Log5.** We simulate an
actual scoring margin for each game (`Normal(expected_margin, sigma)`)
rather than converting straight to a single win probability. This
preserves point-differential information, which matters for NBA
tiebreakers/seeding and is consistent with how serious NBA projection
systems (e.g. FiveThirtyEight's RAPTOR/Elo) are built. Log5 is the more
standard choice in sports where margin doesn't carry much signal (e.g.
baseball); basketball isn't one of those sports.

**`SIGMA = 12.7`** (standard deviation of the simulated game margin).
This is not an arbitrary textbook number -- it comes from an independent
backtest of FiveThirtyEight's real, published NBA models (RAPTOR and
Elo), both of which had residual standard deviations of ~12.7-12.8
points against actual game outcomes.
*Flagged to revisit: calculate our own figure from fresh data once we
have enough of our own projections/results to check against.*

**`HOME_COURT_ADV = 2.5`** (points added to the home team's expected
margin). Placeholder value.
*Flagged to revisit: the same FiveThirtyEight backtest found real models
tend to OVERRATE home court advantage (predicted home teams winning
69-70% of games where the actual rate was ~55%), so this deserves its
own calibration pass rather than staying an assumption.*

**Real 2025-26 schedule, not synthetic.** Originally built a synthetic
placeholder schedule generator (`schedule.py`) matching the NBA's real
82-game format (division/conference weighting), but replaced it as the
default with the actual 2025-26 season schedule once we realized: (a)
every simulated season should use the SAME schedule -- only outcomes
should vary between simulations, not who's playing whom -- and (b) a
real schedule captures real-world scheduling patterns a formula alone
can't approximate.
*Known gap: the real schedule data has 80 games/team, not the full 82 --
7 In-Season Tournament knockout games were still "TBD" (unresolved
matchups) when this dataset was scraped in Oct 2025, before the season
started, so those 7 games were dropped. Not currently a problem; worth
patching to a complete 82-game dataset if exact precision ever matters.*

### Validation performed
1. **Fake-rating sanity check** (`verify_simulation.py`): confirmed
   ordering (better rating -> more wins), confirmed a neutral (0.0)
   rating lands at very close to a .500 record, confirmed real
   game-to-game variance exists (not a fixed/deterministic outcome).
2. **Real backtest vs. Pythagorean formula** (`verify_pythagorean.py`):
   fed the simulator all 30 teams' real, final 2025-26 point
   differentials and compared the simulator's mean win output against
   the standard Pythagorean win expectation for the same data.
   **Result: average absolute difference of 0.39 wins, max difference
   of 0.98 wins, across all 30 teams.** This is strong agreement between
   two independently-derived methods and gives real confidence the
   simulation engine's core mechanics are sound.
3. Both validations were re-run independently by the project owner (not
   just Claude) on their own machine, with matching results.

### What this module does NOT yet do
- Does not know any real 2026-27 team strength -- everything above used
  either fake test ratings or last season's real, already-known point
  differential. Actual next-season projections require the aging curve,
  minutes, and team aggregation modules (still to come).
- Does not yet incorporate rest/fatigue effects (e.g. back-to-back
  performance dips), which would require real game dates rather than
  just a list of matchups.
- Home court advantage is a single flat number for every team/arena,
  not team-specific.

### Reusable assets identified for later modules
- Project owner has a previously-built **NBA Elo rating system** that
  performed well last season -- planned for use in the team aggregation
  module (module 6), likely as a cross-check or blended input alongside
  our point-differential ratings.
- Project owner has a partially-built **NBA offseason tracker tool** --
  planned for use in the data foundation module (module 4).

---

## Module 2: Aging Curve Model (in progress)

### What it will do (once complete)
Model how a player's per-minute production changes with age, so that
Module 7 (individual player projection) can take a player's current
production and age them forward or backward a year. Built and
validated entirely against historical data -- no knowledge of any
specific 2026-27 player is needed for this module.

### Key design decisions

**No position-based curves.** Rejected outright -- positions are
increasingly blurry in the modern game and most players are some
blend of several. If a "role" adjustment is added later, it will be a
**continuous height variable**, not categorical position buckets --
still not started (see "Known gaps" below).

**Multiple stat categories, not one blended metric, but not
position-split either.** Approach: fit universal (non-position) curves
per stat category (scoring, rebounding, playmaking, etc.), and only
consider a secondary adjustment (e.g. by height) later if the data
supports it -- rather than slicing by category AND position AND age
all at once and risking curves fit on tiny, noisy buckets.

**Raw box score + minutes as the uniform foundation across all
eras, computing our own rate stats -- rather than relying on two
different pre-built "advanced stats" lineages.** Basketball-Reference-style
advanced metrics (PER, Win Shares, BPM, VORP) exist for 1950-2017 but
no clean equivalent could be found for 2018-present without either
scraping page-by-page or mixing in a *different* advanced-stat
methodology (stats.nba.com-style Off/Def Rating, Pace, etc.) at the
seam year -- which would create a fake "discontinuity" right at the
era boundary we actually want to test. Decision: drop the pre-built
advanced columns for curve-fitting purposes, compute our own per-36
rate stats and shooting efficiency uniformly from raw box score data
across the full 1950-present range instead.
*Required validation step (per project owner): once our own per-36 /
rate stats are computed, compare them against the original pre-built
PER/WS/BPM/VORP columns (still present in `historical_clean.csv`, just
unused for fitting) as a sanity check that our formulas are reasonable.
DONE -- see "Metric computation" section below.*

### TOT-collapse data-loss bug (found and fixed)

Picking the project back up after a break, `unified_player_seasons.csv`
was found to be a mislabeled copy of a different file (see below). While
rebuilding it from the intact `historical_clean.csv` + `recent_with_age.csv`,
a second, more serious bug was found in `clean_historical()`'s original
logic:

**Root cause:** the original TOT-collapse logic dropped every non-TOT
row for a (SeasonStart, PlayerName) group whenever *any* TOT row
existed in that group, assuming every row was a team-stint fragment of
one traded player. That assumption breaks when a completely different,
unrelated real player shares the exact same name in the exact same
season -- their legitimate single-team row gets silently deleted along
with the real trade fragments.

**Scope, verified against the raw source directly (re-fetched from
github.com/peasant98/TheNBACSV):** every one of the 2,123 (SeasonStart,
PlayerName) groups containing a TOT row was checked -- do the non-TOT
rows' stats actually SUM to the TOT row? Exactly 4 fail this test:
`Charles Jones` 1985, `Charles Smith` 1996, `Eddie Johnson` 1986,
`Marcus Williams` 2008 -- each had lost one unrelated player's entire
season (e.g. Charles Jones 1985: the real Basketball-Ref data has PHO
(age 23, a totally different Charles Jones) sitting alongside
TOT/CHI/WSB (age 27, the other Charles Jones's trade) -- only the age-23
player's row was getting deleted).

**Fix, in two parts:**
1. `recover_collision_rows.py` -- a targeted, one-time patch that adds
   the 4 specific missing rows back into `historical_clean.csv`, using
   the exact original raw values (age, team, full box score) re-fetched
   from source. Run once, after `historical_clean.csv` already exists.
2. `clean_historical()` in `build_player_dataset.py` itself was fixed
   for any future from-scratch rebuild: instead of an all-or-nothing
   "any TOT present -> drop everything else" rule, it now finds the
   actual SUBSET of non-TOT rows that sums to the TOT row (via
   brute-force subset-sum -- these groups are always small) and drops
   only that subset, leaving any row outside it untouched as its own
   separate player-season. Verified this produces the identical correct
   result (20,313 rows, same 4 recovered rows) whether run as the
   original from-scratch pipeline or as the targeted patch.

### Player ID attachment (`attach_player_ids.py`)

The project owner separately provided `player_id_lookup.csv` and
`player_id_seasons.csv` -- a full 1947-2026 player-season ID+age lookup
with a stable ID per real person (encodes debut year, e.g. `jacksja90`
vs `jacksja19` for the two different Jaren Jacksons). This closes a
much bigger problem than originally scoped:

**What it fixed:** `assign_ages()`'s historical-anchor matching (name
only, suffix-stripped) was found to silently produce wildly wrong ages
for post-2017 debuts whose name collided with an unrelated historical
player -- e.g. Kevin Porter Jr. was assigned age 69-72 (should be
19-22), Jaren Jackson Jr. assigned age 51-56 (should be 19-24). 9
players, 26+ player-seasons, errors up to 50 years -- all silently
excluded from the "missing age" bucket that would have resolved them
correctly, because the bad anchor match looked like a valid answer.

**Matching strategy, five passes, run in order:**
1. `(PlayerName, SeasonStart)` -- resolves ~89% of rows directly.
2. `(PlayerName, SeasonStart, Age)` for name+season collisions (2+ real
   players sharing a name in the same season -- the same ~26 cases
   already documented as a "residual name-collision" limitation).
   Checked directly: every one of the 26 known collision combos has
   two DIFFERENT ages, so this resolves all of them with zero manual
   research needed.
3. Strip a trailing `*` (historical_clean.csv marks Hall of Famers this
   way, e.g. `Wilt Chamberlain*`) and transliterate via `unidecode`
   (handles both simple accents and non-Latin-derived letters like
   Icelandic eth/thorn, e.g. `Guðmundsson` -> `Gudmundsson`), then
   retry name+season.
4. The raw historical source was found to TRUNCATE some names -- either
   dropping a generational suffix entirely (`Larry Nance` for `Larry
   Nance Jr.`) or cutting off after 2 words (`Dick Van` for `Dick Van
   Arsdale`). Retried three ways, case-insensitive and accent-
   normalized: (a) word-boundary prefix match (catches truncation),
   (b) suffix-stripped match on both sides (catches suffix mismatches
   in either direction -- `Wade Baldwin IV` vs the ID source's `Wade
   Baldwin`, `Marcus Morris Sr.` vs the ID source's plain `Marcus
   Morris`), (c) first-word + last-word match ignoring inserted middle
   words (`Kiwane Garris` vs `Kiwane Lemorris Garris`). Each
   disambiguated by Age when multiple candidates exist.
5. A small, individually-verified alias table (16 entries) for genuine
   nickname/mononym/legal-name-change cases no automated rule can
   safely catch without risking a wrong match -- e.g. `Luigi Datome` is
   known in the NBA as `Gigi Datome`; `Enes Kanter` legally changed his
   name to `Enes Kanter Freedom`; `Nene Hilario` is `Nenê` (mononym) in
   the ID source; `Maury King` is `Maurice King`. Every entry was
   confirmed by an exact age match (same year, same age) before being
   added, not just a plausible-looking name.

**Result: 100.00% of all 22,094 rows matched to a stable player_id** --
fully complete, no exceptions. This includes all 77 corrections from
the assign_ages() bug (all now fixed) and fully resolves every one of
the project's ~26 documented name-collision player-seasons with a
correct, evidence-backed player_id per row.

**Three names resolved via direct web research this session** (not
findable through any automated name-normalization rule, but real,
identifiable people once looked up): `Wayne Englestad` (1989) is
misspelled in the raw historical source -- his real name is `Wayne
Engelstad` (letters transposed), confirmed via Basketball-Reference/
Wikipedia, single 1988-89 season with the Denver Nuggets, 11 games.
`Sheldon McClellan` (2017) now goes professionally by `Sheldon Mac`
(legal birth name Sheldon Reeves McClellan) -- same pattern as the Enes
Kanter/Freedom case. `Nate Williams` (2024) -- the row that carried the
73-year-old-rookie bug -- is Jeenathan Lewis "Nate" Williams Jr., an
undrafted 2022 Buffalo product who bounced between Portland/Houston/
Rio Grande Valley in exactly this window; "Nate" is a nickname
unrelated enough to "Jeenathan" that no automated matching rule could
have found it, but it was confirmed by an exact age match (24, 2024)
against the ID source's `Jeenathan Williams` entry once identified.
This one was caught by the project owner, not found independently --
worth remembering that a "no automated match, exhausted the obvious
searches" conclusion isn't the same as "unfindable."

---

## Where things stand right now (read this first when picking the project back up)

**Module 2 data engineering + metric computation: DONE.** Everything
below this line is already built, run, and independently verified by
the project owner on their own machine:
- `unified_player_seasons.csv`: 22,094 player-seasons, 1950-2024, 100%
  age coverage, 100% player_id coverage -- no known remaining gaps.
- `player_metrics.csv`: per-36 rates, TS%, era z-scores/ratios for 8
  core categories, cross-checked against pre-built PER/TS%/WS/BPM
  (TS% matches to within 0.0005; Spearman correlations all positive
  and in the expected range).

**The actual next step: curve-fitting itself has NOT started.**
Everything below is still ahead:

1. **Re-run the era-trends chart and delta-method exploration on the
   now-fully-corrected data.** Both were built and run earlier in this
   session, but BEFORE the TOT-collapse fix and player_id/age
   corrections above -- `era_trends.png` and `delta_table.csv` /
   `delta_curves_compare.png` are now stale (only 91 rows changed, so
   unlikely to look meaningfully different, but not yet re-verified).
   Scripts already exist (`plot_era_trends.py`,
   `delta_curves_exploratory.py`) -- just need to be re-run and
   re-reviewed.
2. **Decide the min-n sample-size cutoff for age-transition buckets**
   in the delta method, using the comparison chart from step 1 (this
   was the original question this session set out to answer before
   the data-quality investigation took over).
3. **Decide the primary fitting window** -- 1976/1980-onward per
   earlier discussion, or something else, informed by the era-trends
   chart.
4. **Build the actual delta-method curve-fitting** (not the exploratory
   version) for all 8 core stat categories, incorporating the
   min-n/window decisions above.
5. **Empirically test the 2000/2010/2015 era-break candidates** against
   the fitted curves.
6. Only after all of the above: Module 2 is complete and Module 3
   (rookie/new-player projection) can start.



Run from `aging/`, after `unified_player_seasons.csv` exists:
```
python compute_metrics.py
```
Reads `unified_player_seasons.csv`, writes `player_metrics.csv`
(22,090 rows, 69 columns) with:

- **Per-36 rate stats** for every counting stat (PTS, TRB, ORB, DRB,
  AST, STL, BLK, TOV, PF, FG, FGA, 3P, 3PA, FT, FTA), computed directly
  from raw box score + minutes -- no pre-built rate stats used.
- **True Shooting %** (`PTS / (2 * (FGA + 0.44*FTA))`), chosen over
  eFG% specifically because it folds in free throw efficiency, which
  matters for aging (FT rate is one of the more age-sensitive shooting
  signals -- older players often draw fewer or more fouls as
  athleticism/craft trade off).
- **Era normalization for 8 core categories** (PTS, TRB, AST, STL,
  BLK, TOV, PF per-36, and TS%): both a **z-score** (vs. that season's
  minutes-weighted mean/stdev -- used for the actual curve-fitting,
  since it accounts for era-to-era changes in the *spread* of talent,
  not just the average) and a simpler **ratio-to-league-average** (kept
  alongside as an easier-to-eyeball sanity-check layer).
- **No minutes floor -- minutes-weighting instead.** Every player-season
  is kept; low-minute noise is handled by minutes-weighting the league
  mean/stdev used for normalization (a 40-minute season barely moves
  the league average; a 3000-minute season does), rather than picking
  an arbitrary cutoff and discarding real data.

**Known, expected gap: 1950 and 1951 (358 rows, 100% of those two
seasons) have no MP data.** Confirmed via direct check -- not a
pipeline bug. The NBA didn't track individual player minutes at all
until the 1951-52 season. Per-36 is undefined without minutes, so
these rows are kept in `player_metrics.csv` with every other column
intact, but all per-36/TS%/z-score/ratio columns are NaN. Doesn't
affect the primary 1976/1980+ fitting window; the full 1950+ range is
kept only as a robustness check per the design decision above.

**Cross-check validation (against `historical_clean.csv`'s pre-built
PER/TS%/WS/BPM, 1950-2017 portion only -- these columns don't exist
for 2018-2024):**
- **TS% direct comparison** (identical formula, so should nearly
  exactly match): mean absolute difference **0.00025**, max
  **0.00050**, zero rows differing by more than 0.01, across 20,219
  compared rows. This confirms the TS%/FGA/FTA/PTS computation is
  correct, not just internally consistent.
- **Rank correlation (Spearman)** of our simple per-36/TS% metrics
  against PER/WS/BPM (NOT expected to match numerically -- those
  metrics fold in defense, rebounding, usage, and team adjustments we
  don't have -- only expected to correlate positively and meaningfully):
  PTS/36 vs PER +0.75, vs WS +0.50, vs BPM +0.40; TS% vs PER +0.65, vs
  WS +0.62, vs BPM +0.63. All positive and in the expected range.
- **A methodology bug caught and fixed during this check:** the first
  version of this cross-check matched purely on (SeasonStart,
  PlayerName), which cross-joined the ~23 already-documented
  name-collision rows (two different real players sharing a name in
  the same season -- e.g. two different George Johnsons), comparing
  player A's computed stats against player B's pre-built stats. This
  produced a handful of spurious "large" TS% differences (up to 0.70)
  that were really just two different people's numbers being compared
  to each other, not a formula bug. Caught by noticing the merged row
  count (20,355) exceeded the source historical row count (20,309) --
  a merge producing MORE rows than either input has is itself a red
  flag worth chasing down. Fixed by excluding the 23 known collision
  keys from this specific comparison before merging (the TS%/per-36
  values for those rows are still computed and present in
  `player_metrics.csv` -- only the cross-check comparison excludes
  them, since matching them 1:1 against the right person isn't
  possible from name+season alone).
- **Spot checks against known seasons:** 2012-13 LeBron James (widely
  regarded as his most efficient scoring season) shows z = +2.69 on
  scoring, +2.18 on TS%. 2022-23 Nikola Jokić (MVP, title run) shows
  z = +2.22 on TS%. League-average TS% rises from .521 (2000) to .587
  (2024), matching the well-documented 3-point-era efficiency increase.
  These aren't formal validation, but real, named, correctly-behaving
  data points are a useful gut-check alongside the numeric checks above.

**Primary fitting window: 1976 (merger) or 1980 (Bird/Magic) onward,
full 1950+ history kept as a robustness check only.** Rationale:
league pace/rules changed too much pre-merger to trust directly in a
combined fit; normalizing against seasonal league averages (per
earlier discussion) should handle most of this, but a modern anchor
window is still the primary fit.

**Era-boundary testing: empirical, not assumed.** Project owner's
hypothesis is that pro basketball changed meaningfully around 2010.
Rather than hard-coding a 2010 split, the plan is to test multiple
candidate break years (2000, 2010, 2015) against the fitted curves and
report what the data actually shows, rather than assume the boundary.
*NOT YET DONE -- metric computation (the prerequisite) is now complete;
this depends on curve-fitting itself, which hasn't started.*

### Data sources
- **1950-2017 (`historical_clean.csv`):** originally scraped from
  Basketball-Reference, sourced via
  github.com/peasant98/TheNBACSV (`nbaNew.csv`). Includes Age directly
  per season, full box score, salary, and Basketball-Reference's own
  advanced metrics (PER, TS%, WS, BPM, VORP, etc. -- see "raw box
  score" decision above for why these aren't used directly).
- **2018-2024 (`recent_aggregated.csv` / `recent_with_age.csv`):**
  per-game box scores from github.com/NocturneBear/NBA-Data-2010-2024,
  aggregated up to season totals by `aging/build_player_dataset.py`. Only 2017-18 season onward is
  used from this source, to avoid double-counting the 2010-2017
  seasons already covered by the historical file.
- **Project owner's original spreadsheet** (41,456-row full-history
  file with playoff-advancement score, MVP/All-NBA/DPOY/awards data,
  stat-category-leader flags): NOT yet incorporated. Earmarked as a
  secondary cross-check / later enrichment source (e.g. weighting
  curves by star level), not part of the core age-vs-production curve.
  Also confirmed to have Age but NOT Minutes Played, which is why it
  isn't the primary source for this module.
- **Project owner's full-history age export** (`aging/source_age_data_1947_2026.csv`,
  28,811 rows, SeasonStart/PlayerName/Age, 1947-2026) -- used to close
  the 2018-2024 age gap (see "Known gaps" below for the full story,
  including an Excel encoding corruption that had to be worked around).
  Note: this saved copy still has literal `?` in place of a handful of
  Balkan/Slavic accented characters (unrecoverable cp1252 data loss,
  not a bug in how this file was saved here) -- the ~13 affected
  players were separately patched via `recovered_birthdates_balkan_names.csv`.

### How the player-season dataset is built
Run from the `NBA_Projector` root:
```
python aging/build_player_dataset.py     # downloads sources (cached after first run),
                                           # cleans, aggregates, merges -> aging/unified_player_seasons.csv
python verify_player_dataset.py          # independent automated PASS/FAIL checks (root-level, like the other verify_*.py scripts)
```
`aging/build_player_dataset.py` is fully self-contained -- it downloads its
own source files from GitHub each time it's run somewhere new (cached
locally in `aging/` after the first run), so no manual data-gathering is needed to
reproduce this step.

**Recovery scripts (all run from `aging/`, in this order, added after
the bugs documented above):**
```
python recover_collision_rows.py  # patches historical_clean.csv: adds back the
                                    # 4 rows lost to the TOT-collapse bug
python rebuild_unified.py         # regenerates unified_player_seasons.csv from
                                    # historical_clean.csv + recent_with_age.csv
                                    # (mirrors build_unified() exactly)
python patch_pre1958_ages.py      # fills the 6 pre-1958 rows with manually-
                                    # researched birthdates
python attach_player_ids.py       # attaches player_id + corrects ages using
                                    # player_id_lookup.csv / player_id_seasons.csv
                                    # (3-pass matching, see section above)
```
These aren't a replacement for `build_player_dataset.py` -- they're
narrow, standalone recovery steps, kept separate so each one's effect
is easy to verify independently rather than re-running (and
re-downloading) the whole pipeline. `build_player_dataset.py` itself
was also fixed (see "TOT-collapse data-loss bug" above) so a future
from-scratch rebuild produces the same corrected result directly.

**Metric computation (run from `aging/`, after all of the above):**
```
python compute_metrics.py       # unified_player_seasons.csv -> player_metrics.csv
                                  # (per-36 rates, TS%, era z-scores/ratios;
                                  # prints the PER/TS%/WS/BPM cross-check report)
```
NOTE: if you already ran `compute_metrics.py` before the TOT-collapse
fix and player_id attachment above, re-run it now -- the underlying
`unified_player_seasons.csv` has changed (4 rows recovered, 76+ ages
corrected), so `player_metrics.csv` and the era-trends chart from
earlier in this build log are now slightly stale and should be
regenerated.

`verify_player_dataset.py` checks (all currently passing):
- Historical file covers exactly 1950-2017, recent file 2018-2024
  onward, no overlap.
- A known real box score (LeBron James, 2017-18: 82 GP, 3026 minutes,
  2251 points) matches the aggregated data exactly.
- Age increments by exactly 1 across the 2017/2018 boundary for a
  player spanning both sources (Steph Curry).
- Historical duplicate player-seasons == 23 exactly (the documented
  name-collision cases, see below -- not a bug).
- 2018-2024 minutes retention is in the expected 50-65% range (current:
  57.1%) -- a regression outside this range would signal something
  broke silently.

### Known data-quality issues found and how they're handled
- **Traded players (multi-team seasons):** `nbaNew.csv` gives one row
  per team plus a combined "TOT" row for players traded mid-season.
  Resolved by keeping the TOT row and dropping the per-team splits
  whenever a TOT row is present.
- **Real name collisions:** the historical file has no unique player
  ID, only names. 23 player-seasons are genuinely two different real
  people sharing a name (e.g. two different NBA players both named
  "George Johnson," active in the same era) -- confirmed by checking
  that their ages diverge consistently rather than being a data error.
  Left as separate rows (not merged/deduplicated) since merging them
  would corrupt real data. This is a small residual risk for any
  future name-based matching against this file.
- **Suffix formatting mismatch between sources:** the historical file
  strips name suffixes ("Larry Nance" not "Larry Nance Jr."), the
  recent file keeps them. Fixed by matching on a suffix-stripped key.
  This introduces a *theoretical* risk of conflating a Sr./Jr. pair who
  were both active in the NBA at the same time -- checked the one real
  case in the data (Larry Nance Sr./Jr.) and confirmed no overlap in
  their careers, so the "most recent historical row" heuristic resolves
  correctly for now, but this isn't a guaranteed-safe rule in general.
- **`unified_player_seasons.csv` was found to be a mislabeled copy of a
  different file.** When picking this project back up, the working
  copy of `unified_player_seasons.csv` turned out to actually be
  `source_age_data_1947_2026.csv` (the external age-lookup file) saved
  under the wrong filename -- same exact row count (28,811), same
  3-column schema (`SeasonStart, PlayerName, Age`, no box score data),
  and the same documented literal-`?` Balkan-name corruption. It was
  never the real unified dataset; the actual box-score-bearing file
  just never got saved/exported under its real name. Caught by
  reconciling row counts (`historical_clean.csv` + `recent_with_age.csv`
  should sum to the unified row count, and didn't) and checking the
  file's encoding and header directly rather than trusting the
  filename. Fixed with `rebuild_unified.py` (see above) -- both
  `historical_clean.csv` and `recent_with_age.csv` were confirmed intact,
  so the real `unified_player_seasons.csv` was regenerated from those
  two with no methodology changes, and independently verified by the
  project owner on their own machine.

### Known gaps (flagged to revisit, same pattern as Module 1's
SIGMA/HOME_COURT_ADV placeholders)

**1. No height/weight data in either source.** Needed for the
"continuous size variable instead of position" idea. Searched
extensively for a full-history (1946-present), one-row-per-player bio
file; nothing clean found that's reachable from this environment
(closest options are Kaggle-hosted, capped at 2022, or single-season
snapshots). Deferred -- project owner has better direct access to
source this and will handle it when we return to this piece.

**2. 2018-2024 age gap -- RESOLVED.** Originally 752 players / 42.9% of
2018-2024 minutes had no age (true post-2017 debuts with no anchor in
the historical file). Project owner supplied their own full-history
(1947-2026) age-by-player-by-season export, which closed the gap to
99.99% of minutes via name+season matching (after normalizing accents
and periods -- e.g. "J.J. Redick" vs "JJ Redick", "OG Anunoby" vs
"O.G. Anunoby"). The remaining ~13 Balkan/Slavic-named players (whose
accented characters -- č, ć, đ, ş -- don't exist in the cp1252
encoding and were irrecoverably lost when the source file was
round-tripped through Excel) were closed by looking up their real
birthdates directly and computing age the same way (Feb 1 reference
date). **8 very low-minute fringe players remain unmatched** (Cam
Reynolds, Nate Williams, Matt Hurt, Mitchell Creek, Vincent Edwards,
Filip Petrusev, Vincent Hunter, Jamie Echenique) -- negligible, not
worth chasing further.

**3. Pre-1958 age gap -- RESOLVED.** After rebuilding
`unified_player_seasons.csv` (see mislabeled-file bug above), 6
player-seasons across 5 players were found still missing age: Bob
Schafer (1956, 1957), Don Bielke (1956), Frank Reddout (1954), Ken
McBride (1955), and Mike O'Neill (1953) -- all pre-1958, a different
root cause than the 2018-2024 gap above (these predate the historical
source file's own age data entirely, rather than being true post-2017
debuts). Project owner manually researched all 5 birthdates directly.
`patch_pre1958_ages.py` fills them in using the same Feb-1-of-season
age convention as the rest of the pipeline, closing overall age
coverage to **100.00%** -- independently verified by the project owner
on their own machine.

**A real bug caught and fixed during this recovery:** matching by
suffix-stripped name created a collision between Kenyon Martin Jr.
(active player, personId 1630231) and a stray "Kenyon Martin" entry
(his father, a retired veteran) in the supplied age file, producing
duplicate rows with an obviously wrong age (43-45 instead of 20-22).
Caught by checking for duplicate (personId, SeasonStart) pairs after
merging -- not by visual inspection -- which is exactly why that check
exists. This is the same class of risk flagged earlier with Larry
Nance Sr./Jr. -- suffix-stripped name matching against a second,
independently-sourced file is not fully collision-proof. Worth keeping
in mind if more external data gets merged in later.

**Root cause note for the encoding saga (for future reference):**
Excel's plain "CSV" export uses cp1252, which doesn't just mis-encode
characters outside Western European Latin-1 (recoverable) -- for
characters that don't exist in cp1252 at all (č, ć, đ, ş, and others
used in Balkan/Turkish names), it silently replaces them with a literal
`?`, which is unrecoverable data loss, not a fixable encoding mismatch.
"Save As -> CSV UTF-8" only helps if done on a file that hasn't already
been through a lossy cp1252 save -- re-saving an already-corrupted file
as UTF-8 just makes the corruption permanent-looking (valid UTF-8, but
wrong content). If this comes up again, re-export fresh from the
original source, not from an already-touched CSV.





We're building this "like a car" -- each component built and tested in
isolation before being wired together, starting with the pieces that
can be fully validated without depending on this specific, still-partly-
unknown offseason:

1. Simulation engine -- pure mechanics, testable with fake inputs
2. Aging curve model -- purely backward-looking, testable against history alone
3. Rookie/new-player model -- testable against past draft classes
4. Data foundation -- current rosters, transactions (needs live research)
5. Minutes/rotation model -- depends on module 4's rosters
6. Team aggregation model -- validate against *this* season's real stats first
7. Individual player projection engine -- combines 2 + 3 + 5
8. Full integration + backtesting on past seasons
