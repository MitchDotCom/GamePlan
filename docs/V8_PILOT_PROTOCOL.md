# V8 pilot protocol: does the clip work train recognition? Draft 2026-10-08

Extends the V8 spec in `docs/VALIDATION_PLAN.md` (assessment, staggered start, outcomes). Nothing here has been run. It needs org approval and Visalia hitters. Everything below that is a number is a calculation from stated assumptions, not a result.

## What the existing spec leaves open, and this draft's answer

1. **The same clips pre and post test memory, not recognition.** Use two parallel forms (A and B) of 120 clips matched on pitch type, pocket, pitcher hand and occlusion point. Hitters get A then B, with the order randomized, so a form effect shows up as an order effect. Needs enough clips: at least 240 for the assessment plus the training pool.
2. **The instrument has never been measured.** Before any training, give the form to volunteer staff or hitters twice, two weeks apart, with no training. That gives the test-retest reliability and the real standard error. If reliability is low (a bar to fix in advance: intraclass correlation at least 0.6), the assessment cannot carry the primary outcome.
3. **The clips are not yet the right angle for MLB.** Public clips are center field; the Visalia clips are low home. The assessment must use the low-home footage, which means the held-out release test (30 or more labeled clips) has to pass first, or the occlusion cutoffs are wrong.
4. **Answer keys.** Pitch type and zone come from TrackMan rows. The zone key is the ball's position, not the umpire's call. Say which the assessment scores.
5. **Co-intervention.** The coach 1-on-1 review is part of the treatment (as the spec says). Anything else that changes during the pilot (a new hitting coach drill, promotion, injury) must be logged so it can be excluded or adjusted.

## Power, with assumptions

Paired change in a hitter's score, two-sided alpha 0.05, 80% power. These are the optimistic floors: they assume the only noise is the test's own sampling error plus the stated extra person-by-occasion variability, and they ignore the staggered control, which costs power.

Assessment accuracy (120 items, accuracy about 0.60, measurement SE 0.045 per administration):

| Extra real variability in change (SD) | 12 hitters | 16 | 20 | 30 |
|---|---|---|---|---|
| none | 5.6 points | 4.7 | 4.2 | 3.3 |
| 0.04 | 6.7 | 5.6 | 4.9 | 4.0 |
| 0.07 | 8.4 | 7.1 | 6.2 | 5.0 |

Chase rate on out-of-zone pitches, per-period pitch counts (binomial noise only, chase about 0.28):

| Out-of-zone pitches per hitter per period | 12 hitters | 20 | 30 |
|---|---|---|---|
| 150 | 4.6 points | 3.4 | 2.7 |
| 300 | 3.3 | 2.4 | 1.9 |
| 600 | 2.3 | 1.7 | 1.4 |

Reading it:
- With about 20 hitters, the assessment can detect a change of roughly 4 to 6 points of accuracy. Whether a real effect is that large is unknown; the ABCA case report's gains cannot be used as a size, because it is a vendor report on two hitters.
- Game outcomes are far noisier than the test. A 2- to 3-point chase-rate change needs hundreds of out-of-zone pitches per hitter per period, and real variation (opponents, parks, promotions) adds to the binomial noise assumed here. So the pilot's honest primary outcome is the assessment, with game outcomes as supporting, not confirmatory.
- V3 puts the plausible game-level value at about 0.5 to 1.7 runs per hitter per 150 starts. That cannot be seen in one pilot. The pilot claim is "recognition test scores moved", not "runs were won."

## Pre-registered bars (to be fixed in writing before the first assessment)
- Primary: change in assessment accuracy on the trained shapes versus the not-yet-started hitters over the same weeks, interval above 0 and at least 4 points.
- Transfer check: change on untrained shapes (generic block) reported separately; no transfer claim unless its interval is above 0.
- Guardrails: no drop in contact rate on in-zone pitches larger than 2 points; session minutes logged for every hitter.
- Reported regardless of outcome: reliability of the form, dose per hitter, dropouts, anything that changed besides the clips.

## What to ask the org (draft for the owner to adapt; not sent)
1. Permission to use Visalia pitch tracking and game video for a staff-run pilot with consenting hitters, kept inside org systems.
2. About 20 hitters, 6 to 8 weeks, three short sessions per week on a tablet, with coach review.
3. Clear terms for hitters: opt-in, no effect on playing time or evaluation, results shared with them, data not used for roster decisions.
4. What we need back: a TrackMan export for the pilot games, clip access with a naming scheme that identifies the pitch, and one person who can answer data questions.
5. What the org gets: the assessment results, the tool, and a plain statement of what worked and what did not, including a null result.
