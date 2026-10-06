# Gate 0b pre-registration (2026-10-06), written before any run: does pitch recognition show up in public data, and which pitch facts matter?

Follows `docs/GATE0_READOUT.md`, which found the zone-by-pitch-type calls are mostly the starter's menu and carry little hitter-specific information. The owner's reframing: (1) the cause of a chase or a taken strike three is usually unknown (recognition, sitting on something else, mechanics), and (2) the useful facts are about how a pitch *plays*: a sweeper with a lot of run, a fastball with extension and ride that plays faster than the gun. This tests both ideas on public MLB data, 2025 and 2024 as confirmation. Bars are CHOICE values set now.

Same data, referee and eligibility as Gate 0 (starter pitches; referee fit on the full season; hitters with at least 300 earlier starter pitches). Code to be written in `src/gameplan/recognition_signals.py`.

## Test 1: Can a hitter's pitch-type blindness be measured, and is it separate from zone control?

At the same location and count, a hitter who reads the pitch swings more when the pitch type makes swinging the better choice, and less when it doesn't.

- **Location cell:** x_away in 0.3 ft bins, height as a fraction of his own zone in 0.2 bins, strikes 0/1/2.
- **Type signal t:** the referee's (swing value minus take value) for the pitch, minus the average of that over the pitches in the same location cell. This is the part of "right decision" that depends on the pitch type, not the location.
- **His response s:** swing (0 or 1) minus the league swing rate in that location cell.
- **His type sensitivity g:** the slope of s on t over his pitches, divided by the league slope. 1.0 means he uses the type signal like the average hitter; below 1.0 means he is blind to it.
- **Reliability:** odd-game versus even-game g across hitters, Spearman-Brown corrected. PASS: at least 0.40.
- **Predicts mistakes:** first-half g (games before the split date) against second-half loss per pitch on the 30% of pitches with the largest absolute type signal. Expect a negative relationship. PASS: correlation below 0 with the 95% bootstrap interval (hitters resampled, 1,000 draws) excluding 0, and still below 0 after removing first-half loss on those same pitches (partial correlation).
- **Separate from zone control:** correlation between g and his zone discipline (swing rate on out-of-zone pitches minus the league's). Report. "Separate skills" if the absolute correlation is under 0.5.

## Test 2: Do extension and ride matter beyond the radar gun?

- **Extension-adjusted velocity:** release speed times (average remaining distance divided by this pitch's remaining distance), where remaining distance is 60.5 ft minus release extension minus 1.42 ft. Derived by us, not Savant's perceived-velocity figure.
- **Whiff on swings:** model with location, raw velocity, vertical break, horizontal break, approach angle, count, pitch family and a pitcher intercept; add extension-adjusted velocity. Fit before the split date, scored after. PASS: log-loss gain with the hitter-cluster interval above 0, in 2025 and again in 2024. Run on all pitches and on fastballs only.
- **Hitter-specific sensitivity:** for fastballs, each hitter's slope of whiff on vertical break (ride), on extension-adjusted velocity, and for breaking balls on horizontal break (run), estimated on the first half with ridge shrinkage toward the league slope (K = 100 swings). Reliability by odd and even games, PASS at least 0.40. Predictive: second-half log-loss gain over the league-slope model, hitter-cluster interval above 0.

## How the results are read

| Result | Decision |
|---|---|
| Test 1 reliable and predictive, separate from zone control | Recognition is a real, measurable hitter skill in public data. The card can say "you swung at the changeup like a fastball" and the drill targets it |
| Test 1 reliable but not predictive, or not reliable | Public data cannot separate pitch-type blindness from noise. Recognition stays a hypothesis for the clip test to settle |
| Test 2 extension-adjusted velocity passes | Facts like "plays as 96" belong on the card, from the starter's own numbers |
| Hitter-specific sensitivities reliable and predictive | "He struggles with ride" is a real, personal, surfaceable fact |
| Both fail | The card's content is the starter's characteristics only; nothing personal beyond his own misses, which come from the receipt |

## Predictions on record

- Test 1: reliability is the risk. A slope through a few hundred pitches is noisy; I expect 0.2 to 0.4, below the bar, with a real chance of passing for the most-sampled hitters only.
- Test 2: extension-adjusted velocity should pass for whiffs on fastballs (it is a known effect) and add little for breaking balls.
- Hitter-specific ride and run sensitivities: likely too noisy at these sample sizes.

## Not testable here

When to surface what (pregame, night before, morning after). That needs hitters and coaches: a staggered pilot. A proposed design is in the readout of this gate.

## Amendment (2026-10-06, before the full runs)

A short-window development run (March to early June 2025, not a result) showed that the league slope of swinging on the type signal is slightly **negative** (about -0.08): on average hitters swing a little less when the pitch type makes swinging the better choice (for example they take more offspeed pitches than the average-hitter model says they should). Dividing a hitter's slope by that league slope, as written above, flips the sign and produces extreme values. The measure is therefore changed to the **raw hitter slope** (no division). Higher means he uses the type signal more. Everything else is unchanged, and the expected relationship with later mistakes is now: higher slope, less second-half loss on high-type-signal pitches (correlation below 0). The negative league slope is itself a finding: hitters do not track the average-hitter model's type signal, which is what we would expect if recognition is limited.
