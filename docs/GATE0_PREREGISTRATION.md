# Gate 0 pre-registration (DRAFT, not run)

Written 2026-10-04, before any Gate 0 test has been computed. Bars below are CHOICE values: set now, from reasoning, not from results. Nothing is adopted until the owner has seen the results table. Part of `docs/GAMEPLAN_V2_PLAN.md` (section 7).

## 1. Strategy: three paths, one decision

| Path | What it is | Strength | Weakness |
|---|---|---|---|
| **A. Calls first** | Build lanes, the two calls and the receipt. Show a coach the card with the existing video playlist. Recognition is not measured | Fast; reuses the engine; tests whether two calls matter | Does not address pitch recognition, which is the stated north star |
| **B. Recognition first** | Build a minimal clip drill from TruMedia exports and test whether hitters can recognize the starter's pitches. Calls picked by a simple rule | Tests the north star soonest; needs no engine | Blocked on org video and hitters; highest evidence risk; says nothing about the plan or its measurement |
| **C. Two tracks, joined late** | Track 1 (public data, now): decide whether per-hitter calls exist at all. Track 2 (once exports are allowed): a fixed clip set by pitch shape for about 10 hitters, to learn whether recognition is a problem and for which shapes. Join them in the ranking only if both pass | Each half can ship alone; failure of one does not kill the other; the order follows what we can test now | Slower to a single finished product; two things to keep in step |

**Decision: C, with three changes to V2.**
1. **Make the first clip test independent of the calls.** Use a fixed set of clips by pitch shape, not clips picked by a hitter's calls. Our own evidence says per-hitter information is thin (a median of 0.2 of a hitter's own swings sits behind any cell; hitter-specific effects on plan calls were not distinguishable from zero in `docs/G1_EVIDENCE.md`). If personalization fails, recognition training on the starter's pitches can still be right for everyone. Tying the two together early risks killing the stronger half with the weaker one.
2. **Move a minimal clip test ahead of building the receipt and the hitter app.** It is the cheapest test of the north star: a splitter, a web page, about 10 hitters, 30 clips shown at a fixed cut point. If accuracy is at ceiling or no better than chance for everyone, the video loop is not worth building.
3. **Ship the receipt regardless.** Execution against intent works without video and without recognition. It is the part this project's evidence supports best.

## 2. Setup

- **Data:** `data/league` (full 2025 season, all pitchers), `data/b24` (2024 confirmation, 145 hitters), 2025 held-out by date. Public Triple-A and Florida State League data (Savant minor-league search, access check passed 2026-10-04) for the sample-size stress test.
- **Decision loss:** per pitch, the runs lost against the better option under the average-hitter model, as already computed by `mockup._decision_loss` (swing value minus take value, scale 1.257 wOBA per run). This is the "wrong decision" measure for every test. It is deliberately not the hitter's own model, so his tendencies are not graded against themselves.
- **Eligibility:** a hitter-start counts when the hitter has at least 300 earlier pitches that season (150 in the stress test).
- **Prediction rule:** every call is made from data before the game it is evaluated on. No future data.
- **Call ranking** for hitter h against starter s in game g: for each cell, value at stake = starter's usage of the cell (earlier starts, shrunk to league) x mean decision loss of the cell for this hitter group (average-hitter model) x his wrong-decision rate on the cell (earlier pitches, shrunk to league, K=40 as in `arsenal_fit`). The top cell where the right decision is a take and the top cell where it is a swing are the two calls.

## 3. Pitch shape definitions to compare (decision 1: explore all)

| ID | Definition | Cells |
|---|---|---|
| S1 | Pitch family (fastball, breaking, offspeed) x zone third in his own zone | 9 |
| S2 | S1 x side (in, middle, away relative to his body) | 27 |
| S3 | Pitch type code x zone third | about 24 |
| S4 | Data-driven shape cluster (k-means on velocity, induced vertical break, horizontal break, approach angle, per pitcher hand) x zone third | k=8 x 3 |
| S5 | Starter-relative shape (his primary fastball, hardest breaking pitch, primary offspeed) x zone third | 9 |

All five are reported for every test. Selection rule, fixed now: among definitions that pass test A, choose the one with the highest test B1 lift; ties go to the simpler one (S1, S5, S3, S2, S4). Only the chosen definition's 2024 confirmation counts. The others are reported, not hidden.

## 4. Tests and bars

**Test A, coverage.** Touches = pitches the starter throws to the hitter in that game that fall in his two call cells.
- PASS: median touches per hitter-start is at least 2.0.
- WIDEN: median 1.0 to 2.0. Next step is a coarser definition, a third call, or call groups.
- FAIL: median under 1.0.
Also reported: touches per hitter per month, and the share of hitter-starts with zero touches.

**Test B, stability.** Calls are made from the first half (through 2025-06-30) and judged on the second half, then repeated on 2024 (first half through 06-30).
- B1, lift. Wrong-decision loss per pitch on his call cells divided by the same on his other cells. PASS: ratio at least 1.25 with the 95% hitter-cluster bootstrap lower bound above 1.0.
- B2, personalization. B1 lift using his own error rates minus B1 lift using league error rates, with the starter and cell mass the same. PASS: difference above zero with the lower bound above zero. This is the test that justifies "per hitter".
- B3, reliability. Odd-game versus even-game correlation of his cell-level wrong-decision rates across hitters, Spearman-Brown corrected. PASS: at least 0.4 (the floor used for traits in `docs/traits_reliability.txt`).

**Test C, concentration.** Share of his total held-out decision loss that sits in the cells chosen by the top k calls, k = 1 to 5.
- PASS for k=2: at least 30% of his held-out loss, and at least 1.5 times the share two random cells of equal usage would carry (permutation baseline, 1,000 draws).
- Number of calls: the smallest k whose share reaches 50% of the k=5 share.

## 5. How the results are read

| Outcome | Decision |
|---|---|
| A pass, B1 pass, B2 pass | Per-hitter calls are justified. Proceed to Gate 1 |
| A pass, B1 pass, B2 fail | Calls are real but not personal. The product ranks the starter's pitches for everyone and uses recognition scores for personal emphasis |
| A widen | Try the next definition or a third call before judging |
| B1 fail or A fail | Two fixed calls per hitter do not work at this level. Fall back to the starter-level card plus the receipt |
| C fail at k=2 | Use the k the curve picks, or reduce the promise from "two calls" to "the pitch that matters" |

## 6. Predictions recorded in advance

- A: likely PASS or WIDEN. A hitter sees roughly 10 to 12 pitches from the starter, and a family x zone-third cell holds about 11% of them.
- B1: likely PASS on S1 and S5; weaker on S2 to S4 where cells are thin.
- B2: **the main risk.** The repository's own results found hitter-specific terms add little at these sample sizes. I expect B2 to be marginal or to fail. If it fails the product still stands (see section 5).
- B3: likely below 0.4 for fine definitions, above for coarse ones.
- C: S1 likely passes by construction because there are only nine cells. S2 and S4 are the real test.
- Single-A stress test (150 earlier pitches): all lifts shrink. A pass on MLB does not show a Visalia hitter's lane holds.

## 7. Stress test and confirmation

- 2024 confirmation of the chosen definition as above.
- Re-run the chosen definition on public Triple-A and Florida State League data, with the history requirement cut to 150 pitches, and report the same tables.
- Pass bars do not change.

## 8. Tunneling proof of concept (pre-registered separately, after A to C)

The separation measure (distance between a secondary pitch and the same pitcher's fastball at a fixed distance before the plate, from trajectory fields), tested by held-out log-loss gain on whiff and chase models after controlling for location, velocity, movement, count, pitcher and hitter, on 2025 with 2024 confirmation. The bar will be written to `docs/` before it runs. Earlier research here found no public evidence that tunneling explains hitter performance, so the prior is skeptical.

## 9. Outputs

Three tables (A, B, C) for each of the five definitions, plus the chosen-definition confirmation and stress test. Then stop and wait for the owner.

---

# Addendum 2026-10-04 (23:05 UTC), written before any test was run: three candidate paths, tested head to head

The owner asked for three possible approaches to be tested, with answers that can be checked, because pitch recognition is the north star and the output feeds both game-plan prep and the nightly video. This addendum replaces sections 4 and 7 where they differ and makes the evaluation rolling instead of half-season.

## The question, in plain baseball terms

For tonight's starter and a given hitter, which pitches should the prep and the video focus on so that the focus lands on pitches where hitters actually make costly mistakes? Three ways to choose, each tested on real games using only data from before the game.

## The three paths

| Path | How it picks the two focus pitches | What it says about the idea |
|---|---|---|
| **P, personal** | The starter's pitch types and locations ranked by how often he throws them, times how much this hitter has lost on them in earlier games (his loss shrunk toward the league, K=40 pitches) | The V2 plan as written |
| **L, starter-level** | The same ranking using the league's loss on each pitch, so every hitter gets the same two calls against this starter | The simple alternative: the prep is about the starter, not the hitter |
| **D, look-alike** | The starter's non-fastball pitches ranked by usage x league loss x how closely they follow the starter's fastball path early in flight (distance at 23.8 ft from the plate; closeness = 1 / (1 + distance in feet / 0.5)) | The recognition idea: train on the pitches that look like the fastball and still cost hitters |

P and L pick one take pitch and one swing pitch (the cell where the league's better option is to take, and the cell where it is to swing). D picks the top two non-fastball cells.

## Shape definitions run for every path

S1 pitch family x zone third in his own zone; S2 S1 x side (in, middle, away, split at 0.28 ft from the middle of the plate); S3 pitch type code x zone third; S4 data-driven shape cluster (k-means, k=8, on velocity, vertical break, horizontal break, approach angle) x zone third. S5 (starter-relative) is dropped from this round because it would label most pitches the same as S1; it is run only if S1 to S4 give a reason.

Zone thirds: height as a fraction of his own zone (bottom to top of that pitch's zone), below 1/3 low, 1/3 to 2/3 middle, above 2/3 high; pitches outside the zone count in the nearest third.

## Protocol

- **Data:** 2025 regular season, every pitch, from the league files already in the repository. 2024 full season downloaded from Savant for confirmation.
- **Referee for "mistake":** per pitch, the runs lost against the better option under the average-hitter model (the existing decision-loss calculation). The referee is fit on the full season; that is allowed because it defines truth, not a prediction. The calls never use data from the same game or later.
- **Rolling:** for every hitter-start from 2025-05-01 on, the two focus cells are chosen using only that season's earlier games. The hitter needs at least 300 earlier pitches seen, and the starter at least 2 earlier starts.
- **Tests, per path and shape definition:**
  1. **Coverage (A).** Pitches the starter throws to the hitter in that game that fall in his two focus cells. PASS: median at least 2.0. WIDEN: 1.0 to 2.0. FAIL: under 1.0.
  2. **Real weak spot (B1).** Mean loss per pitch on the focus cells divided by mean loss per pitch on his other cells, in the same game. PASS: at least 1.25 with the 95% hitter-cluster bootstrap lower bound above 1.0 (1,000 draws, fixed seed).
  3. **Is it him (B2).** B1 of path P minus B1 of path L. PASS: above zero with the lower bound above zero. This is the only test that supports "per hitter".
  4. **Reliability (B3).** Odd-game versus even-game correlation of the hitter's cell-level mean loss across hitters, Spearman-Brown corrected, cells with at least 10 pitches in each half. PASS: at least 0.4.
  5. **Concentration (C).** Share of the hitter's total loss in that game that falls in the two focus cells, next to the share of his pitches that fall there. PASS: loss share at least 30% and at least 1.5 times the pitch share.
- **Direct look-alike test (D-direct).** Does early-flight closeness to the starter's fastball predict more whiffs and more chase, after controlling for location, velocity, movement, approach angle, count, pitch family and the pitcher? Non-fastball pitches only. Fit on games before 2025-07-01, scored after; log-loss gain with a 95% hitter-cluster bootstrap interval; smaller distance must mean more whiffs/chase. PASS: lower bound above zero in the right direction, on 2025 and on 2024.

## How the results are read

| Result | Meaning |
|---|---|
| P passes A, B1, B2 | Per-hitter calls are supported. The V2 plan stands as written |
| L passes A, B1; P fails B2 | The prep should be about the starter, same for the lineup, and personal data should only set emphasis |
| D passes A, B1 and D-direct | Look-alike pitches are the right recognition target, and the video clips should be built around them |
| D-direct fails | Closeness to the fastball does not predict mistakes. Drop the disguise idea for now; plain cues |
| Nothing passes A | Two focus pitches a game is too thin at this level. Widen the focus (three calls or pitch groups) before building |
| A pass but B1 fails for all | The flagged pitches are not where mistakes are. Do not build prep on this |

If two paths pass, the simpler one wins unless the harder one beats it by the B2 test.

## Predictions on record

- P vs L: the repository's earlier results found hitter-specific terms add little. I expect B2 to be small or to fail, and L to be competitive.
- D: the earlier research found no public evidence that tunneling explains performance. I expect D-direct to be small. It could still pass at this sample size.
- A: coverage could land between 1 and 2 on the coarse shapes and below 1 on the fine shapes.

## Limits stated now

The referee is a model, not truth. Mistakes are measured against the average hitter, not against the best choice for this hitter. MLB pitchers and hitters are better than Single-A, so a pass on MLB is not a pass at Visalia; the public Triple-A and Florida State League stress test comes after this round. Nothing here tests that watching video improves recognition. That needs hitters and clips.

---

# Addendum 2 (2026-10-06), written before any of these runs: fixing the ranking after Gate 1

**Why.** Gate 1 (`docs/GATE1_WORKED_EXAMPLES.md`) showed that about half of the personal calls point at pitches the hitter handles *better* than the league does (for example Marte against Sears: both calls are fastballs where he loses less than the league). The current personal ranking multiplies how often the starter throws a pitch by the hitter's shrunk loss on it, so the starter's most-used pitches win whether or not the hitter struggles with them.

## Two new paths (same pitch definitions S1 to S4, same rolling protocol, same referee, same bars as Gate 0)

| Path | Rule | Meaning |
|---|---|---|
| **E, excess** | Score = starter usage x max(his shrunk loss minus the league loss, 0) on cells where he has at least 10 earlier pitches. One take call and one attack call, chosen as before. A cell where his excess is not above zero is never a call | "Pitches the starter throws that this hitter handles worse than most hitters" |
| **W, standing weak spots** | Score = his excess loss alone, on cells the starter throws at least 5% of the time and where he has at least 10 earlier pitches. One take call and one attack call | "His season-long weak spots, filtered by what tonight's starter throws". Gives continuity from night to night |

If a hitter has no cell with excess above zero against that starter, there is no call and the card says "no weak spot flagged". Reported: the share of hitter-starts that get at least one call.

## Tests and decision rules (fixed now)

- **Bars unchanged:** coverage (median touches of the called pitches at least 2.0), real weak spot (B1 at least 1.25 with the interval above 1.0), concentration (C), reliability (B3, already measured per definition).
- **New, B2 against the starter-level ranking:** E minus L and W minus L in B1 lift, same hitters, same resamples. PASS means the lower bound is above zero.
- **New, handled-better rate:** the share of calls on cells where his loss is at or below the league's. Reported for P, L, E and W. E and W are zero by construction; the point is to show how often P and L were pointing at pitches he is fine on.
- **Flagged share:** at least 60% of hitter-starts get a call (CHOICE).

| Result | Decision |
|---|---|
| E or W passes B1, coverage and B2 in 2025 and again in 2024, with flagged share at least 60% | Adopt the better of the two: W if its B1 beats E's with the interval above zero, otherwise E (simpler) |
| Neither passes B2 | Keep L as the ranking (same two pitches for the lineup against a starter) and show each hitter's standing weak spots as a separate line, not as the calls |
| Passes B2 but flagged share is under 60% | Adopt, but the card often says "no weak spot flagged"; discuss with the coach whether that is acceptable |
| Fails B1 | Weak-spot ranking does not find costly pitches; stay with L |

## Prediction on record

E and W will lift B1 over P and L, because they are chosen on how much worse than the league the hitter is, while P and L include cells where he is better. B2 may pass for the first time with a meaningful margin. Coverage will drop, because W and E call fewer cells and sometimes none.
