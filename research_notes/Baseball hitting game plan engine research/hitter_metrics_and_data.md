# Hitter-side metrics, models and data for hitter approach plans

Access note: every WebFetch (BP, FanGraphs, MLB.com, arXiv, Medium/Substack, Pitcher List, phys.org, tandfonline) was EGRESS_BLOCKED. All findings below come from WebSearch result summaries only, not full-page reads, so numbers are as the search summarizer reported them and should be re-verified against the primary page. License note: I could not verify licenses of any source (license status is unstated on nearly all pages); I cite facts only, and no source was positively identified as non-commercial/share-alike. Omitted for license reasons: 0 verified (license check not possible from this environment).

## 1. Statcast bat tracking: definitions, measurement, validity, pitch conditioning, public swing-quality models

### Takeaway
Statcast (Hawk-Eye cameras) reports bat speed and swing length at the sweet spot, plus (from 2024) attack angle, attack direction, swing path tilt and intercept. Swing shape depends strongly on pitch height and count, so any use must condition on pitch location/approach angle. Public swing-quality models (aSwing+) exist but I found only secondary descriptions.

### Cited Findings
- Bat speed = linear speed of the bat "sweet spot" (about 6 inches from the end) at contact or estimated contact. Swing length = path length from swing start to (estimated) contact. — [ESPN](https://www.espn.com/mlb/story/_/id/40120458/mlb-statcast-bat-tracking-data-giancarlo-stanton-luis-arraez); [Fangraphs search summary](https://blogs.fangraphs.com/what-statcasts-new-bat-tracking-data-does-and-doesnt-tell-us/)
- Measurement: Hawk-Eye, 12 cameras per park, five at 300 fps; MLB spent 2+ years refining the model. — [ESPN](https://www.espn.com/mlb/story/_/id/40120458/mlb-statcast-bat-tracking-data-giancarlo-stanton-luis-arraez)
- Squared-up: from bat speed and pitch speed compute max possible exit velocity; a batted ball is squared up if actual EV is at least 80% of that max. Blast = squared-up swing that also has high bat speed. — [ESPN](https://www.espn.com/mlb/story/_/id/40120458/mlb-statcast-bat-tracking-data-giancarlo-stanton-luis-arraez)
- Public data began 2H 2023 (bat speed, swing length); 2024 added stance metrics, attack angle, attack direction, intercept, swing path tilt. — [Search summary of Fangraphs/BP](https://blogs.fangraphs.com/test-driving-statcasts-newest-bat-tracking-metrics/)
- Attack angle: vertical direction of the sweet spot's travel at contact (positive = upward); 5-20 deg called "ideal" by MLB glossary. Attack direction: horizontal direction of sweet-spot travel at contact (0 = parallel to front of plate). Swing path tilt: angle of the swing plane vs ground, from the bat path in the 40 ms before contact (higher = steeper). Intercept: point where bat is nearest the ball (also for swings and misses), reported relative to the front of the plate or the batter's center of mass. — [MLB glossary: Attack Direction](https://www.mlb.com/glossary/statcast/attack-direction); [MLB news](https://www.mlb.com/news/new-statcast-swing-metrics-2025)
- Swing tilt is very hard to change, unlike attack angle and direction (analyst claim). — [Search summary](https://blogs.fangraphs.com/what-statcasts-new-bat-tracking-data-does-and-doesnt-tell-us/)
- Pitch-height dependence: average attack angle about 16 deg on low pitches, 9 on middle, 7 on high. — [Creally, Medium](https://medium.com/@mattjcreally/what-can-we-learn-from-pitch-level-swing-shape-data-6bfe153845cf)
- Count: each strike lowers swing speed 0.89 mph, each ball raises it 0.46 mph (2024 game-state analysis of public data). — [GitHub analysis](https://github.com/vavetsbarets/mlb-swing-speed-analysis)
- Powers & Yurko (Rice/CMU): Bayesian hierarchical model of batter "intended" swing speed by count and pitch location, then instrumental-variables regression of bat speed/swing length on contact and power; 685,143 2024 pitches. Result: slowing swings with strikes cuts strikeouts but costs power, roughly offsetting for the average batter; shortening swing length (choking up) can lower strikeout rate. Published in The American Statistician 2026 (arXiv 2507.01238). — [Rice news](https://news.rice.edu/news/2026/should-hitters-change-their-swing-based-count-rice-study-weighs-in); [Search summary](https://www.researchgate.net/publication/393332979_Swinging_Fast_and_Slow_Interpreting_variation_in_baseball_swing_tracking_metrics)
- Raw swing metrics are measured at contact and conflate intent with pitch/timing, so raw bat speed can overstate the value of swinging hard. — [Search summary of Powers & Yurko](https://arxiv.org/pdf/2507.01238)
- Shorter swings whiff less: 19% whiff on shorter-than-average swings vs 30% on longer. Bat speed vs wRC+ r=0.11; swing length vs K% r=0.277. — [Fangraphs summary](https://blogs.fangraphs.com/what-statcasts-new-bat-tracking-data-does-and-doesnt-tell-us/)
- aSwing+ (A. Salorio): CatBoost classifier predicting probability a swing yields ideal contact; inputs bat speed, tilt, attack angle, attack direction, contact point, swing length, interactions, and pitch location plus vertical and horizontal approach angle; trained on 2023-24 batted balls with bat tracking, applied to 2023-25 swings; reliability .80 after about 50 swings. — [Salorio](https://adamsalorio.substack.com/p/a-closer-look-at-swing-decision-metrics) and search summary
- Wearable sensor accuracy literature exists (commercial bat sensors) but is a different measurement system from Hawk-Eye. — [PMC8879135](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8879135/)

### Inferences
- Attack angle/intercept must be modeled conditional on pitch height and approach angle (the engine already has VAA/location); use residual vs expected-for-this-pitch as the hitter trait.
- Swing length and bat-speed-by-count are the cleanest evidence-backed "approach levers"; the two-strike study says the tradeoff is roughly neutral on average, so hitter-specific estimates matter.

### Gaps
- Public "Swing+" other than aSwing+ not found. Savant's measurement validation (error bars on Hawk-Eye bat tracking) not found. Primary Savant glossary text not opened. No YoY r or stabilization numbers for attack angle, tilt, bat speed found.

## 2. Swing-decision metrics

### Takeaway
All metrics compare an expected value of swing vs take given location, count (and in some, movement/approach angle), then credit the actual decision. Reliability numbers were largely not retrievable.

### Cited Findings
- SEAGER (Robert Orr, BP): per-pitch decision value from count, location, likelihood of called strike, and historical damage on swings in that location; roughly "correct takes minus hittable takes"; correlates better with offense (wOBA, ISO) than zone swing or chase, weaker at explaining BB%. — [BP](https://www.baseballprospectus.com/news/article/86572/the-crooked-inning-corey-seager-rangers/) and search summary
- Decision Value (PLV, Pitcher List): inputs velocity, location, movement; rewards swings on hittable pitches and takes on poor ones. — [Pitcher List](https://pitcherlist.com/plv-weekly-analyzing-swing-decisions-with-plv/)
- SwRV (Drew Haugen): event probabilities from pitch-quality models using pitch characteristics and count/handedness estimate swing value and take value; compared by actual decision. — [Down on the Farm](https://downonthefarm.substack.com/p/a-closer-look-at-swing-decisions)
- aDecision+ (Salorio): CatBoost on all pitches with bat tracking 2023-24, predicting expected run value of swing/take from location, vertical/horizontal approach angle, count; similar to his SOTO. — [Salorio](https://medium.com/@adamsalorio/introducing-abatting-639f36647b40)
- Savant Swing/Take: four zones (Heart, Shadow, Chase, Waste); every pitch classified, split by swing/take, run values assigned from pitch location, count and decision. — [Tangotiger/Statcast lab](https://tangotiger.com/index.php/site/article/statcast-lab-swing-take-and-a-primer-on-run-value); [Lookout Landing](https://www.lookoutlanding.com/2019/9/20/20875992/statcast-swing-take-tool-debuts-daniel-vogelbach-should-swing-more-mariners-swing-analysis-seattle)
- Chase (O-Swing%) split-half r-squared reported just above 0.5. — [Fangraphs search summary](https://blogs.fangraphs.com/evaluating-early-season-plate-discipline-breakouts/)

### Inferences
- The engine's swing-versus-take-by-count value is already the SEAGER/SwRV construct; the incremental ideas are (a) conditioning on movement/approach angle, (b) scoring decisions against the hitter's own swing damage, not league average, so that it is a development measure.

### Gaps
- Exact SEAGER formula, YoY r for DV/SwRV/aDecision+, and documented weaknesses (e.g., league-average damage ignores the hitter's own ability; umpire zone effects) were not retrievable; pages blocked.

## 3. Stabilization and reliability; empirical Bayes

### Takeaway
Pitch-level discipline stats stabilize faster than PA-level outcomes; aSwing+ about 50 swings to .80. No retrievable figures for xwOBAcon, attack angle or tilt.

### Cited Findings
- Plate-discipline stats reach reliability faster than PA stats since a batter sees about 4 pitches per PA. — [Search summary, Pitcher List guide](https://pitcherlist.com/a-beginners-guide-to-understanding-plate-discipline-metrics-for-hitters/)
- aSwing+ .80 reliability at about 50 swings. — Salorio (above)
- Sample-splitting cut flagged changepoints by 89% (chase) and 88% (whiff) in 2023-24 data (min 100 swings, 100 out-of-zone pitches). — [arXiv 2510.25961](https://arxiv.org/pdf/2510.25961)
- Hierarchical Bayes/empirical Bayes literature for batting: [Brown 2008](https://arxiv.org/pdf/0803.3697); [Hierarchical Bayesian hitting model](https://arxiv.org/pdf/0902.1360).

### Gaps
- No stabilization points for whiff, zone contact, xwOBAcon, bat speed, attack angle, tilt found.

## 4. Hitter heat maps

### Takeaway
Raw hot/cold zones are noisy; smoothing and shrinkage are required, and even with four zones split-half remained poor.

### Cited Findings
- BP "Spinning Yarn": zone heat maps predict future performance poorly; with more sample split-half improved somewhat but much noise remained even with four zones. — [BP](https://www.baseballprospectus.com/news/article/15363/spinning-yarn-can-we-predict-hot-and-cold-zones-for-hitters/)
- Spatial batting ability modeled with a known covariance matrix. — [ResearchGate](https://www.researchgate.net/publication/276465486_Modeling_spatial_batting_ability_using_a_known_covariance_matrix)
- Hierarchical Bayes shares information across similar entities. — [arXiv 1704.00823](https://arxiv.org/pdf/1704.00823)

### Gaps
- No quantitative minimum sample sizes found.

## 5. Two-strike, platoon, recognition, fatigue

### Takeaway
Two-strike adaptation evidence is the strongest new (2025-26) result; platoon, timing, fatigue evidence not found.

### Cited Findings
- See section 1 (Powers & Yurko 2026; strike/ball effects on swing speed).
- Platoon and switch-hitter swing analysis exists at FanGraphs but contents not read. — [FanGraphs](https://blogs.fangraphs.com/i-had-an-idea-about-bat-tracking-data/)

### Gaps
- Pitch recognition/timing and within-game fatigue: no sourced findings. Platoon swing-shape numbers not retrieved.

## 6. Ranked recommendations (tentative; evidence limited)
1. Count-conditioned swing length and bat speed (intent) per hitter, hierarchical-shrunk; strongest published support (Powers & Yurko).
2. Pitch-conditioned attack angle/intercept residual vs expected for pitch height and VAA (clear height dependence: 16/9/7 deg).
3. Hitter-specific swing/take decision value using movement and approach angle (aDecision+/SwRV style), shrunk.
4. Swing-quality score (aSwing+-style) as a covariate for contact quality; .80 reliability at 50 swings (single-author, unverified).
5. Tilt and attack direction: low priority (tilt hard to change; no reliability data).
Evidence quality: mostly analyst blogs via search summaries; recommend re-verifying against primary pages before adoption.
