# V2 evidence ledger (2026-10-04)

Every claim in `docs/GAMEPLAN_V2_PLAN.md` section 11, with where its source lives and what has actually been checked. "In this repo" means a note or report in this repository holds the source. "Verified here" means a full page or paper was read in this project. Nothing below counts as verified unless that column says yes.

Status of the network when this was written: Savant answers (HTTP 200). Most other research domains (mlb.com, PubMed Central, FanGraphs, SABR, jmir.org, frontiersin.org, arxiv.org) were blocked in earlier research runs, so those could not be read in full.

## A. Claims V2 relies on

| # | Claim in V2 | V2 source and tier | In this repo | Verified here | What to do |
|---|---|---|---|---|---|
| 1 | Temporal occlusion training has a large effect; video and field tests agree; 12 studies | Muller and Morris-Binelli meta-analysis, A | No | No | Read the paper; check effect size and sport mix |
| 2 | Perceptual-cognitive training: lab 1.51, game transfer 0.65; life-size video 0.46, VR 0.96; over 4 weeks better; sessions under 10 minutes ineffective | Behavioral Sciences 2024, A | No | No | Read; confirm the 4-week and 10-minute moderators, because the plan's dose design leans on them |
| 3 | Opponent-specific training improved accuracy only against the same opponent (39 pro tennis players) | Frontiers in Psychology 2024, A | No | No | Read; check what "same opponent" meant and whether it transferred to matches |
| 4 | VR batting trial, 80 players, 6 weeks, better league stats | Frontiers in Psychology 2017, A (abstract only) | No | No | Read the full paper; effect sizes were not in the abstract |
| 5 | Visual and oculomotor skills predicted 22 to 28% of swing-discipline variance, 71 minor leaguers | bioRxiv preprint, A | No | No | Read; preprint, exploratory |
| 6 | Single-A anticipation correlated with walk rate, r about .35, n=34 | "Earlier research note", A | **Not found** | No | Locate the source or drop it |
| 7 | If-then plans in sport: 11 studies, mixed | Bieleke et al. scoping review, A | No | No | Read |
| 8 | Process goals d=1.36, performance 0.44, outcome 0.09 | Goal-setting meta-analysis, "earlier note" | **Not found** | No | Locate the source |
| 9 | Progress monitoring d=0.40, larger when recorded and reported | Harkin 2016, "earlier note" | **Not found** | No | Locate the source |
| 10 | Swings start within about 100 ms on largely 2D information | Baseball Prospectus article, B | No | No | Read; an article, not a study |
| 11 | Skilled cricket batters use pre-release and pre-bounce cues better | Murdoch University study, A | No | No | Read |
| 12 | 19 trackable pitcher tell markers | Baseball America, B | No | No | Not used by the engine; low priority |
| 13 | Minor leaguers at 53% recognition on a go/no-go test | ABCA article on uHIT, C | Mentioned as "pitch recognition" in `research_notes/Baseball hitting game plan engine research/hitter_metrics_and_data.md` line 88, which says "no sourced findings" | No | Treat as vendor material; biased sample |
| 14 | Augmented feedback in cricket: anticipation g=1.21, neither effect significant | PLOS ONE review, A | No | No | Read |
| 15 | Closer early paths mean higher whiff rates (tunneling) | Roegele via Hardball Times, B/D | No | No | Gate 0 tests this directly |
| 16 | Fadde college program: 20 pitches in 5 minutes, voluntary, 14 of 18 used | "Earlier research note", B | **Not found** | No | Locate the source |
| 17 | Batter-versus-pitcher history adds little beyond season stats | "Earlier research note", A/B | One adoption note touches the topic, not this claim | No | Locate or test on our data |
| 18 | Hitters differ stably by pitch type, r about .7 year to year, MLB only | "Earlier research note", A/B | **Not found** | No | Gate 0 test B3 measures our own version |

Reading the table: the six "not found" rows (6, 8, 9, 16, 17, 18) came from a session whose notes are not in this repository. Until their sources are located and read, no gate or number may depend on them.

## B. What this repository's own work says about V2

| Question | Our evidence | Source |
|---|---|---|
| Does per-hitter information add to plan calls? | Hitter-specific terms changed 7.6% of calls and the effect was not distinguishable from zero. A median of 0.2 of a hitter's own swings sits behind a cell | `docs/G1_EVIDENCE.md` |
| Are hitter skills stable year to year? | Whiff skill and contact-quality skill beat the league year over year (Brier skill 0.022; MSE skill 0.0023, both with lower bound above zero). Bat-tracking traits are stable (split-half 0.99+) | `docs/scorecard.md`, `docs/traits_reliability.txt` |
| Do alternative approach paths differ enough to show? | Collapsed to one path in 84% of hitter-counts; Hunt scored 0.7 to 3.2 runs per 100 plate appearances worse than Value | `docs/paths_evidence.txt` |
| Can recognition or tunneling be supported from public sources? | No sourced findings on recognition; no public evidence that tunneling explains performance; deferred for v1 | `research_notes/Baseball hitting game plan engine research/` |
| How small a change can one hitter show in a season? | Assumption-based: about 9 to 13 points in chase rate at roughly 300 plate appearances. These are the researchers' calculations, not published figures | `reports/Hitting approach intent and success.md` |
| What does the dugout allow? | MLB restricted AI recommendations on dugout iPads from the second half of 2026; MiLB status unconfirmed (snippet only) | same report |

## C. Rule going forward

Before any gate depends on a claim in section A, its source is read in full and the row is updated here with the finding. The first priority is rows 1 to 3 (the occlusion meta-analysis, the perceptual-cognitive meta-analysis, and the opponent-specific study) because the dose design and the starter-versus-generic decision rest on them. That needs the network allow-list to include `pmc.ncbi.nlm.nih.gov`, `mdpi.com`, `frontiersin.org` and `biorxiv.org`.
