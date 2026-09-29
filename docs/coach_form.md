# Hitter report form (one page)

One row per read. A report is one hitter on one date; use as many rows as you have real reads. Skip a cell you have no read on: a blank is worth more than a guess, and the model scores every read you do write.

Fields (match `examples/coach_reports_template.csv`):

| Field | Values | Meaning |
|---|---|---|
| report_id | any | same id on every row of one report |
| coach_id | your id | used only to track how well your reads match the tracked data |
| hitter_id | player id | |
| date | YYYY-MM-DD | date you formed the read |
| family | FB, BRK, OFF, blank | fastball (FF, SI, FC); breaking (SL, ST, SV, CU, KC); offspeed (CH, FS). Blank = all |
| vert | LOW, MID, HIGH, blank | third of the zone by height |
| horiz | IN, MID, AWAY, blank | relative to the hitter: IN = on his hands, AWAY = off the plate away |
| whiff_delta | number | how much more (+) or less (-) he misses than a typical hitter on swings there |
| contact_delta | number | how much more (+) or less (-) damage he does when he does hit it |
| confidence | 1, 2, 3 | 1 = a hunch, 2 = seen it repeatedly, 3 = consistent and obvious |
| notes | text | what you saw; not used by the model |

## Sizing the two numbers

Typical hitter: misses on about 23 of 100 swings (0.23) and averages about .370 xwOBA on balls in play.

| whiff_delta | reads as |
|---|---|
| 0.03 | slightly more or fewer misses |
| 0.06 | clearly a weakness (or strength) |
| 0.10 | major hole (or elite there) |
| 0.15+ | almost can't touch it (or almost never misses it) |

| contact_delta | reads as |
|---|---|
| 0.02 | a bit better or worse contact |
| 0.05 | clearly hits it harder or weaker |
| 0.08+ | damage zone (or he only produces weak contact there) |

Same direction for both means different things: a hitter who chases a pitch (whiff +0.10) but does damage when he connects (contact +0.05) is a real profile; write both.

## Rules that keep the numbers useful

- Three to six rows per hitter is plenty. A pattern of "everything a little weak" is not a read.
- Do not average the two axes. Write what you saw for misses and for contact separately.
- Update after real change (a new swing, an injury), not on a schedule.
- Nothing you write is graded on one report. Your reads are scored in bulk against tracked swings, and your weight in the model rises or falls with how well they match. A coach whose reads keep matching the data moves the plan more; a coach whose reads do not moves it less.

Score reports: `python -m gameplan.coach_reports --reports reports.csv --swings <dir of swing CSVs>`
