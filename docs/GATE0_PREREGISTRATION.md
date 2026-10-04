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
