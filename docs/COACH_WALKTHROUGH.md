# Showing the game viewer to a hitting coach (10 minutes)

Open either file in any browser (laptop is fine; it works offline). Each is one real 2025 game built from public data, with every plan fit only on games before that date.

- `docs/gameview2/game.html`: Red Sox at Diamondbacks, 2025-09-06, Pfaadt vs Giolito, 9 innings, 69 plate appearances. Lead with this one: normal game, both starters go deep, Arizona hitters.
- `docs/gameview/game.html`: Astros at Tigers, 2025-08-19, Skubal vs Brown, 0-0 through nine and a 10th-inning walk-off walk, 71 plate appearances. Use it as the second example, a pitchers' duel.

## Say this first (30 seconds)
"This is a prototype built on public MLB data. For every hitter, count and time through the order, it shows where a hitter should swing and where he should take against this starter, and then it scores what actually happened. I want to know what is useful, what is noise, and what is missing."

## Walk through (in this order)
1. **Game tab.** Nine innings, both teams. Each box is a plate appearance (bar color: blue hit or walk, red strikeout, gray out; faded = reliever, no plan). Click one.
2. **The at-bat view (the zone is the point).** A large strike zone in the batter's view, inside on the left. The black outline is that hitter's own zone. Every pitch is plotted in order as a numbered dot, colored by result (ball, called strike, swinging strike, foul, in play). The blue and red cells are the plan for the selected pitch: swing or take. Step through with the Previous and Next buttons, the number chips, or the arrow keys. A pitch drawn with a dashed ring was far outside the grid. Beside it: count, situation, location, what the plan said, what he did, the decision value and a plain-words review. Ask: "Would you show this to the hitter on video? Which pitches?"
2b. **The swing under the zone.** For every swing the view shows bat speed, swing length, attack angle and swing path tilt next to what he usually does on that kind of pitch and what the league does. Below it, the bat path versus the pitch: the angle between where his bat was going and where the pitch was coming from, and whether that sits inside his own sweet band. Below that, whether the pitch was one he can damage (damage per swing in that pitch group and zone, against his own average and the league's). Ask: "Does his sweet band match what you see on video?"
2c. **Skipping at-bats.** Bunts, intentional walks, catcher interference, automatic ball or strike calls and position players pitching are skipped automatically and left out of the totals. Use "Skip this at-bat" for anything the data cannot see (hit-and-run, told to take, injury) and "Include this at-bat" to bring one back. The choice is logged. Ask: "What else should be skipped automatically?"
2d. **Can he damage this starter?** On the Hitters tab and the Pregame board: the starter's pitches one by one, with this hitter's whiff rate, damage per swing, edge over the league and where his bat path sits against that pitch. A chart shows his whiff rate by bat-to-pitch angle against the league's, with his sweet band shaded. Ask: "Which of these would you tell the hitter in the series meeting?"
3. **Runner on third.** Switch the selector at the top to "contact first" and look at a plate appearance with a runner on third and fewer than two outs. Ask: "Is this the policy you would want to control, and by hitter or by starter?"
4. **Pregame board tab.** Pick a hitter, a time through the order, a count, a pitch. Show the two plans when they genuinely differ (value plan and contact-capped). At two strikes and some counts only one is offered, on purpose. Ask: "Are these two the right alternatives? What would you call them?"
5. **Hitters tab.** Swing profile from bat tracking (attack angle low / middle / high, bat speed, swing length), shrunk toward the league. Descriptive only. Ask: "Does this match what you see in the cage?"
6. **Save a decision** on the pregame board (plan, reason, note). Ask: "Is this how you would want to record your call?" Export the log as CSV.

## Be upfront about limits
- The personal sweet band was tested: it predicts whiffs better than the current model in both 2025 and 2024, but the gain is small per swing. Bat speed, swing length and attack angle alone did not beat the current model, and nothing helped predict damage. So the band is a diagnostic and does not yet move any swing or take zone.
- Damage per swing is pulled toward the league by sample size. A hitter with few swings in a pitch group reads close to the league, and every table shows the swing counts.
- The thresholds for "damage pitch" (15% above his average) and "weak spot" (15% below) are my choices, not derived.
- The plan stays silent on about half of pitches (47 to 49% in both games), because the evidence is thin or the two options are too close. The top of the Game tab shows the exact rate. Say it first.
- Public MLB data, one game, not tested at Single-A, not tied to the club's TrackMan or Hawk-Eye data yet.
- Hitters' own past swings add little at these sample sizes; the plans are mostly driven by pitch shape and count. The hitter-specific part is the whiff and contact baseline and the bat-tracking profile.
- Decision value compares the hitter's choice with what the model says is better at that count. It is not a measure of whether he hit the ball hard.
- "Value if followed" is an upper bound.
- A hunt-a-pitch style is hidden by default because the model cannot value sitting on a pitch.

## Questions to write down
1. What would you use in a pregame meeting? What would you skip?
2. Are two plans per count useful? What words do you use for them?
3. Which hitters' development targets look right or wrong?
4. Which post-game pitches would you show on video?
5. What is missing (a count, a situation, a pitch, a name for something)?
