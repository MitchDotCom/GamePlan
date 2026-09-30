# Traceability: what is published, what is mine, and how each piece was tested

Evidence levels used below:
- **PUBLISHED**: the method or value comes from a published source (links in `docs/METHODOLOGY_AUDIT.md`; found via web search, primary pages not opened, so this is "matches what search summaries of the source say").
- **STANDARD**: a standard statistical technique, not baseball-specific.
- **MINE**: designed here. No publication behind it. Its only support is the out-of-sample tests listed.
- **UNPROVEN**: a claim nobody, including this project, has evidence for yet.

| Component | Level | Published precedent | How it was tested here | Status |
|---|---|---|---|---|
| wOBA weights and scale (1.257) | PUBLISHED | FanGraphs Guts 2025 | pinned by test; league wOBA from raw events with those weights = .3157 vs FanGraphs .314 | verified |
| Run value of a strike / ball by count | PUBLISHED | Tango run-expectancy tables; Savant count values | 3 published values matched within 10% | verified |
| Swing vs take valued by outcome probabilities x count values | PUBLISHED | Savant Swing/Take; Baseball Prospectus StuffPro/PitchPro; TJStats batter decision value | external replication vs Savant's per-hitter swing/take run values (`docs/external_check.txt`) | in progress |
| xwOBA on contact | PUBLISHED | Statcast expected stats | used as supplied by Savant, not recomputed | as published |
| Squared-up, VAA, IVB definitions | PUBLISHED | MLB glossary; FanGraphs VAA primer | formulas match; IVB league means match published (15.8 vs about 16; -10.3 vs about -10) | verified |
| Time-through-the-order effect | PUBLISHED | Tango/Lichtman, Baseball Prospectus, Brill et al. | league-wide +6.9 then +12.9 wOBA points vs published +8 to +13 per time | reproduced |
| Called-strike probability by location and count | PUBLISHED | Baseball Prospectus called-strike models; umpire count-effect literature | held-out Brier .0470 vs .0523 stand-in; borderline strike rate by strikes matches actual | validated (simpler than BP's model) |
| Shrinking small samples toward the league (empirical Bayes) | STANDARD | Efron-Morris; Robinson's baseball application; Carleton stabilization | hitter-level term improved held-out skill 2x to 6x at 50 to 400 swings; k chosen within published stabilization scale | validated |
| Time-split validation, cluster bootstrap, Holm and BH corrections | STANDARD | general statistics | applied to headline tests; no headline test survives Holm | applied |
| Nearest-neighbour / kernel model of outcomes by location and pitch shape | MINE (with precedent) | nearest-neighbour xwOBA models exist (TJStats); no published hitter-by-shape kernel model | held-out prediction skill vs league model: whiff +2.6%, xwOBAcon +1.3%; year over year +2.8% / +0.9% | validated as prediction |
| Confidence gating of calls (call only if the 90% bound clears zero) | MINE | none | confident calls separate swing/take by +0.054 (GO) and +0.066 (NO_GO) runs more than thin ones | validated |
| Count recalibration | MINE | none | pending (tuning run) | pending |
| Base-out and score/inning policy weights | MINE (fit from published run expectancy) | Savant offers context-neutral and leveraged run value | overall no gain; positive on changed pitches in two spots, uncorrected for multiple tests; score/inning null | weak |
| Coach-report trust ledger | MINE | none | mechanism tested by simulation only | unvalidated with real coaches |
| Plan-level individualization (hitter-specific calls beat league calls) | UNPROVEN | none | +0.047 runs [-0.001, +0.099] two-way bootstrap; fails its criterion | unproven |
| Following the plan improves outcomes | UNPROVEN | none anywhere | cannot be tested on MLB data (observational, selection bias); needs a pilot | unproven |

## What "prediction" versus "better calls" means, plainly

- **Prediction (validated):** for a pitch in a given place with a given shape, this model forecasts how likely a given hitter is to miss and how hard he hits it better than a league-average forecast does. Tested on swings the model never saw, including next season.
- **Better calls (not proven):** whether telling a hitter "swing / take" from that forecast beats telling him what the league-average forecast says. The test of that has a positive point estimate and an interval that just includes zero.
- **Helps when followed (not provable here):** whether a hitter who follows the card produces better results than he would have. Nobody has evidence for this for any swing-decision tool; only an experiment with real hitters can supply it.

## What would make this ironclad, in order

1. Every constant carries source and status (done: `constants.py`, pinned by tests).
2. Outputs reproduce published numbers each season, automatically (benchmarks exist; wire them into a scheduled check).
3. Independent replication of the headline metric against a published one (Savant swing/take; in progress).
4. Outside review by someone who did not build it: a statistician and a baseball-analytics reader, working from this document and the code.
5. A pre-registered pilot (`docs/PILOT_DESIGN.md`) for the "helps when followed" claim, with the measures and stopping rules fixed in advance.
6. Public, dated changelog of every default that changes and why.

## External replication (Savant swing/take leaderboard, 2025, 221 hitters)

Savant's run values are realized production by zone. Replicating that quantity with this pipeline's count values and outcomes: r +0.854 overall (heart +0.822, shadow +0.681, outside +0.947). The expectation-based decision value is a different quantity and agrees less (r +0.472; heart +0.035, shadow +0.082, outside +0.875). See docs/external_check.txt.
