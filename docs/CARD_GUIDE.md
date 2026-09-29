# Reading the plan card (one page, for coaches)

The card is a suggestion for one hitter against one starter in one situation. It says, pitch type by pitch type and location by location, whether swinging or taking is worth more for this hitter. It does not know what pitch is coming; it is a "if it is this pitch, and it is here, then..." sheet.

## The header

```
plan 37b9b69bdd5c30cc  PA  hitter 665742 vs starter 554430  mode COMPETE
count 0-0, 0 out, bases 000, lead +0, inning 1, TTO 2
```

- **PA / GAME:** a plan built for one plate appearance (uses the count and base-out state) or the pregame card (neutral count).
- **COMPETE / DEVELOP:** COMPETE is the plan that maximizes today's damage. DEVELOP holds the hitter's own damage zone fixed against a reference arsenal and ignores count and situation.
- **TTO:** which time through the order. The pitcher's usual pitch mix and shape for that stage feed the card.

## The grid, per pitch type

Each block is one of the starter's pitches, with how often he throws it in this count, its speed, its rise or drop (IVB, inches) and its side movement (HB, inches).

```
FF  usage 49%  95.8 mph  IVB 14.8  HB -2.4 ...
        in  ->  away
   3.8 ft  x x ? x x
   3.2 ft  x G G G x
   2.8 ft  ? G G G .
```

Columns run from inside to away **from the hitter's side** (the same for lefties and righties). Rows run from the top of the zone down. Each cell is about 6 inches square.

| Symbol | Meaning |
|---|---|
| **G** | Swing. For this hitter, in this count, swinging is worth clearly more than taking. |
| **x** | Take. Swinging is worth clearly less than taking (it is probably a ball, or he does little with it). |
| **.** | No call. The two are close; use your own judgment. |
| **?** | Thin evidence. The estimate would be a call, but the hitter's own swings in that area are too few to be sure, so the card withholds it. Treat like a no-call. |

"Clearly" means the difference is at least 0.02 wOBA points and the estimate stays on that side even after allowing for uncertainty.

## The sample-size line

`(effective hitter swings behind these cells: median 4; 5 thin cells withheld)`

This is how much of the hitter's own history is behind the cells for that pitch shape. A small number means the card is leaning on league averages and coach reports, not on him. A pitch type with many `?` cells is a pitch the hitter has not been seen against much: do not over-read it.

## The bottom lines

```
If 665742 follows every call: about +1.90 runs per 100 pitches (upper bound...)
54% of this starter's pitches land in a called cell; his tendencies already match the call on 50% of those.
Largest opportunities (cell, runs per 100 pitches): FF|2|2 +0.12, ...
```

- **Runs per 100 pitches:** what the calls would be worth if he did exactly what they say, given where this starter actually throws and how often this hitter swings there now. It is an upper bound, because hitters choose what to swing at, which flatters the swing side. Use it to rank plans and cells, not to promise runs.
- **Already match the call:** how much of the plan he already does. Low means there is room to change; high means the card mostly confirms what he does.
- **Largest opportunities:** the cells where following the call moves the needle most. Start the conversation there.

## Situations and the runner-on-third setting

The first line of the printout suggests a policy for a runner on third with fewer than two outs (MILD, STRONG or CONTACT_FIRST), based on how likely this hitter is to strike out against this starter. It is a suggestion. You can set your own per hitter, per starter, or per matchup; the card shows which weights are in force.

## What this card cannot do

- It does not know the pitch. If the hitter cannot recognize a pitch in time, the card's split by pitch type does not apply to him.
- It does not see the pitcher adjust. If the hitter takes every "x" pitch, the pitcher may change what he throws.
- It is built on tracked history. A hitter with few tracked swings gets a mostly league-based card; that is what the sample-size line is for.
- A single at-bat says nothing about whether the card is right. Judge it over many pitches.
