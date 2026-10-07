# GamePlan in plain English

Written 2026-10-07 for checking my work. Every test, every result, what it means, and how you can check me. No stats background needed. Where a number matters, I show the line in the results file so you can find it.

## 1. What we are building

A pregame tool. For each hitter facing a specific starter, it picks a couple of pitches worth working on that night. The hitter sees the same pitches as video clips, and the next day gets a receipt of what he did. The goal is to train pitch recognition, not to build a lineup optimizer.

The tests below ask one question over and over: **are the pitches we pick really the ones that cost this hitter, and do we pick them better than a coach would with no model?**

## 2. The five ideas you need

**The referee.** For every pitch in a season, a model works out what a swing was worth and what a take was worth, in runs, for an average hitter. If he did the better thing, nothing was lost. If he did the worse thing, the gap is that pitch's **loss**. Example: a pitch he took was worth +0.04 runs as a swing and -0.02 as a take. Taking cost him 0.06 runs. That is the loss.

Why it matters: the referee defines "mistake." It does not pick the calls. Its weakness is that it grades against an average hitter, so a hitter who is not average gets graded against someone he is not. I flagged this as the biggest flaw and test it in V9.

**A shape.** A group of similar pitches. We tried four ways to group them:
- S1: pitch family (fastball, breaking, offspeed) by height third of the zone. 12 groups.
- S2: S1 plus inside, middle or away. 36 groups.
- S3: exact pitch type (four-seam, slider, and so on) by height third.
- S4: pitches clustered by speed and movement, by height third.

**A path.** A rule for picking which shapes to call for one hitter against one starter. Same data, different rule:
- L: starter-level. Pick the shapes where the league loses the most, weighted by how often this starter throws them.
- P: personal. Same, but using this hitter's own loss, pulled toward the league when he has few pitches.
- U: usage only. Just pick the starter's most-used shapes. No model, no loss. This is our "what a smart coach does" control.
- E and W: pick shapes where this hitter is worse than the league (E weights by how often the starter throws it, W looks at his weak spots alone).
- D and N: the look-alike idea. Pick breaking and offspeed pitches that start out looking like the starter's fastball.
- B1 and B3: simple baselines built from his own raw results, no referee. B1 is his two costliest shapes so far. B3 is his costliest shape plus the starter's top non-fastball.

**No peeking.** Every pick for a game uses only earlier games. Nothing from the night being graded leaks in.

**Raw results.** Statcast gives a run value for every pitch result (`delta_run_exp`). Using it means no model is in the grading at all. Several tests use it so the model can't grade its own work.

## 3. The first round of tests (Gate 0). What each letter means

| Test | Plain question | Bar |
|---|---|---|
| A, coverage | How many flagged pitches does he see in a game? | A median of 2 or more |
| B1, lift | Do flagged pitches cost more than his other pitches? | At least 25% more, and clearly above 1.0 |
| B2, is it him | Is the personal list better than the starter-level list? | Clearly above zero |
| B3, reliability | If you split his season into odd and even games, do both halves find the same weak spots? | 0.40 or higher |
| C, concentration | Do two calls hold a big share of his mistakes? | At least 30% of his loss, and 1.5 times their share of pitches |

**What we found, four seasons (2022 to 2025):**
- A: S1, S3 and S4 meet it. S2 (the finest grouping) sometimes sees only one flagged pitch a game.
- B1: passes everywhere. Flagged pitches cost 14 to 35% more. Real.
- B2: personal beats starter-level on S1 in all four years and S2 in three. It is tiny (a few hundredths). Not clearly true on S3 and S4.
- B3: passes everywhere, 0.42 to 0.57. His weak spots are stable inside a season.
- C: fails every time. Two calls hold about a third of a hitter's loss. The rest is spread everywhere.

**Plain reading:** the signal is real and stable, but it is spread thin. Two calls per hitter cannot "fix" a hitter on their own.

## 4. The second round (V tests). The ones that grade the model from outside

**V1, does it show up in real results?** Take the pitches we flagged and the ones we did not. Compare their real run values (Statcast), matched on shape and count. Positive means flagged pitches really cost him more.

Found: only **S2** passes in all four seasons. Example, 2025: `S2 L: cost lift +0.639 [+0.437, +0.850] PASS` in `docs/validation_results_V1V3_2025.txt`. Read it as: flagged pitches cost 0.64 runs more per 100 pitches than his others, and we are 95% sure the true number is between 0.44 and 0.85. On S1, S3 and S4 it is mixed.

**V2, does the model beat a simple rule?** Same raw results, but now compare our model's picks against the simple ones (U, B1, B3). If the model is worth building, it should win.

Found: it never wins. **0 of 64 comparisons** across four seasons. Picking the starter's most-used pitches (U) is as good as the model. This is the most important finding so far.

**V3, how big is it?** Convert the lift to runs. About half a run to 1.7 runs per hitter per 150 starts. That is small. So the honest claim is "this helps train recognition," not "this wins games." One hitter's change would take thousands of games to see in the data.

**V4, did we get lucky?** If you test 192 things, some pass by luck. The standard fix (Benjamini-Hochberg) raises the bar based on how many things you tested. Found: 48 of 53 passes survived. The S2 results and the "personal beats starter-level on S1" result stayed. V2 stayed at zero. Details in `docs/validation_results_V4.txt`. One caution: I estimated the p-values from the intervals in the files, which is an approximation.

**V5, is the result an accident of one setting?** The personal path pulls a hitter toward the league when he has few pitches. The strength of that pull ("K") was set at 40 without testing. V5 tries 10, 20, 40, 80, 160. We choose K on 2022 and 2023, then judge on 2024 and 2025 so we cannot cheat.

**V6, are the intervals too narrow?** Our intervals treat hitters as independent. But the same starters face many hitters, so results are linked. V6 redoes the intervals counting both hitters and starters. Expect them to get wider. The question is whether S2 still passes.

**V7, will it work at Single-A?** MLB hitters have lots of history. A Single-A hitter has little. V7 cuts the history we allow to 100, 150, 200 and 300 pitches, and the starter history to 1, 2 and 3 starts, then checks whether results hold. This is MLB data cut down, not real Single-A data, so it is only a stand-in.

**V8, does it train recognition?** None of the above measure recognition. V8 is the plan for a real test: video clips, same test before and after, with hitters starting in different weeks so each is his own comparison. Needs org approval. Spec is in `docs/VALIDATION_PLAN.md`.

**V9, is the referee fair to each hitter?** The referee grades against an average hitter. V9 rebuilds it using each hitter's own whiff and contact skill (from other games, so no peeking) and reruns V1. If the S2 result survives, the finding is not just an artifact of grading everyone as average.

## 5. The extra tests on pitch traits (Gate 0b)

- **Fastball ride and breaking-ball run.** Does a hitter react differently to a fastball with more ride, or a sweeper with more run? Found: yes, and it is stable in all four seasons. This matches how your coaches talk.
- **Extension-adjusted velocity** ("the 93 plays as 96"). Does a hitter whiff more when extension makes the pitch play faster? Found: no. Fails in all four seasons.
- **Look-alike pitches** (tunneling). Does a slider that starts like the fastball get more chase? It looked strong at first. After matching pitches on where they end up, nothing is left. Four seasons agree.
- **Pitch-type blindness.** Is a hitter reliably worse at telling pitch types apart? Passes in two seasons, fails in two. Not confirmed.

## 6. What this means for what we build

1. Build calls from the starter's most-used pitches on the S2 grid (family, height, side). The referee ranking adds nothing on real results.
2. Show his ride and run reactions. They are the best hitter-specific information we found.
3. Drop extension-adjusted velocity and look-alike weighting.
4. Call it "decision cost," not "recognition," until V8 exists.
5. Promise training value, not a win edge.

## 7. What I got wrong or changed along the way

- I once pulled data labeled minor-league that was MLB data. I corrected the notes and threw out that run.
- The look-alike result looked strong, then fell apart when matched on landing spot. I reported it as a failed result, not a win.
- One V1 bar I wrote ("effect at least half the model's prediction") compared two things in different units. I fixed it and recorded the change with a date, before any full run.
- My background jobs were being killed whenever the machine paused. I rebuilt them so each stage can restart, and I now run them while I am actively working.

## 8. How to check my work

You do not need to run code.

1. **Open `docs/validation_results_V1V3_2025.txt`.** Find the line `S2 U: cost lift`. Then find `S2 L`. Those two are close. That is the "model adds nothing over usage" result, in one place.
2. **Open `docs/validation_results_V4.txt`.** The top four lines give the counts. Check that V2 says 0 survive.
3. **Open `docs/GATE0_FOUR_SEASON_READOUT.md`.** Section D is the ride and run table. Does it match how a coach would describe those pitches?
4. **Pick one claim you doubt and tell me.** I will point to the exact file and line.
5. **Ask for any single hitter-start.** I can print which pitches were flagged and what happened on them, so you can judge it with your own eyes.

## 9. Questions for you

1. **The S2 grid uses "inside / middle / away" and "low / middle / high" thirds. Is that how your coaches split the zone, or would they say it differently?** The card should use their words.
2. **What video do you have access to that could become the clips?** Same-night tracking from Visalia, or only broadcast-style video? The clip cut-off point and the camera angle change the test.
3. **For the pre/post recognition test, would your org allow a short tablet test (about 10 minutes) with Visalia hitters?** If not, V8 needs another form.
