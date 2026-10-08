# TrackMan adapter, 2026-10-08

`src/gameplan/trackman.py` reads a standard TrackMan CSV and produces the pitch rows the playlists already use. It was built against standard column names with no sample export. The Visalia export has not been seen.

## What it needs
Date, PitcherId, PitcherThrows, BatterId, BatterSide, Balls, Strikes, TaggedPitchType, PitchCall, RelSpeed, InducedVertBreak, HorzBreak, PlateLocHeight, PlateLocSide. Optional: PitchUID, GameID, Pitcher, Batter, PitchNo, ZoneTime. A missing required column stops the read and lists what is missing.

## Nothing guessed
- **Sign of PlateLocSide** is inferred: pitchers throw more pitches away from a batter than in, so the side whose average sits further positive tells which way + points. Needs at least 200 pitches to each batter side and a gap of at least 0.05 ft, else it refuses.
- **Sign of HorzBreak** is inferred: a right-handed pitcher's fastballs and sinkers run arm-side, toward first base. Needs at least 100 right-handed and 100 left-handed fastballs/sinkers with opposite signs, else it refuses.
- **Strike zone** top and bottom are not in a TrackMan export. The pocket height thirds use 1.5 to 3.5 ft unless per-batter heights are passed in.
- **No run expectancy** in TrackMan, so the hitter-cost playlist returns nothing from TrackMan history (it says so rather than ranking arbitrarily). Usage, ride, run and count lists work.

## Validation on MLB data (`trackman_validate.py`, raw output `trackman_validation_2026-10-08.json`)
MLB pitches (3,962 from 14 games of 2025-06-08 to 06-10) were written out as TrackMan-style tables with all four combinations of flipped plate-side and horizontal-break signs, read back through the adapter, and compared with the values the study uses.

| Check | Result |
|---|---|
| Inferred signs equal the applied signs | 4 of 4 combinations |
| Plate x, ride, run recovered | max absolute difference 0.0 in all four |
| Pocket agreement with MLB per-batter zone | 97.05% |
| Pocket agreement with the single default zone (what TrackMan forces) | 91.01% |
| A hitter's ride and run slopes (Nootbaar, 2023 to 2025, 1,315 and 548 swings) from TrackMan-style history vs Statcast history | identical in all four combinations (ride +0.0585, run -0.1663) |

Two bugs were caught by this validation: an extra pitcher-hand factor on run for left-handed pitchers (fixed in the adapter), and a test that mixed the feed's and Statcast's opposite horizontal-break conventions (fixed in the test).

## What this does not show
- It shows the adapter reproduces MLB values from a TrackMan-shaped table. It does not show that the Visalia export looks like this. The first real file needs a field audit.
- About 9% of pitches change pocket because of the default zone. A per-batter zone (even a height-based one) closes that.
- TrackMan's own PitchCall and TaggedPitchType vocabularies vary by firmware and by whether a human cleaned the file. The mappings are in `trackman.py` and `trackman_validate.py`.
- The clip join is still open: no video timestamp match. The playlists can say which pitches to show (PitchUID, inning, batter, count). Attaching a clip to a PitchUID needs the staff mapping or a sequence-based match, to be built when we know what the video files look like.
