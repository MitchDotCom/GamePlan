# Coach mock-up (Track B)

`board.html` is a single file; open it in any browser. It is built from public 2025 MLB data and the current engine, fit only on games before the game date (2025-08-19, Astros lineup against Tarik Skubal). Regenerate with:

    PYTHONPATH=src python3 -m gameplan.mockup --league data/league --date 2025-08-19 --game 776685 --starter 669373 --out docs/mockup

What it shows
- Starter profile and the 9-man lineup with each hitter's data support.
- Per hitter, every count and time through the order: three illustrative approach styles (value plan, contact-capped, hunt a spot), each with a swing/take grid for one pitch type and plain numbers (share of pitches swung at, whiff on swings, contact quality, value if followed).
- Development targets: where the hitter's past swing/take decisions cost more than a typical hitter's.
- Post-game: every pitch the lineup saw from the starter, scored against the plan in force at that count.

What it is not
- Not validated for Single-A. Public MLB data only.
- The three styles are hand-built from the current plan to show the format. They are not the final path generator and the tags are computed from numbers, not coach vocabulary.
- "Value if followed" is an upper bound (hitters choose what to swing at).
- Development targets are descriptive and need more than a game or two of evidence before anyone acts on them.

`board.json` holds the same data for the later application.
