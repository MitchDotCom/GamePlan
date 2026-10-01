# Starter-side metrics and sequencing for hitter approach plans

Research limits: library.fangraphs.com, drivelinebaseball.com, baseballprospectus.com and arxiv.org were EGRESS_BLOCKED for page fetch, so findings come from web-search result summaries only (not full-text reads). Treat figures as search-snippet level and re-verify before relying on them. Sources omitted for license reasons: 3 (public GitHub repos with no license found/stated; not used). Sources are cited as publications/methodology descriptions; no code was reviewed.

## Pitch-quality (Stuff) models: inputs, target, algorithm, stability, rebuild route, FanGraphs export

### Takeaway
FanGraphs Stuff+/Location+/Pitching+, PitchingBot, and BP StuffPro/PitchPro are all supervised models of per-pitch run value from tracking fields; Stuff+ stabilizes fast (~80 pitches) while Location+ is slow (~400). The approach (XGBoost on public Statcast fields, run-value target) is reproducible from scratch from the published descriptions without copying code.

### Cited Findings
- Stuff+ uses only physical characteristics (release point, velocity, vertical/horizontal movement, spin); Location+ is count- and pitch-type-adjusted and ignores physical traits; Pitching+ is a third model using physical traits, location and count, not an average of the two — [FanGraphs Stuff+/Location+/Pitching+ primer (via search summary)](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/)
- Models are XGBoost, trained against run values, indexed to 100 = average — [same primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/)
- Reported reliability: Stuff+ reliable at ~80 pitches, Location+ ~400; year-over-year correlation about 0.73 (Stuff+) vs 0.48 (Location+). Search summary did not clearly attribute to one page among FanGraphs primer / pitching.dev; verify — [FanGraphs primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/), [pitching.dev](https://pitching.dev/stuff-the-future-of-pitching-analytics)
- PitchingBot (Cameron Grove): Statcast inputs incl. pitcher/batter handedness, zone height, count, velocity, spin, movement, release point, extension, location; XGBoost with cross-validation and depth/steps tuned for lowest MSE; separate Overall, Stuff, and Command (location-only: pitch type, count, handedness, location) models — [FanGraphs PitchingBot primer](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/), [FanGraphs announcement](https://blogs.fangraphs.com/pitchingbot-and-stuff-pitch-modeling-are-now-on-fangraphs/)
- BP StuffPro/PitchPro: runs per 100 pitches; inputs are pitch/release physical characteristics, batter handedness, count; PitchPro adds location. Chain of sub-models: swing probability (all pitches), take outcomes (taken pitches), swing outcomes (swung pitches), and a batted-ball value model (exit velo, launch angle, spray angle) multiplied by count-specific average run values — [BP intro](https://www.baseballprospectus.com/news/article/89245/stuffpro-pitchpro-introduction-new-pitch-metrics-bp/), [BP leaderboards](https://www.baseballprospectus.com/news/article/89389/bp-announcements-stuffpro-and-pitchpro-leaderboards-player-cards/), [BP arsenal metrics](https://www.baseballprospectus.com/news/article/96026/introducing-new-arsenal-metrics/)
- Driveline published its Stuff+ methodology revisit (2024) and earlier "What is Stuff" (2021); content not readable here — [Driveline 2024](https://www.drivelinebaseball.com/2024/05/revisiting-stuff-plus/), [Driveline 2021](https://www.drivelinebaseball.com/2021/12/what-is-stuff-quantifying-pitches-with-pitch-models/)
- Public replications/explainers exist (Adam Salorio aStuff+ v2; Twinkie Town explainer) — [Salorio](https://adamsalorio.substack.com/p/introducing-astuff-v2), [Twinkie Town](https://www.twinkietown.com/2024/2/7/23592389/mlb-minnesota-twins-understanding-what-goes-into-pitching-stuff-models-analytics-fundamentals)
- Leaderboard export: FanGraphs custom leaderboards have an Export button yielding a CSV of the displayed table; Stuff+/Location+/Pitching+ are selectable columns — [FanGraphs leaderboards guide](https://library.fangraphs.com/how-to-use-fangraphs-leaderboards/). Exact column names and Members-only gating were not confirmed.

### Inferences
- Rebuild route: Savant pitch-level fields + run-value target + XGBoost/GBM, trained by us, avoids copying anyone's code; BP's swing/take/contact-chain is a documented alternative structure. Validate against the FanGraphs export as a comparison feature (correlation by pitch type), not as a training input.
- Because Stuff+ stabilizes in ~80 pitches, a per-start (~90 pitch) profile can use Stuff by pitch type only coarsely; Location+ should be shrunk heavily (~400 pitches) for a single starter.
- Single-A org TrackMan data may differ in calibration from Statcast; models trained on MLB need domain checks.

### Gaps
- No full-text read of FanGraphs, BP, Driveline methodology (blocked); validation metrics, known biases, and minimum samples per pitch type not verified.
- Exact FanGraphs export columns and Members-only/MLB-only details not found.

## Command and location quality from public tracking alone

### Takeaway
Without a catcher target, options are expected-run-value-by-location (Location+ style) and self-referenced dispersion around the pitcher's own typical location; a 2025 paper (xCTRL) fits per-pitcher Gaussian mixtures on public data to infer intent.

### Cited Findings
- Command+ (Stats LLC) models intent as discrete targets using cues like glove placement; Location+ compares outcomes to league expectations by count and pitch type, assuming everyone should aim at the same zones, conflating control with conformity — [arXiv 2508.19184 (search summary)](https://arxiv.org/pdf/2508.19184)
- Simple proxy: Euclidean distance of each pitch from the pitcher's average location by pitch type; independent of whether the target is good — [arXiv 2508.19184](https://arxiv.org/pdf/2508.19184)
- xCTRL: Gaussian mixture fit per pitcher, pitch type, batter handedness and season to learn where he tends to aim; uses public Statcast only — [arXiv 2508.19184](https://arxiv.org/pdf/2508.19184)
- Location+ ~400 pitches to stabilize, YoY ~0.48 (see above).
- Other: Commandf/x measured distance from catcher target (proprietary Sportsvision/MLBAM) — [arXiv 2508.19184](https://arxiv.org/pdf/2508.19184)

### Inferences
- Build two location features: (a) run-value-by-location by count/pitch type/batter side; (b) dispersion around per-pitcher, per-pitch-type, per-batter-side cluster centers. For hitters, the cluster centers (where he actually lands, by count) matter more than a scalar command grade.

### Gaps
- xCTRL stabilization and validation numbers not retrieved.

## Pitch sequencing, next-pitch prediction, tunneling

### Takeaway
Next-pitch type models using pitcher, count, runners, inning, outs, prior pitches reach ~40-50% multiclass and ~78-81% fastball vs non-fastball, with best accuracy in hitter-favored counts. Tunneling metrics have no public evidence of explaining performance.

### Cited Findings
- Pre-pitch context models get 40-50% accuracy for all pitch types — [arXiv 2603.04874 (search summary)](https://arxiv.org/pdf/2603.04874)
- Binary fastball/non-fastball: LDA ~78%, SVM 79.8%, kNN 80.9% — [Applying ML to baseball pitch prediction](https://www.scitepress.org/Papers/2014/47639/47639.pdf); 236 pitchers in 2009 averaged 77.45% in one study, a KNN model 44.25% — [Ganeshapillai & Guttag](https://www.semanticscholar.org/paper/Predicting-the-Next-Pitch-Ganeshapillai-Guttag/e455030bd945ceffcbf2fc99bb12271ee9c013ff), [ResearchGate](https://www.researchgate.net/publication/319131812_Using_multi-class_classification_methods_to_predict_baseball_pitch_types)
- Accuracy higher in batter-favored counts (3-0, 2-0), lower in 1-2 and 0-2 — [Applying ML to baseball pitch prediction](https://www.scitepress.org/Papers/2014/47639/47639.pdf)
- Deep ensemble predicting type and location — [Lee 2022, J Sports Analytics](https://journals.sagepub.com/doi/10.3233/JSA-200559)
- Tunneling: BP published the first public metric in 2017 (separation at 24 ft); "no one has publicly quantified pitch tunneling in a way that actually explains performance" (Prospects Live opinion); alternatives include release-point indistinguishability, integration-based TDR, Deception+ — [Prospects Live](https://www.prospectslive.com/the-mystic-art-of-pitch-tunneling/), [FantraxHQ TDR](https://fantraxhq.com/introducing-tdr-an-integration-based-approach-to-pitch-tunneling/), [Towards Data Science](https://towardsdatascience.com/quantifying-pitcher-deception/)

### Inferences
- Much "accuracy" is a baseline gap: predicting a pitcher's own mix by count already gets most of it; a hitter plan needs calibrated probabilities by count/side, not a classifier. Skip tunneling for v1.

### Gaps
- Accuracy-vs-baseline (majority-class) comparisons, and 2025-26 sequence models (transformers) not retrieved; several cited studies use older PITCHf/x data.

## Usage by count/side, times through the order, fatigue, arm angle, extension, VAA, seam-shifted wake

### Takeaway
Fatigue drift in velocity and release is documented; times-through-order penalty may be a smooth drift rather than steps. VAA depends mainly on extension and release height and flat VAA at the top of the zone aids whiffs.

### Cited Findings
- About 70% of pitchers lose velocity first to last inning; 85% show release point change; April starters lost nearly 1 mph in 5+ inning starts — [FanGraphs fatigue articles](https://fantasy.fangraphs.com/in-game-velocity-changes-when-fatigue-attacks/), [FanGraphs community](https://community.fangraphs.com/can-pitchfx-data-be-used-to-identify-muscle-fatigue/)
- Velocity decline associated with higher contact, lower swinging-strike rate, higher FIP; max velocity change explained 23% of K-rate variance — [FanGraphs community](https://community.fangraphs.com/can-pitchfx-data-be-used-to-identify-muscle-fatigue/)
- Expected wOBA rises steadily through a game without discontinuity at each TTO — [Bayesian TTO analysis, arXiv 2210.06724](https://arxiv.org/pdf/2210.06724); BP also has a 2025 piece on the other side of the TTO penalty — [BP](https://www.baseballprospectus.com/news/article/103768/best-of-bp-2025-the-other-side-of-the-times-through-the-order-penalty/)
- VAA: whiff% rises as four-seam VAA flattens toward 0 (threshold around -4.5 deg in one analysis); extension and release height are main drivers; low arm angle helps — [Iowa Baseball Managers](https://medium.com/iowabaseballmanagers/fastball-vertical-approach-angle-12e2824d245a), [TDA Baseball arm angle](https://www.tdabaseball.com/post/how-important-is-the-new-statcast-arm-angle-data), [Pitcher List](https://pitcherlist.com/exploring-optimal-fastball-traits-through-the-approach-of-luis-castillo/)
- Seam-shifted wake produces extra run/drop on sinkers; it can be estimated using Savant spin direction — [Medium stuff-models](https://medium.com/@bradleyjg03/new-mlb-stuff-models-1be08693d0e4)

### Inferences
- In-game drift is best modeled as pitch-count/inning-continuous deviations from a pitcher's first-inning baseline (velocity, release, IVB/HB, usage), with shrinkage.

### Gaps
- Usage-by-count and batter-side published studies not found; no evidence retrieved on arm-angle drift or SSW validated for hitter approach. Many fatigue sources are PITCHf/x-era.

## Ranked recommendation (starter-side additions)

### Takeaway
Build, in order: (1) usage/location by count and batter side with shrinkage, (2) in-game drift of velocity/shape/release vs pitch count, (3) own Stuff-style run-value model by pitch type, with FanGraphs export as a comparison feature, (4) location run-value plus self-referenced dispersion, (5) VAA/arm angle/extension as descriptive features, (6) calibrated next-pitch probabilities, (7) defer tunneling and SSW.

### Cited Findings
- Stuff stabilizes ~80 pitches vs Location ~400 — see first section; sequencing models' accuracy is highest in hitter-favored counts, where predictability aids approach — see sequencing section.

### Inferences
- Ranking logic is mine: rank by relevance to per-count decisions, sample-size feasibility per starter, and evidence strength. Items 1-2 are direct inputs to count-level plans and need no external model; 3-4 add pitch-quality context; 6 is useful only if probabilities beat a count-by-side baseline; 7 lacks validated evidence.

### Gaps
- No source directly tests which starter features improve hitter outcomes in approach planning; ranking is untested.
