# Measuring hitter development with process metrics and decision quality at minor-league sample sizes

Research limits, read first. WebFetch was blocked by the egress proxy for every domain I tried (FanGraphs, Baseball Prospectus, MLB.com, arXiv, PMC, Substack, Pitcher List). All findings below come from web-search result summaries, not from reading the full pages. Every number is therefore secondary and is flagged "snippet-level, verify against the page". Numbers marked "Derived" are my own calculations, with assumptions stated. Evidence tiers: A peer-reviewed or primary data, B named practitioner account, C vendor or marketing, D opinion. Dates were not visible in the snippets unless stated; "date n/v" means not verified. Today is 2026-10-04.

## 1. Which swing-decision and plate-discipline metrics have published reliability?

### Takeaway
Swing rate and contact rate are among the fastest hitting rates to stabilize, on the order of tens to ~100 PA in the classic Carleton work, but I could not verify per-swing or per-pitch figures for chase, zone swing, zone contact or whiff. I found no public reliability figure at all for Statcast swing/take run value, SEAGER, Decision Value or SwRV.

### Cited Findings
- Carleton's method: a stat is "stabilized" when split-half correlation reaches r = 0.70 (about 49% of variance is signal); the 0.50 convention gives the "regress half-way" point. Several sources describe it as a split-half reliability procedure that averages correlations over random halves (Tier A/B, FanGraphs library material, date n/v) — [FanGraphs: A Long-Needed Update on Reliability (title via search)](https://blogs.fangraphs.com/a-long-needed-update-on-reliability); [FanGraphs: A New Way to Look at Sample Size](https://blogs.fangraphs.com/a-new-way-to-look-at-sample-size); [Redleg Nation summary](https://www.redlegnation.com/2016/04/22/when-do-stats-stabilize/). Snippet-level.
- FanGraphs-reported hitter stabilization points: K% 60 PA, BB% 120 PA, HBP rate 240 PA, singles rate 290 PA (Tier B, snippet-level, sample and date n/v) — [FanGraphs library/blog via search](https://blogs.fangraphs.com/randomness-stabilization-regression).
- Reported Carleton stabilization points: swing% 50 PA, contact% 100 PA, K% 150 PA (Tier B; a search-engine summary of a Baseball Prospectus article, which conflicts with the 60 PA K% figure above, so the numbers are not consistent across vintages and methods) — [Baseball Prospectus, Carleton](https://www.baseballprospectus.com/?p=14215). Snippet-level, unverified.
- FanGraphs now states reliability is a spectrum and the library shows reliability graphs per stat; it also offers a confidence-interval tool for a player's rate given sample size (Tier B) — [FanGraphs: Introducing the FanGraphs Library](https://blogs.fangraphs.com/introducing-the-fangraphs-library/).
- A fantasy source says O-Swing% stabilizes "remarkably fast" and about 60 PA suffices to judge early swing numbers; this is a practitioner assertion with no stated method (Tier D) — [search summary of fantasy sources](https://fantraxhq.com/sabermetric-series-part-3-plate-discipline/).
- Statcast Swing/Take Run Value is documented as the run value of the swing-or-take decision on every pitch, relative to the alternative, with a public leaderboard (Tier A for definition; no reliability figure published that I could find) — [Baseball Savant swing-take leaderboard](https://baseballsavant.mlb.com/leaderboard/swing-take); [MLB Statcast glossary](https://mlb.com/glossary/statcast).
- Third-party swing-decision models: SEAGER (Robert Orr, Baseball Prospectus), SwRV (Drew Haugen, "Down on the Farm", also covers MLB and AAA), PLV Decision Value (Pitcher List), plus independent hobbyist models. Claims that SwRV predicts future wOBA better than O-Swing% and SEAGER describes/predicts wOBA and ISO are author claims (Tier B) — [BP: Quantifying the Corey Seager Approach](https://www.baseballprospectus.com/news/article/86572/the-crooked-inning-corey-seager-rangers/); [Down on the Farm: swing decisions](https://downonthefarm.substack.com/p/a-closer-look-at-swing-decisions); [Pitcher List: PLV DV](https://pitcherlist.com/examining-hitters-combining-selectivity-with-aggression-using-plv-dv/).
- Model-based note: SwRV finds only ~33% of pitches have higher expected run value on a swing than a take, against a 48% league swing rate; only 64% of in-zone pitches favor swinging (Tier B, one author's model) — [Down on the Farm](https://downonthefarm.substack.com/p/a-closer-look-at-swing-decisions).
- A Dec-2025-era arXiv preprint proposes a "Discipline Score" from league swing probability (Tier A-, preprint, not peer reviewed; content not read) — [arXiv 2511.19672](https://arxiv.org/html/2511.19672v1).

### Inferences
- The stabilization points above are PA-based for rates whose denominator is not PA (chase uses out-of-zone pitches, zone contact uses zone swings). Per-denominator reliability is unknown from what I could read; expect chase and zone-contact to need more PA than overall swing%, because their denominators are smaller subsets.
- Model-based decision-value metrics add model error to sampling error, so their reliability at 300 PA is probably lower than the raw rates they are built from, but no data was found to confirm that.

### Gaps
- No verified table of stabilization points (in swings or pitches) for O-Swing, Z-Swing, Z-Contact, SwStr/whiff, with sample, season and method. The FanGraphs and BP pages could not be read.
- No published split-half or year-over-year reliability for Statcast swing/take run value, SEAGER, DV or SwRV found. Recommend computing it ourselves from Single-A data once pitch-level feeds exist.
- No published reliability work specific to Single-A (different pitcher quality, hit-tracking vendor and umpiring or ABS use).

## 2. Minimum detectable change (MDC) for each metric

### Takeaway
Under simple binomial assumptions, a hitter with roughly 300 PA in a split season cannot show a change in chase or zone-swing rate below about 10 to 13 percentage points, and a change in zone contact or whiff-per-swing below about 9 to 12 points, with 80% power. Only large approach changes are detectable within a season for a single hitter.

### Cited Findings
- No published MDC figures for these metrics were found. The statistical formula is standard: for a difference in two proportions with equal n per period, MDC ≈ (z_alpha/2 + z_power) × sqrt(2 p(1-p)/n) (Tier A, standard statistics text method; see any power-analysis text such as Cohen's *Statistical Power Analysis for the Behavioral Sciences*; no URL verified).

### Inferences
Derived. Assumptions: independent pitches (ignores pitcher and count mix, so true variance is larger), two-sided alpha 0.05, 80% power (multiplier 2.8), equal n in baseline and post period, league-typical base rates (chase 30%, zone swing 68%, zone contact 84%, whiff per swing 25%, overall swing 46%). The rates are my rough assumed values, not verified from a source.

| Metric (base rate) | n per period | MDC (percentage points) |
|---|---|---|
| Chase, O-Swing (30%) | 100 pitches out of zone | 18.1 |
| Chase | 200 | 12.8 |
| Chase | 400 | 9.1 |
| Zone swing (68%) | 100 | 18.5 |
| Zone swing | 200 | 13.1 |
| Zone contact (84%) | 60 zone swings | 18.7 |
| Zone contact | 150 | 11.9 |
| Zone contact | 300 | 8.4 |
| Whiff per swing (25%) | 100 swings | 17.1 |
| Whiff per swing | 200 | 12.1 |
| Whiff per swing | 400 | 8.6 |
| Overall swing (46%) | 300 pitches | 11.4 |
| Overall swing | 600 | 8.1 |
| Overall swing | 1000 | 6.2 |

- Volume conversion (assumed, not sourced): about 3.9 pitches per PA, so 300 PA is about 1,150 pitches; roughly 45% are out of zone (~520), roughly 40% are zone pitches. Split into halves, that is about 260 out-of-zone pitches per period, giving a chase MDC of about 11 points. Zone swings per half are about 90 to 110 so zone-contact MDC is about 14 to 19 points.
- Comparing a post period against a long, well-estimated prior baseline (single-sided, 1 sample vs known): chase MDC is 11.4 points at 100 out-of-zone pitches, 8.1 at 200, 5.7 at 400 (Derived, same assumptions, alpha .05 one-sided, power 80%).
- Pooled, shrunk estimates (section 3) reduce this by borrowing strength, but do not change the amount of information about a single hitter.
- Decision-value run metrics: no variance data, so no MDC can be derived.

### Gaps
- Overdispersion (true between-game and between-pitcher variance) means real MDCs are larger than the table; the size of that inflation is unknown without Single-A data.
- Autocorrelation across a season (fatigue, injuries, call-ups) is ignored.

## 3. Study designs for tiny samples

### Takeaway
Single-case designs (multiple baseline, stepped rollout), Bayesian hierarchical models and empirical-Bayes shrinkage all fit a few hundred PA per hitter; control charts suit monitoring but not causal claims. Sports-science precedent exists for the single-case and N-of-1 approach; I found no baseball-development example of a stepped rollout.

### Cited Findings
- Sports science uses single-case experimental designs (SCEDs) for individual athletes, including a non-concurrent multiple-baseline design with about four participants (baseline then intervention phases) (Tier A) — [PMC12194246, SCED of a 6-week reactive-strength intervention](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12194246/) (content not read; summary from search); [Single-subject designs for elite athletes' conditioning](https://sponet.de/sponet/Record/4010636).
- Quality problems found in sport-psychology SCEDs: upwardly biased effect sizes from publication bias, not using multiple baselines, and no procedural reliability checks (Tier A) — [Staffordshire eprint, multiple-baseline in sport psychology](https://eprints.staffs.ac.uk/6381/1/Accepted%20Version%20MRA%20in%20Sport%20Psychology_PSE%20June%202020.pdf).
- Bayesian vs frequentist multilevel single-case models: Bayesian approaches showed better Type I error control with small samples (Tier A, simulation) — [Bayesian vs Frequentist in multilevel SCDs](https://portalcientifico.uned.es/documentos/69f8dc6a579ceb0ec2bf3d2f).
- Empirical-Bayes shrinkage: Efron and Morris (1975) showed beta-binomial shrinkage of early-season batting averages beats raw averages under squared-error loss; posterior mean = (alpha + successes)/(alpha + beta + n) (Tier A) — [Hierarchical Beta-Binomial Shrinkage explainer](https://metricgate.com/calculator/hierarchical-beta-binomial-baseball) (secondary explainer; original paper not retrieved).
- Changepoint detection on player performance metrics is the subject of a 2025 arXiv preprint (Tier A-, not peer reviewed; content not read) — [Tractable Algorithms for Changepoint Detection in Player Performance Metrics](https://arxiv.org/html/2510.25961v1).
- A digital-health primer on N-of-1 and single-case designs exists (preprint, not read) — [arXiv 2608.15526](https://arxiv.org/pdf/2608.15526).

### Inferences
- Stepped rollout: stagger the start of an approach intervention across hitters (or across metrics within a hitter) after pre-registered baselines of varying length. With about 8 or more hitters this gives causal leverage that a single before/after cannot.
- Empirical-Bayes per metric: estimate a Single-A prior (mean and variance of true chase, etc. across hitters) and report posterior estimates and intervals, so a 100-pitch jump is shrunk appropriately.
- Control chart (e.g., p-chart or CUSUM on weekly chase) works as an alert for drift, not as proof of effect.
- Pre-register the metric, baseline length and threshold, because the detectable change is large.

### Gaps
- No documented baseball player-development example of multiple-baseline or stepped-rollout evaluation found. No public example of control charts for hitters found.
- Specific effect-size statistics for the sports-science SCEDs not extracted (content unread).

## 4. Separating decision quality from outcome (resulting)

### Takeaway
"Resulting" (Annie Duke) names judging a decision by its outcome. Baseball's closest tools are expected-value swing-decision models that score each swing or take by the expected run value of the pitch, not by what happened. Evidence that this separation is validated for development use is thin.

### Cited Findings
- Duke defines "resulting" as confusing outcome quality with decision quality, deriving quality from one instance; good decisions can have bad outcomes and vice versa (Tier B, practitioner and author, from poker) — [Annie Duke](https://www.annieduke.com/?p=3108); [Wharton summary](https://dca.wharton.upenn.edu/?p=1009539).
- Baseball examples that score the decision by the pitch, not the result: Statcast swing/take run value, SwRV, SEAGER, PLV Decision Value (see section 1). DV rewards swinging at pitches the hitter should hit hard and taking pitches unlikely to produce much, "punishing" the opposite (Tier B/C) — [Pitcher List: PLV DV](https://pitcherlist.com/examining-hitters-combining-selectivity-with-aggression-using-plv-dv/).
- SEAGER values each pitch by count, location, strike probability and historical damage from hitters swinging there (Tier B) — [BP: SEAGER at the Team Level](https://www.baseballprospectus.com/news/article/86926/the-crooked-inning-seager-at-the-team-level/).

### Inferences
- Counterfactual-value scoring still depends on the model's expected-damage estimate, which embeds the average hitter; a hitter with a different true swing profile may be misscored.
- Decision score and result can be tracked separately (e.g., decision score vs wOBA on swings) and divergences read as luck or execution, but this is my design suggestion, not a published method.

### Gaps
- No peer-reviewed validation of swing-decision metrics as measures of decision quality found. No evidence from other fields beyond Duke's poker framing was gathered (e.g., medicine, finance outcome-bias research).

## 5. What goes wrong when process metrics become targets

### Takeaway
Goodhart's law applies: a metric used as a target stops measuring the underlying skill. I found general sports-analytics commentary but no baseball-specific empirical study of hitters gaming chase or decision metrics.

### Cited Findings
- Goodhart: "When a measure becomes a target, it ceases to be a good measure"; in sports, players optimize for the stats they are evaluated on, and suggested countermeasures are multiple metrics, audits and rotating emphasis (Tier D, commentary) — [HoopVision, Incentive Stats & Goodhart's Law (2020-10-02)](https://hoopvision.substack.com/p/incentive-stats-and-goodharts-law); [Keith Lyons on Goodhart in performance analysis (2016-04-24)](https://keithlyons.me/2016/04/24/seth-charles-and-norman-science-and-magic-in-analysing-performance/).
- The MPRA paper in the results is an economics treatment of Goodhart-type issues (not read) — [MPRA 98288](https://mpra.ub.uni-muenchen.de/98288/1/MPRA_paper_98288.pdf).

### Inferences
- Likely failure modes for a hitter told to cut chase: swing rate drops across the board (more called strikes, deeper counts, fewer hittable pitches swung at), passivity at two strikes, and walk-heavy lines that look good on process metrics with no gain in damage. Hence pair chase with in-zone swing and contact quality, and track decision-value metrics that penalize taking hittable pitches. This is inference, not cited.
- Do not tie playing time or evaluation to a single metric; use targets as coaching feedback with a pre-set review of unintended changes.

### Gaps
- No empirical baseball study of metric-gaming found. No documented organizational examples (B-tier) found.
