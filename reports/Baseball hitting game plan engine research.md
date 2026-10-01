# Build a tagged-option hitter plan engine, but license the data first

**One-page recommendation.** Build a layered engine: (1) a data adapter with player-ID, coordinate and tracking-system harmonization; (2) a hierarchical Bayesian hitter model of swing/take decisions and contact quality by count and pitch zone; (3) a starter model of usage and location by count and batter side, plus in-game drift, plus an in-house pitch-quality (Stuff) model; (4) a plan generator that enumerates tagged approaches, scores each with posterior draws, keeps the near-optimal band and picks 2 to 3 behaviorally different ones; (5) a one-card-per-hitter board with sample badges, a default marker and one-tap override with reason codes; (6) a staged evaluation that powers process metrics, not outcomes. The most important finding is not methodological. **Savant and the MLB Stats API appear to permit only individual, non-commercial, non-bulk use without written MLBAM authorization.** That is a snippet-level reading of a notice nobody on the research team could open (see Section 1). It is fine for a private proof of concept (PoC) built by one person for evaluation, and it is likely not fine for any club-operated pipeline. Resolve it with counsel and MLB before the club ingests a single bulk pull.

Evidence labels used throughout: **[P]** read from the primary page; **[S]** snippet-only, taken from a search-result summary because the primary page was blocked; **[I]** inference by the research team or by me. Almost everything is [S] or [I]. Section 9 lists what must be verified first.

### Ordered list of sources and methods to adopt

| # | Adopt | Why | Confidence |
|---|---|---|---|
| 0 | Written MLBAM authorization or an MLB-supplied feed before any club use of Savant or Stats API data | Terms appear to bar org/bulk use [S] | HIGH that it is a gate; MEDIUM on the exact terms |
| 1 | Club TrackMan/Hawk-Eye feeds as the production data; MLB public data for the PoC only | Only compliant route to Single-A pitch data; no public Visalia pitch data found | HIGH |
| 2 | Chadwick Register (ODC-By), Retrosheet (attribution), MIT/Apache/BSD libraries (pybaseball, baseballr, PyMC, MAPIE, netcal) | Clearly commercial-safe code and ID data [P for several repos] | HIGH |
| 3 | Per-source, per-season coordinate and system adapter (TrackMan vs Hawk-Eye; 2026 plate-location convention change) | Documented offsets and a convention change [P for Savant docs, S for extension offset] | HIGH |
| 4 | Hierarchical (empirical Bayes) shrinkage everywhere: hitter by count by zone, starter by count by side | Single-A samples are small; heat maps are noisy [S] | HIGH |
| 5 | Hitter swing/take decision value, scored against the hitter's own damage, conditioned on movement and approach angle | Public analogues (SEAGER, SwRV, BART) [S]; development-relevant | MEDIUM-HIGH |
| 6 | Starter usage and location by count and batter side with hierarchical Dirichlet shrinkage, plus pitch-count drift from first-inning baseline | Direct input to per-count plans; needs no external model | MEDIUM-HIGH |
| 7 | Plan generator: tag enumeration, posterior-band filter, MMR/DPP diverse top-k | Transfer from recommender literature [S]; no sport precedent found | MEDIUM |
| 8 | In-house Stuff model (gradient boosting on public fields), FanGraphs Stuff+ only as a comparison feature | Reproducible from published descriptions [S] | MEDIUM |
| 9 | Count-conditioned swing intent (bat speed, swing length) on Hawk-Eye parks only | Strongest 2025-26 evidence (Powers and Yurko) [S] | MEDIUM (data availability is the limit) |
| 10 | Location dispersion around per-pitcher cluster centers (xCTRL-style) | Only public-data command proxy found [S] | LOW-MEDIUM |
| 11 | Calibrated next-pitch probabilities | Useful only if they beat a count-by-side baseline [I] | LOW |
| 12 | Stepped-wedge Bayesian evaluation on process metrics; doubly robust off-policy evaluation of overrides | Few hitters, small effects [S] | MEDIUM |
| 13 | Defer: tunneling, seam-shifted wake, deep sequence models, hockey/golf analogues | No validated evidence for hitter approach [S] | HIGH that deferral is right |

## 1. The Savant and Stats API terms are the gating finding

**What the notes found.** The MLB-StatsAPI README says use of MLB data is subject to the notice at gdx.mlb.com/components/copyright.txt ([MLB-StatsAPI repo](https://github.com/toddrob99/MLB-StatsAPI)) [P for the README]. A search summary of that notice says it permits **only individual, non-commercial, and non-bulk use**, and prohibits any other use without prior written authorization from MLBAM [S]. Savant's CSV documentation lists 80+ fields and states no explicit volume limit, and the widely cited 25,000-row cap was not verified ([Savant CSV docs](https://baseballsavant.mlb.com/csv-docs)) [P]. The notice itself, mlb.com's terms of use and any Savant-specific terms were not opened. So the finding is plausible and consistent across sources, but it is unverified against the primary terms page.

**Implications.**

| Use | Reading of the terms [S] | Implication |
|---|---|---|
| One person's private PoC to test whether the method works | Closest to "individual, non-commercial" but bulk pulls of full seasons are the risk | Keep the PoC small, personal, non-redistributed; do not call it club-sanctioned; keep a log of what was pulled |
| Club staff running a nightly Savant/Stats API pipeline | Organizational, commercial, bulk | Not permitted without written MLBAM authorization |
| Using pybaseball or baseballr to do it | MIT covers the code only, not the upstream data [P for licenses] | No change in the answer |
| Publishing outputs or models trained on Savant data | Not assessed in notes | Unknown; ask counsel |
| Single-A club game data from the club's own TrackMan/Hawk-Eye feeds | Governed by the club's vendor contract or MLB's 2026 data-collection arrangement, not read | Likely fine; confirm contract terms |

**Options, best first.**

1. Ask MLBAM or the club's MLB data contact for written authorization or an MLB-supplied research feed for the PoC and for production. Cost: time. Upside: removes the gate. [I]
2. Build the PoC on non-MLB-terms inputs: Retrosheet (free for any use with attribution) and Chadwick Register [S], plus the club's own TrackMan/Hawk-Eye data for the production path. Retrosheet has no tracking data, so this covers only the event and ID layers. [I]
3. Keep the PoC on Savant data as an individual, non-commercial, small-volume exercise and treat every result as a method demonstration, not an org asset. Cost: no organizational reuse, and the research design must be rebuilt on club data. [I]
4. Use the 2026 MLB takeover of minor-league data capture: MLB says it will collect tracking data for all minor-league games from 2026 with equal access for all 30 clubs ([Baseball America](https://www.baseballamerica.com/stories/8-takeaways-from-mlbs-new-minor-league-data-regulation-plan/), [MLB Data Warehouse](https://www.mlbdatawarehouse.com/p/mlb-to-regulate-minor-league-data)) [S]. Whatever feed the club gets will carry its own terms, which are the real operative terms for production.

Recommended path: option 1 now, option 3 meanwhile, and design the engine so production runs on club feeds through the same adapter (option 4). All of this is research, not legal advice; counsel should confirm.

## 2. Source inventory with license and organization-use verdicts

Priority: P1 build on it, P2 add next, P3 optional. Effort: Low, Moderate, High. Data-side verdicts come from the data-sources note, which could open only some pages; "terms not read" means the primary contract or terms page was not seen.

| Source | Content | Coverage | Access and cost | License / org-use verdict | Quality issues | Priority | Effort |
|---|---|---|---|---|---|---|---|
| Baseball Savant Statcast Search ([link](https://baseballsavant.mlb.com/csv-docs)) | Pitch-level CSV, 80+ fields: velocity, release, spin, movement, batted ball, xStats, bat tracking | MLB; PITCHf/x-era 2008-2016, Statcast 2017+ | Web CSV, free | MLB terms; PoC only until written MLBAM authorization [S] | Revised after the fact; 2026 plate-location convention moved from front to middle of plate [P] | P1 for PoC | Low |
| Savant Minor League Search ([link](https://baseballsavant.mlb.com/statcast-search-minors)) | Same style, ABS challenge filter | Triple-A all games from 2023; Florida State League (Single-A) from 2021; "certain levels and ballparks" [P] | Web CSV, free | Same MLB terms | No California League listed on the page; Visalia pitch data likely not public [I] | P2 | Low |
| MLB Stats API / GUMBO | Schedules, rosters, box scores, play-by-play | MLB and minors | REST; no official public docs found; free | Not usable commercially without written authorization [S] | Unofficial docs only | P2 (rosters, IDs, schedules) | Moderate |
| Club TrackMan feed ([support](https://support.trackmanbaseball.com/hc/en-us/articles/5089413493787-V3-FAQs-Radar-Measurement-Glossary-Of-Terms)) | CSV with RelSpeed, PlateLocSide etc.; documented coordinate system [P/S] | Club parks | Vendor export under license; cost not captured | Yes under club contract (contract not read) | Radar infers release and spin; calibration differs from Hawk-Eye [S] | P1 production | Moderate |
| Hawk-Eye feed (club or MLB-supplied) | Optical release, spin components, skeletal and bat tracking [S] | MLB; some minor parks; planned for all minor parks 2026 [S] | No public schema or export documentation found | Depends on MLB or club arrangement (unread) | Extension reads about 1/3 ft longer than TrackMan/PITCHf/x at 2020 debut [S] | P1 production | High (schema unknown) |
| Savant bat tracking | Swing speed, length (2H 2023), attack angle, direction, tilt, intercept (2024-25) [S] | MLB; public minors bat tracking not found | Via Savant | MLB terms | Hawk-Eye only; validation error bars not found | P2 | Low |
| pybaseball ([repo](https://github.com/jldbc/pybaseball)) | Python wrapper for Savant, FanGraphs, Baseball Reference, Chadwick | Per source | pip, free | MIT code [P]; upstream data terms still apply | Release lag; scraping FanGraphs and Baseball Reference not cleared by MIT [I] | P1 for PoC | Low |
| baseballr ([repo](https://github.com/BillPetti/baseballr)) | R wrapper incl. Stats API, Savant minors | Per source | CRAN, free | MIT code; upstream terms apply | Active | P3 | Low |
| Chadwick Bureau Register ([repo](https://github.com/chadwickbureau/register)) | Player ID crosswalk | All | GitHub, free | ODC-By; yes with attribution [S] | Weekly extract | P1 | Low |
| Retrosheet ([notice](https://www.retrosheet.org/notice.txt)) | Event files | Historical | Download, free | Free for any use with the stated attribution line [S] | No tracking data | P2 (priors, run values) | Low |
| FanGraphs / BP leaderboards (Stuff+, Location+, StuffPro) | Published pitch-model grades | MLB | Export button; Members gating unconfirmed [S] | Terms not read; treat as comparison only, do not train on or redistribute | Column names unconfirmed | P3 | Low |
| Blast Motion | Bat sensor metrics | Own players | Manual app export; subscription | Vendor contract (unread) | No public API found | P3 | Moderate |
| Rapsodo | Pitching and hitting reports | Own | CSV only on higher cloud tier | Vendor contract (unread) | Manual export | P3 | Moderate |
| HitTrax | Batted-ball speed, angle, spray | Own | Export format not found | Unknown | Gap | P3 | Unknown |
| Open-Meteo paid plan | Weather | Global | Paid; free tier non-commercial [S] | Only on paid plan | Pricing not captured | P3 | Low |
| Park factors, umpire-zone data | Context | Unknown | Not verified | Unknown | Not assessed | P2 | Unknown |

Eight further data sources and five repositories were dropped by the researchers for license reasons (restrictive, share-alike, or no license stated), and counts for other notes were 0 to 14 depending on how conservatively each researcher read the rule. No omitted item is named, so I cannot judge whether any mattered.

## 3. Hitter metrics and data: decisions first, then swing quality

**What the evidence supports.** Pitch-level swing-decision metrics all compare the expected value of swinging versus taking given location and count, then credit the actual choice. SEAGER (Baseball Prospectus) correlates with wOBA and ISO better than zone swing or chase ([BP](https://www.baseballprospectus.com/news/article/86572/the-crooked-inning-corey-seager-rangers/)) [S]. SwRV, PLV Decision Value and aDecision+ add pitch movement or approach angle ([Down on the Farm](https://downonthefarm.substack.com/p/a-closer-look-at-swing-decisions), [Pitcher List](https://pitcherlist.com/plv-weekly-analyzing-swing-decisions-with-plv/), [Salorio](https://medium.com/@adamsalorio/introducing-abatting-639f36647b40)) [S]. A peer-reviewed BART framework yields the optimal swing decision per pitch and is the closest published analogue to the engine's core ([arXiv 2305.05752](https://arxiv.org/pdf/2305.05752)) [S]. Savant's Swing/Take uses four zones (heart, shadow, chase, waste) ([Tangotiger](https://tangotiger.com/index.php/site/article/statcast-lab-swing-take-and-a-primer-on-run-value)) [S].

**The 2025-26 result that matters most.** Powers and Yurko modeled intended swing speed by count and location on 685,143 pitches from 2024. Slowing swings with more strikes cuts strikeouts but costs power, and the two roughly offset for the average batter ([Rice news](https://news.rice.edu/news/2026/should-hitters-change-their-swing-based-count-rice-study-weighs-in), [arXiv 2507.01238](https://arxiv.org/pdf/2507.01238)) [S]. The average is neutral, so hitter-specific estimates are what make a "contact" versus "damage" option pair worth offering. Raw bat speed conflates intent with pitch and timing, so use residuals against what is expected for the pitch [S].

| Metric or method | Needs | Evidence | Reliability reported | Verdict |
|---|---|---|---|---|
| Swing/take decision value vs league damage | Pitch location, count | Multiple public analogues [S] | Chase split-half r-squared just above 0.5 [S] | Adopt, but score against the hitter's own damage [I] |
| Swing-quality model (aSwing+ style) | Bat tracking, pitch location | Single-author blog [S] | .80 at about 50 swings, unverified | Use as covariate on Hawk-Eye data only |
| Count-conditioned bat speed and swing length | Bat tracking | Powers and Yurko [S]; strike lowers swing speed 0.89 mph, ball raises 0.46 mph [S] | Not found | Adopt where bat tracking exists |
| Attack angle and intercept residual vs expected for pitch height | Bat tracking | Average attack angle about 16 / 9 / 7 degrees on low / middle / high pitches [S] | Not found | MEDIUM, condition on height and approach angle |
| Swing path tilt, attack direction | Bat tracking | Tilt hard to change (analyst claim) [S] | Not found | Low priority |
| Hitter heat maps | Pitch location | BP: poor future prediction even with four zones [S] | Poor | Use only with spatial smoothing and shrinkage |
| Zone damage by pitch type | Pitch data | Standard | Sample-hungry | Pool via hierarchical model |

**Stabilization at Single-A scale.** Reported benchmarks: K% about 60 PA, BB% about 120 PA, HR rate about 300 PA, ISO about 550 PA, a swing-decision metric about 255 pitches ([Athlon](https://athlonsports.com/fantasy/fantasy-baseball-when-do-batter-stats-matter-2026), [Salorio](https://adamsalorio.substack.com/p/introducing-my-swing-decision-model)) [S; per-number attribution not verified]. A roughly 450 to 550 PA season [I, unsourced] sits near the K% and BB% range and far from ISO and AVG. So shrink outcomes heavily to level, league and park priors and lean on process metrics. Sample-splitting cut flagged changepoints in chase and whiff by 88 to 89% in 2023-24 data ([arXiv 2510.25961](https://arxiv.org/pdf/2510.25961)) [S], a warning against reading short-run swings as real changes.

**Not found.** Platoon swing-shape numbers, recognition and timing evidence, within-game fatigue for hitters, stabilization for whiff, zone contact, xwOBAcon, bat speed, attack angle and tilt.

## 4. Starter metrics and data: usage and location first, Stuff second

**Pitch-quality (Stuff) models.** FanGraphs Stuff+ uses physical traits only; Location+ uses location, count and pitch type; Pitching+ combines both. All are XGBoost on run value, indexed to 100 ([FanGraphs primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/)) [S]. Reported reliability is about 80 pitches for Stuff+ and about 400 for Location+, with year-over-year r about 0.73 and 0.48 [S; attribution between FanGraphs and pitching.dev unclear]. PitchingBot trains separate Overall, Stuff and Command models ([FanGraphs](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/)) [S]. BP's StuffPro and PitchPro chain swing probability, take outcomes, swing outcomes and a batted-ball value model ([BP](https://www.baseballprospectus.com/news/article/89245/stuffpro-pitchpro-introduction-new-pitch-metrics-bp/)) [S].

| Option | Inputs | Target | Strength | Weakness | Verdict |
|---|---|---|---|---|---|
| Rebuild gradient boosting, run-value target | Velocity, movement, spin, release, extension, pitcher-relative differentials | Run value per pitch | Reproducible, you own it [I] | Noisy target; MLB-trained, may not transfer to Single-A calibration [I] | Adopt (rank 8) |
| Whiff-probability target (jakeyoung1/pitchquality, MIT) | Velocity, spin, axis, VAA, HAA | P(whiff given swing) | Self-reported held-out AUC .767; adding VAA/HAA raised AUC from .652 to .767 ([repo](https://github.com/jakeyoung1/pitchquality)) [P, self-reported] | Single author, logistic model | Read, copy only after license file check |
| BP-style chain | As above plus count, batter side | Run value via sub-models | Interpretable stages | More models to maintain | Alternative structure |
| FanGraphs export | Published grades | Stuff+ etc. | Free comparison | Terms unread; MLB only | Comparison feature, not training input |

**Command and location from public data only.** There is no catcher target, so there are two substitutes. First, expected run value by location, count, pitch type and batter side (Location+ style). Second, self-referenced dispersion: distance from the pitcher's own average location by pitch type, or the xCTRL approach of fitting a Gaussian mixture per pitcher, pitch type, batter side and season to infer where he aims ([arXiv 2508.19184](https://arxiv.org/pdf/2508.19184)) [S]. The paper notes that Location+ conflates control with conformity, since it assumes everyone should aim at the same place [S]. For a hitter plan, where this starter actually lands by count matters more than a scalar command grade [I]. xCTRL validation numbers were not retrieved.

**Sequencing.** Next-pitch models reach about 40 to 50% on all pitch types and about 78 to 81% on fastball versus not, best in hitter-favored counts and worst at 1-2 and 0-2 ([arXiv 2603.04874](https://arxiv.org/pdf/2603.04874), [SciTePress](https://www.scitepress.org/Papers/2014/47639/47639.pdf)) [S]. Most of this is baseline: the pitcher's own mix by count already captures much of it [I]. One unreviewed, unlicensed repo's claim that the previous pitch adds about 12.8 millibits versus 102 for pitcher hand and 58 for count, with year-to-year r 0.22, points the same way [S, weak]. Tunneling: no public metric has been shown to explain performance ([Prospects Live](https://www.prospectslive.com/the-mystic-art-of-pitch-tunneling/)) [S].

| Starter feature | Evidence | Sample issue | Build? |
|---|---|---|---|
| Usage by count and batter side, hierarchical Dirichlet shrinkage | Standard method; direct plan input [I] | One start is about 90 pitches; shrink to pitcher-season and league | Yes, first |
| Drift vs pitch count: velocity, release, shape, usage | About 70% of pitchers lose velocity first to last inning; 85% show release change ([FanGraphs](https://fantasy.fangraphs.com/in-game-velocity-changes-when-fatigue-attacks/)) [S, PITCHf/x era]; xwOBA rises smoothly through a game with no step at each time through the order ([arXiv 2210.06724](https://arxiv.org/pdf/2210.06724)) [S] | Needs first-inning baseline | Yes |
| Stuff by pitch type | Stabilizes about 80 pitches [S] | Coarse per start | Yes |
| Location run value and dispersion | About 400 pitches to stabilize [S] | Heavy shrinkage per start | Yes, after the above |
| VAA, arm angle, extension | Flatter VAA at the top of the zone aids whiffs [S] | Extension differs by tracking system | Descriptive only |
| Next-pitch probabilities | 40-50% multiclass [S] | Must beat the baseline | Only if it does |
| Tunneling, seam-shifted wake | No validated evidence [S] | n/a | Defer |

**Gap.** No source tests which starter features improve hitter outcomes in approach planning. The ranking above is untested and rests on relevance, sample feasibility and evidence strength [I].

## 5. Plan generation: tags in, diverse near-optimal options out

**Method comparison for producing 2 to 3 meaningfully different options.**

| Method | Idea | Evidence | Fit | Risk |
|---|---|---|---|---|
| Single argmax per count | One best plan | n/a | Fails the brief (options required) | None new |
| Pareto front over axes (contact vs damage, zone width, target) | Show trade-offs ([IJCAI 2023 survey](https://www.ijcai.org/proceedings/2023/0755.pdf)) [S] | Mature | Good for framing | Front can be large |
| Near-optimal band plus MMR/DPP diverse top-k | Keep options within a posterior-probability band of the best, then pick for dissimilarity ([arXiv 2212.14464](https://arxiv.org/pdf/2212.14464)) [S] | Recommender literature; no sport use found | Best fit | Distance metric is a design choice [I] |
| Robust or risk-sensitive value (mean vs lower quantile) | Gives principled reason for both "contact" and "damage" paths to be reasonable ([arXiv 2405.10221](https://arxiv.org/pdf/2405.10221)) [S] | Mature | Good | Needs well-calibrated posteriors |
| Thompson sampling selection | Randomized choice from posterior draws ([Chapelle and Li](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/thompson.pdf)) [S] | Mature | Helps later off-policy evaluation | Stochastic output may confuse coaches |

**Design proposed [I].** For each hitter and count, enumerate candidate approaches as combinations of tags, score each with posterior draws from the hitter and starter models, keep those within a band of the best, then choose 2 to 3 by greedy MMR on a behavioral distance (difference in target zone and pitch-type basis), not on value. Log propensities so overrides can be evaluated later.

**Should hitters vary approach at all?** Kovash and Levitt (2009) found pitchers throw too many fastballs and play-calling shows negative serial correlation ([NBER w15347](https://www.nber.org/papers/w15347)) [S]. A 2024 paper reports the opposite for most players in a swing/take versus inside/outside game ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S2773161824000168)) [S, abstract only]. Nothing directly tests hitter-side variation. So the engine should neither hard-code "randomize" nor "exploit predictability", and should surface the starter's predictability by count as an input with uncertainty [I].

**Learning from overrides.** Learning-to-defer ([Mozannar and Sontag 2020](https://proceedings.mlr.press/v119/mozannar20b.html)) and off-policy evaluation (doubly robust) apply, provided the shown set, choice and propensities are logged [S]. Override rates in clinical alerting run 49 to 96%, with about half appropriate ([systematic review](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7400042/)) [S], so overrides are not errors. No sport-specific study exists.

## 6. Other sports: borrow structure, not results

| Sport | Transferable idea | Evidence quality | Limit |
|---|---|---|---|
| NFL | Enumerate options, convert to common value, rank; show outcome tree; log overrides with reasons. Romer found teams went for it on 108 of 1,100 fourth downs where going was better, which he attributes to job-security incentives ([Romer](https://eml.berkeley.edu/~dromer/papers/PAPER_NFL_JULY05_FORWEB_CORRECTED.pdf)) [S]. NFL tool output is a printable card because league rules bar technology in the booth ([NFL.com](https://www.nfl.com/news/introducing-the-next-gen-stats-decision-guide-a-new-analytics-tool-for-fourth-do)) [S] | Mixed; adherence figures are journalistic | One decision-maker, rare high-leverage events; baseball is frequent and low-leverage |
| NBA | Separate decision quality (qSQ) from execution (qSI) ([ESPN glossary](https://www.espn.co.uk/fantasy/basketball/story/_/id/20712582/fantasy-basketball-analytics-glossary)) [S]. Warning from "Moreyball": league-average value pushes everyone to the same option [I] | No published validation of qSQ | Proprietary |
| Soccer | State-value credit by change in value (VAEP, [paper](https://janvanhaaren.be/assets/papers/kdd-2019-vaep.pdf)); count states map to this [S] | Peer-reviewed for retrospective credit | No opponent-plan use documented |
| Tennis | Hierarchical shrinkage; mixed strategy near but not at equilibrium ([Swartz et al.](https://www.sfu.ca/~tswartz/papers/tennis1.pdf)) [S] | Texts unread | Near-simultaneous choice, unlike hitting |
| Cricket | Nearest-neighbor expected outcome by tracked line and length ([CricViz](https://cricviz.com/cricviz-develops-new-batting-and-bowling-metrics-for-the-world-cup/)) [S] | Snippet only | Unverified workflow |
| Hockey, golf, esports | Not researched | None | No claim made |

The transfer worth keeping: score decisions against context-conditional expectations, then judge execution separately, so a good decision with a bad result is credited as a good decision. This fits a development-first mission.

## 7. Coach-facing design and approach vocabulary

**Vocabulary.** Coach sources agree on a core set: hunt a location, sit on a pitch type or timing, adjust off it, and two-strike modifications (shorten, protect, expand) ([Driveline](https://www.drivelinebaseball.com/2022/08/developing-a-baseball-hitting-approach/), [GRB Academy](https://grbacademy.com/2025/02/24/the-art-of-two-strike-hitting/)) [S]. Coaches split on whether to expand the zone with two strikes, which is a reason to tag rather than name options aggressive or passive [S]. All axes below are my proposal [I] and need coach review.

| Tag axis | Values (proposed) | Example of two options that share intent but differ |
|---|---|---|
| Zone target | inner, middle, away, up, down, middle-out | "Hunt away" vs "hunt inner" |
| Pitch basis | sit fastball, sit offspeed, react | Sit fastball vs react |
| Timing | sit-fast adjust-slow, neutral | |
| Zone width | narrow, standard, expanded | |
| Swing intent | damage, contact (shorten), situational (move runner, sac fly) | Damage vs contact |
| Count role | hitter's, even, two-strike | Derived from the count |
| Risk note | e.g., chase risk, called-strike risk | Informational |

**Board.** One row per hitter (9), counts across (grouped as hitter's, even, two-strike, then expandable to all 12), 2 to 3 cards per count in identical tag slots, a mini zone outline on each card, a sample-size badge (for example "n=38 pitches") with cells hidden below a minimum, a default marker shown as a suggestion, and "choose other or write own" that records a reason tag. Two modes: pregame, printable, and post-game review comparing planned path with actual swing/take by zone as development feedback, not compliance. Public descriptions suggest the real slot is short: a hitting-coach meeting of up to about 15 minutes at the Yankees ([MLB.com](https://www.mlb.com/news/yankees-doubleheader-behind-the-scenes)) and night-before reports plus one-on-one meetings at the Orioles ([The Banner](https://www.thebanner.com/sports/orioles-mlb/orioles-hitting-meetings-individual-approach-FLG3E7UP2REEBFCGRM3PRC5VSI/)) [S]. Nine hitters in 15 minutes is under two minutes each [I], which argues for a glanceable card.

**Why 2 to 3 options.** Two meta-analyses find the average choice-overload effect near zero with large variation by task difficulty, set complexity and preference uncertainty ([Chernev et al. 2015](https://chernev.com/wp-content/uploads/2017/02/ChoiceOverload_JCP_2015.pdf)) [S]. Explanations did not reduce automation bias and sometimes raised it ([Vered et al. 2023](https://psychologicalsciences.unimelb.edu.au/__data/assets/pdf_file/0019/5252131/2023Vered.pdf)) [S], so show evidence beside each option without persuasive framing, and make override one tap.

**Display.** Follow Savant's batter-view zone with red good and blue bad as the familiar convention ([Savant Swing/Take](https://baseballsavant.mlb.com/swing-take)) [S], but because red-blue is not safe for every viewer, put numbers in cells, outline the planned zone over a faint damage map and test with a color-vision simulator [I]. No coach usability evidence was found for any of this.

## 8. Minor league specifics: TrackMan, Hawk-Eye and thin data

**System differences.** TrackMan is radar and infers release and spin from the trajectory; Hawk-Eye is a 12-camera optical system that sees release, measures spin components directly and powers bat and skeletal tracking ([THT](https://tht.fangraphs.com/theres-lots-of-physics-to-do-now-that-hawk-eye-is-up-and-running/), [Baseball Cloud](https://baseballcloud.blog/2020/08/14/is-hawk-eye-inflating-extensions/)) [S]. At Hawk-Eye's 2020 debut, league-average extension was about 1/3 ft above TrackMan/PITCHf/x, and the offset looked consistent [S].

| Metric | TrackMan | Hawk-Eye | Handling |
|---|---|---|---|
| Velocity, movement, plate location | Reliable [I] | Reliable | Use directly after coordinate adapter |
| Batted-ball EV, launch angle, direction | Available [I] | Available | Use directly |
| Extension, release point | Inferred, less reliable [I] | Observed; reads longer [S] | Additive offset per system, estimated from pitchers seen in both [I]; none published for minors |
| Spin direction, gyro | Inferred [I] | Direct [S] | Stuff model must not depend on it unless harmonized |
| Bat speed, swing length, attack angle | Not available [I] | Available [S] | Swing-intent features only on Hawk-Eye; fall back to swing/take and zone contact |
| Plate-location origin | Front of plate (TrackMan docs) [S] | Savant moved to middle of plate in 2026 [P] | Per-source, per-season adapter |

**Coverage.** Public Savant minor-league Statcast covers Triple-A from 2023 and only Florida State League parks for Single-A from 2021 ([Savant](https://baseballsavant.mlb.com/statcast-search-minors)) [P]. No California League coverage was seen, and nothing about Visalia's tracking system was found [S]. Training on public Single-A pitch data for Visalia is therefore not possible, and the PoC runs on MLB data with a plan to recalibrate on club feeds [I]. MLB's takeover plan says Hawk-Eye for all minor-league games from 2026 ([Baseball America](https://www.baseballamerica.com/stories/8-takeaways-from-mlbs-new-minor-league-data-regulation-plan/)) [S]; whether it was executed by October 2026 is unverified, so keep the system as a covariate.

**Level, league and park effects.** The California League was historically the highest run environment in full-season ball (over 5 runs per game in 2007-2009), more than a run above the Florida State League ([THT](https://tht.fangraphs.com/minor-league-run-environments/)) [S, old data]. Refit hierarchical priors by level, league and park each season and carry latent player traits across promotions [I]. ABS challenge exists in Triple-A and, from 2026, MLB; Single-A ABS status in 2025-26 was not confirmed [S]. If it applies at the club's level, called-strike modeling changes.

**Not found.** TrackMan's official field list beyond the glossary, any published cross-system harmonization method, tracked swings per hitter, pitches per Single-A starter, starts per pitcher, and roster turnover.

## 9. Evaluation design and pre-registerable tests

**Design.** Evaluate in three stages: offline model tests on MLB held-out seasons, offline replay on club data, then a staged live trial. The live trial should be a Bayesian hierarchical stepped-wedge across hitters with staggered start dates (permanent switch suits a development setting where carryover makes crossover weak) ([BMC 2022](https://link.springer.com/article/10.1186/s12874-022-01550-8), [Tong et al. 2025](https://journals.sagepub.com/doi/abs/10.1177/17407745241276137)) [S], with an N-of-1 crossover by opponent-starter series only for hitters where carryover is judged small ([arXiv 2110.08970](https://arxiv.org/pdf/2110.08970)) [S]. Power the primary metric on process (plan-consistent swing share, swing-decision run value per pitch) and report wOBA only as secondary with posterior intervals. No power calculation was run by the researchers, and none exists for hitter outcomes; every sample size below is a planning heuristic that must be confirmed by simulation against the engine's own per-pitch variance [I].

**Pre-registration rules.** Fix thresholds, splits and metrics before looking at held-out data. Train on seasons before the cut, test on seasons after (2024-2025 as a candidate hold-out for MLB PoC work; the club's most recent season for Single-A). Stop at first failure per row; a failed row means do not ship that component, not re-tune until it passes.

| Addition | Held-out design | Pass rule (proposed) | Sample needed (heuristic) |
|---|---|---|---|
| Coordinate and system adapter | Pitchers or parks seen in both systems or before and after the 2026 convention change | Residual offset in plate location and extension after adapter within a pre-set tolerance (set from system precision); no residual system effect in a model of movement and location | Pitchers observed in both systems: at least 30 pitchers, 200 pitches each |
| Hitter shrinkage model (swing/take by count and zone) | Season-forward split; hitters with at least 300 pitches in training | Held-out log loss beats (a) league-by-count baseline and (b) unshrunk hitter rates; calibration slope 0.9 to 1.1 | At least 200 hitter-seasons; at Single-A, at least 100 hitters |
| Decision value scored vs hitter's own damage | Split-half and next-season | Split-half reliability at or above 0.6 at 250 pitches and next-season correlation above that of chase% (r-squared about 0.5 benchmark [S]) | At least 100 hitters, 250 pitches each |
| Count-conditioned swing intent (Hawk-Eye) | Replicate Powers and Yurko direction on next season | Same sign for bat-speed-by-strikes effect on strikeout and power in hold-out; per-hitter effect shrinks to prior when n is small | At least 100 hitters, 200 swings each on bat-tracked parks |
| Starter usage by count and side | Forward split by starts; each starter's last starts held out | Held-out log loss beats raw count-by-side frequencies and pitcher-season average, with calibration slope 0.9 to 1.1 | At least 150 starters, 10 starts each |
| In-game drift | Hold out later innings per start | Mean absolute error of predicted velocity and release vs a "first-inning baseline held constant" model improves by a pre-set margin | At least 150 starters, 10 starts each |
| In-house Stuff model | Next-season split; correlate with FanGraphs Stuff+ by pitch type | Held-out whiff-given-swing AUC at or above 0.75 (repo self-report .767 [P, self-reported]); year-over-year r at least 0.6; adds predictive value for next-start outcomes beyond the pitcher's shrunk run value | At least 700k pitches (one MLB season) |
| Location dispersion (xCTRL-style) | Next-season split | Improves held-out location log-likelihood versus pooled-by-pitch-type density; incremental to Location+ proxy | At least 300 pitchers, 400 pitches each |
| Next-pitch probabilities | Forward split | Beats count-by-side baseline on log loss and calibration; otherwise drop | Same as usage |
| Plan generator: option diversity and quality | Offline, then coach rating | Every shown option within the posterior band of the best; pairwise behavioral distance above a threshold; at least 80% of sets rated "meaningfully different" by blinded coach review | At least 100 hitter-count sets reviewed by the coach |
| Override logging and doubly robust evaluation | Replay club logs | Estimator variance small enough that a 95% interval excludes zero for at least one process contrast; coach reasons coded for at least 90% of overrides | Several hundred logged decisions; may not be reached in one season |
| Live trial | Bayesian stepped-wedge | Posterior probability above 0.9 that plan-consistent swing share and decision value improve; no worsening of K% beyond a pre-set margin | Staggered start across all nine hitters; confirm with simulation |

## 10. Ranked risks and unknowns

| Rank | Risk or unknown | Why it matters | What would resolve it |
|---|---|---|---|
| 1 | MLB data terms bar club use [S] | Could invalidate the production data path | Read gdx.mlb.com/components/copyright.txt and mlb.com terms; counsel opinion; written MLBAM authorization or MLB feed |
| 2 | No public Single-A (California League) pitch data and unknown club TrackMan/Hawk-Eye mix | PoC may not transfer to Single-A | Obtain a club export sample; run the adapter test above |
| 3 | Cross-system harmonization has no published method | Stuff and release features may be biased by system | Estimate offsets from dual-system pitchers; test residual system effects |
| 4 | Single-A sample sizes are tiny and turnover is unknown | Hitter and starter estimates may be mostly prior | Count tracked swings per hitter and pitches per starter in the club's data |
| 5 | Almost every claim here is snippet-only | Numbers may be misreported | Verify Section 11 items from primary pages |
| 6 | Option diversity may not equal option usefulness; no coach validation of tags or layout | Tool may be ignored | Coach review of tags and a mock board; the diversity test above |
| 7 | Coaches' acceptance and automation bias; override data confounded by coach knowledge | Weakens learning from overrides and adoption | Reason codes; track aggregate adherence, not per-decision |
| 8 | Evidence that hitter approach changes help is thin (hitter-side mixing untested; two-strike tradeoff neutral on average) | Engine could recommend changes with no true payoff | Staged trial; hitter-specific effects with shrinkage |
| 9 | Stuff models trained on MLB may miscalibrate at Single-A | Wrong starter quality signals | Domain check on club data; recalibrate by level |
| 10 | Bat tracking unavailable at TrackMan parks and public minors | Swing-intent features limited | Confirm which parks have Hawk-Eye; fall back to swing/take features |
| 11 | Plate-location convention change in 2026 and Statcast revisions | Silent coordinate errors | Per-season adapter; checksum tests |
| 12 | Ranking of starter features is untested | May build the wrong thing first | Stage-gated tests above |

## 11. What must be verified from the primary page before building

| Item | Currently | Primary page to read |
|---|---|---|
| MLBAM terms: individual, non-commercial, non-bulk; org and bulk limits; Savant-specific terms; whether derived models are covered | Search summary only | gdx.mlb.com/components/copyright.txt; mlb.com terms of use; Savant terms |
| Savant CSV row cap and rate limits | Unverified (25,000 cap) | [Savant CSV docs](https://baseballsavant.mlb.com/csv-docs) |
| MLB minor-league data takeover: what clubs get, in what format, and when | Search summary of two blocked pages | [Baseball America](https://www.baseballamerica.com/stories/8-takeaways-from-mlbs-new-minor-league-data-regulation-plan/), [MLB Data Warehouse](https://www.mlbdatawarehouse.com/p/mlb-to-regulate-minor-league-data) |
| Whether Hawk-Eye is installed at the club's parks and which league parks are covered | Not found | Club and league operations |
| Hawk-Eye extension offset and plate accuracy | Search summaries (about 1/3 ft; about 1/4 inch) | [Baseball Cloud](https://baseballcloud.blog/2020/08/14/is-hawk-eye-inflating-extensions/), [ESPN](https://www.espn.com/mlb/story/_/id/26753650/robo-umps-not-fast-here-mlb-technology-upgrade-means) |
| Stuff+ and Location+ stabilization (80 and 400 pitches; r 0.73 and 0.48) | Attribution unclear | [FanGraphs primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/), [pitching.dev](https://pitching.dev/stuff-the-future-of-pitching-analytics) |
| Powers and Yurko numbers and conclusion | Search summaries | [arXiv 2507.01238](https://www.arxiv.org/abs/2507.01238) |
| aSwing+ .80 reliability at 50 swings | Single-author blog snippet | [Salorio](https://adamsalorio.substack.com/p/a-closer-look-at-swing-decision-metrics) |
| xCTRL method and validation | Snippet | [arXiv 2508.19184](https://arxiv.org/pdf/2508.19184) |
| Stabilization benchmarks (K% 60 PA, etc.) | Attribution per number unverified | [Athlon](https://athlonsports.com/fantasy/fantasy-baseball-when-do-batter-stats-matter-2026) |
| jakeyoung1/pitchquality LICENSE file and metrics | Page summary only | [repo](https://github.com/jakeyoung1/pitchquality) |
| Kovash and Levitt, and the 2024 minimax paper | Snippets | [NBER](https://www.nber.org/papers/w15347), [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S2773161824000168) |
| NFL adherence figures | Journalistic summaries | NFL fourth-down primary data |
| Retrosheet and Chadwick license statements | Search snippet | [Retrosheet notice](https://www.retrosheet.org/notice.txt), [Chadwick repo](https://github.com/chadwickbureau/register) |

## 12. Annotated reading list

| Priority | Source | Why read it | Status |
|---|---|---|---|
| 1 | [MLB-StatsAPI README](https://github.com/toddrob99/MLB-StatsAPI) | Points to the governing notice | Read [P] |
| 1 | [Savant CSV docs](https://baseballsavant.mlb.com/csv-docs) | Fields, 2026 coordinate change | Read [P] |
| 1 | [Savant minor league search](https://baseballsavant.mlb.com/statcast-search-minors) | Public minors coverage | Read [P] |
| 1 | [Powers and Yurko, arXiv 2507.01238](https://www.arxiv.org/abs/2507.01238) | Count-conditioned swing intent | Snippet [S] |
| 1 | [BART plate discipline, arXiv 2305.05752](https://arxiv.org/pdf/2305.05752) | Closest published analogue to the swing/take engine | Snippet [S] |
| 1 | [xCTRL, arXiv 2508.19184](https://arxiv.org/pdf/2508.19184) | Command from public data | Snippet [S] |
| 1 | [FanGraphs Stuff+ primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/) | Stuff model structure | Snippet [S] |
| 1 | [Baseball America takeover piece](https://www.baseballamerica.com/stories/8-takeaways-from-mlbs-new-minor-league-data-regulation-plan/) | Minor-league data regime | Snippet [S] |
| 2 | [jakeyoung1/pitchquality](https://github.com/jakeyoung1/pitchquality) | MIT whiff model, VAA/HAA value | Page summary [P, summary] |
| 2 | [pitchpredict](https://github.com/baseball-analytica/pitchpredict) | MIT next-pitch baseline; LICENSE read | Read [P] |
| 2 | [pybaseball](https://github.com/jldbc/pybaseball), [baseballr](https://github.com/BillPetti/baseballr) | Data-access code, MIT | Read [P] |
| 2 | [BP StuffPro/PitchPro](https://www.baseballprospectus.com/news/article/89245/stuffpro-pitchpro-introduction-new-pitch-metrics-bp/) | Alternative Stuff structure | Snippet [S] |
| 2 | [Result diversification survey, arXiv 2212.14464](https://arxiv.org/pdf/2212.14464) | MMR and DPP for option sets | Snippet [S] |
| 2 | [Bayesian vs REML for stepped-wedge, BMC 2022](https://link.springer.com/article/10.1186/s12874-022-01550-8) | Few-cluster evaluation design | Snippet [S] |
| 2 | [Mozannar and Sontag 2020](https://proceedings.mlr.press/v119/mozannar20b.html) | Learning to defer | Snippet [S] |
| 2 | [Burke 4th-down study](http://www.advancedfootballanalytics.com/2009/09/4th-down-study-part-3.html), [Romer](https://eml.berkeley.edu/~dromer/papers/PAPER_NFL_JULY05_FORWEB_CORRECTED.pdf) | NFL option ranking and adherence | Snippet [S] |
| 3 | [Driveline hitting approach](https://www.drivelinebaseball.com/2022/08/developing-a-baseball-hitting-approach/) | Coach vocabulary | Snippet [S] |
| 3 | [Savant Swing/Take](https://baseballsavant.mlb.com/swing-take) | Zone display convention | Snippet [S] |
| 3 | [Vered et al. 2023](https://psychologicalsciences.unimelb.edu.au/__data/assets/pdf_file/0019/5252131/2023Vered.pdf), [Chernev et al. 2015](https://chernev.com/wp-content/uploads/2017/02/ChoiceOverload_JCP_2015.pdf) | Option count and automation bias | Snippet [S] |
| 3 | [Swartz et al. tennis](https://www.sfu.ca/~tswartz/papers/tennis1.pdf), [VAEP](https://janvanhaaren.be/assets/papers/kdd-2019-vaep.pdf) | Other-sport methods | Snippet [S] |
| 3 | [THT minor league run environments](https://tht.fangraphs.com/minor-league-run-environments/) | Level and park priors (2007-09 data) | Snippet [S] |

## What this changes

The hard part is access and fit, not the algorithm. Every method above is reproducible from public descriptions with permissively licensed tools, but the data that makes it matter, Single-A pitch tracking, is not public for the club's league, and the public MLB feeds that would stand in for it appear to carry terms that block organizational use. The first deliverable should therefore be a data-rights answer and a club-data adapter test, not a model.

The second shift is in what success means. Because the average two-strike tradeoff is roughly neutral, outcome gains are likely small and slow to measure, and hitters in a development setting are the unit of analysis. Powering process metrics, shrinking hard, and treating overrides as information rather than errors is the defensible path; claims about winning should wait.
