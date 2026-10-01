# Open-source implementations and academic work for a baseball hitter-approach decision engine

Scope notes. Research date 2026-10-01. Licenses were read from GitHub repo pages (via WebFetch summaries, not raw LICENSE files, except where stated). Could not open: arxiv.org, sloansportsconference.com, adamsalorio.substack.com (all blocked by the egress proxy); papers below are known from search-result snippets only. Omitted for license reasons (no license stated, so all rights reserved): 5 repositories that were checked. A further batch of repositories surfaced only in search results was not license-checked and is not listed. One repo surfaced in search (a public Stuff+/Pitching+ template) returned 404 on fetch and could not be verified, so it is not listed.

## 1. Open-source Stuff / pitch-quality models

### Takeaway
Only one permissively licensed public pitch-quality repo was verified (an MIT expected-whiff stuff model). Most public Stuff+ replications either state no license or could not be verified. Treat all as read-only references and re-implement from the methods.

### Cited Findings
- jakeyoung1/pitchquality, license MIT. Logistic regression on 711,897 pitches (2025 Statcast) predicting P(whiff | swing). Features: velocity, spin rate, spin axis, vertical/horizontal approach angle (VAA/HAA), optionally location and count. Adding VAA/HAA raised AUC from .652 to .767. Reported held-out (2026 season) AUC .7674, log loss .4465, Brier .14187; calibration tight through 8th decile, top decile predicts .767 vs observed .720; stuff model beats raw outcomes below about 125 swings. Code fetches data; no pretrained weights distributed (outputs in /reports). Self-reported numbers, single author, not independently verified. Verdict: READ, and may copy code (MIT) after review; do not depend on it as a package. — [repo](https://github.com/jakeyoung1/pitchquality)
- Common public Stuff+ recipe (from the unlicensed repos' READMEs, so methodology only): gradient-boosted regressors (XGBoost/LightGBM) on per-pitch run value (from RE24 run expectancy), physics features (velocity, induced vertical and horizontal break, spin, release point, extension), pitcher-relative features (movement and velocity differential vs the pitcher's own fastball), excluding location/count/batter, then z-scaled to 100 per pitch type and season. Reported validation in such repos: year-over-year pitcher r about 0.74 (one repo) and 0.49-0.62 (another); whiff-model AUC about 0.76. Methods are generic and re-implementable. Methodology facts only; the source repos are among the omitted count.
- Chase Coppersmith's public Pitching+/Stuff+ write-up exists as a Medium post (methodology readable, license of its repo not verified). — [Medium](https://medium.com/@coppersmithchase/a-new-public-facing-mlb-pitch-quality-model-with-full-2023-pitch-by-pitch-data-b8a1caa39783)
- Adam Salorio's aStuff+ and aSwing+ (Substack/Medium) are methodology posts; Substack was blocked so details were not read. — [Medium](https://medium.com/@adamsalorio/introducing-my-stuff-model-2840f196cf01)

### Inferences
- Targets are a design choice: run value (noisy, stable only moderately) vs whiff/contact probability (AUC about 0.76-0.77 in two independent repos). Approach angles (VAA/HAA) are a high-value feature.
- No public repo ships trained weights with a permissive license; plan to train in-house.

### Gaps
- No verified permissive Stuff+ repo with weights. No raw-LICENSE-file read for jakeyoung1 (relied on page summary; confirm the LICENSE file before copying code).

## 2. Open-source swing-decision, swing-quality (bat tracking) and hitter models

### Takeaway
No permissively licensed swing-decision or bat-tracking repo was verified. The usable material is academic: published methods to re-implement.

### Cited Findings
- Powers and Yurko, "Swinging, Fast and Slow: Interpreting variation in baseball swing tracking metrics" (arXiv 2507.01238, July 2025; later in The American Statistician, 2026). Bayesian hierarchical skew-normal model of batter intention given count and pitch location (random batter slopes), then instrumental-variables regression for causal effects of bat speed and swing length on contact and power. Finding: lowering bat speed with more strikes cuts strikeouts but the lost power roughly offsets it for the average batter. Directly relevant to swing-quality and per-count approach. — [arXiv](https://www.arxiv.org/abs/2507.01238), [AmStat](https://doi.org/10.1080/00031305.2026.2633338), [Pith summary](https://pith.science/paper/2507.01238)
- "Evaluating plate discipline in Major League Baseball with Bayesian Additive Regression Trees" (arXiv 2305.05752, 2023). Three-step approach: BART models for P(contact), P(called strike), and expected runs as functions of location, players/umpire, and game state; yields optimal swing decision per pitch and decision-quality measures. Closest published analogue to a per-count swing/take value engine. — [arXiv](https://arxiv.org/pdf/2305.05752)
- "Introducing Discipline Score Based on League Overall Swinging Probability" (arXiv 2511.19672, late 2025). Plate-discipline metric from league swing probability; not read in detail. — [arXiv](https://arxiv.org/pdf/2511.19672)
- Bayesball: Bayesian Integration in Professional Baseball Batters (bioRxiv 2022). Batters weight prior vs likelihood by pitch uncertainty; supports modelling pitch-type uncertainty in decisions. — [bioRxiv](https://www.biorxiv.org/content/10.1101/2022.10.12.511934v2.full)
- SSAC-listed work: hitters' two-strike swing adjustments add 0 to .020 expected wOBA on two-strike swings (snippet only, authors/year not confirmed). — [search result](https://www.sloansportsconference.com/research-papers/a-game-theoretical-approach-to-optimal-pitch-sequencing) (listing page; not opened)
- Repos in this area that were checked (swing probability, swing/take counterfactual value with Q_swing/Q_take, bat-speed analysis) stated no license and are omitted (counted in the omitted total).
- Counterfactual swing/take framing (value of swing vs take as change in run expectancy, with decomposed whiff/foul/in-play outcomes) appears in the omitted repos' descriptions and is a generic, re-implementable idea consistent with the BART paper above.

### Inferences
- Combine the BART plate-discipline framework (decision value) with the Powers-Yurko hierarchical batter-by-count structure (swing-quality, uncertainty) as the primary design references.

### Gaps
- Could not read the full text of any arXiv paper (blocked); details come from search snippets. No code links confirmed for these papers.

## 3. Pitch sequencing, next-pitch and pitch-type usage

### Takeaway
One MIT-licensed next-pitch package is available (pitchpredict); the rest of the evidence is academic. Sequencing signal is real but small and unstable year to year.

### Cited Findings
- baseball-analytica/pitchpredict, license MIT (copyright Addison Kline 2024, LICENSE file read). Two algorithms: weighted nearest-neighbour "similarity" and an xLSTM sequence model with player IDs and game state; trained on Statcast via pybaseball (2015 onward); xLSTM weights download on first use; Python 3.12+, API/REST/CLI. Verdict: DEPEND OPTIONALLY / READ. Use as a benchmark baseline rather than a core dependency; check the weights' own terms and Statcast data terms before any production use. — [repo](https://github.com/baseball-analytica/pitchpredict), [LICENSE](https://github.com/baseball-analytica/pitchpredict/blob/main/LICENSE), [PyPI](https://pypi.org/project/pitchpredict/)
- "Decoding MLB Pitch Sequencing Strategies via Directed Graph Embeddings" (SSAC; about 3.5M pitches 2015-2019): graph embeddings find "setup" and "knockout" pitch clusters. — [SSAC](https://www.sloansportsconference.com/research-papers/decoding-mlb-pitch-sequencing-strategies-via-directed-graph-embeddings) (listing seen in search; page not opened)
- "A Game Theoretical Approach to Optimal Pitch Sequencing" (BYU thesis / SSAC): zero-sum game, Stackelberg and "decision point" equilibria. — [BYU](https://scholarsarchive.byu.edu/cgi/viewcontent.cgi?article=10919&context=etd)
- "Transformer-Based Baseball Modeling for Pitch Outcome Prediction and Strategy Optimization" (SSAC listing; not opened). — [SSAC](https://www.sloansportsconference.com/research-papers/transformer-based-baseball-modeling-for-pitch-outcome-prediction-and-strategy-optimization)
- "Strategic Pitch Location: The Role of Two-Pitch Sequences in Pitching Success" (SABR Journal). — [SABR](https://sabr.org/journal/article/strategic-pitch-location-the-role-of-two-pitch-sequences-in-pitching-success/)
- Evidence the previous pitch adds little: one unlicensed repo (omitted; SSAC 2027 submission, self-reported) found previous-pitch information of about 12.8 millibits vs 102 for pitcher hand and 58 for count, split-half reliability 0.75 but year-to-year r 0.22, using a hierarchical Dirichlet model with empirical Bayes. Treat as an unreviewed claim; the method (hierarchical Dirichlet shrinkage on pitch-type usage by count) is standard and re-implementable.
- Many other small next-pitch repos exist (LSTM/RF/HMM benchmarks on synthetic or PITCHf/x data); not license-checked.

### Inferences
- Pitch-mix by count should use hierarchical shrinkage toward pitcher and league priors rather than deep sequence models; deep models can be a benchmark only.

### Gaps
- No peer-reviewed validation numbers confirmed for the SSAC sequencing papers (pages blocked).

## 4. Data access, uncertainty/hierarchical modelling, calibration and evaluation libraries

### Takeaway
The core stack is permissively licensed and safe to depend on: pybaseball, PyMC, MAPIE, netcal (plus ArviZ, scikit-learn, Stan by general knowledge, not verified this session).

### Cited Findings
- pybaseball (jldbc/pybaseball), MIT, about 1.7k stars; pulls Statcast, FanGraphs, Baseball Reference. Statcast seasons have 700,000+ pitches and are subject to revision. Verdict: DEPEND for exploration and backfill. — [repo](https://github.com/jldbc/pybaseball), [PyPI](https://pypi.org/project/pybaseball/2.1.1/)
- PyMC, Apache-2.0, about 9.8k stars, NumFOCUS. Verdict: DEPEND for hierarchical Bayesian shrinkage and per-hitter, per-count posteriors. — [repo](https://github.com/pymc-devs/pymc)
- pymc-examples notebooks (hierarchical models, gallery); license not read on the page summary (the main PyMC repo is Apache-2.0; confirm the examples repo LICENSE before copying notebooks). — [repo](https://github.com/pymc-devs/pymc-examples)
- MAPIE, BSD-3-Clause; conformal prediction and uncertainty quantification. Verdict: DEPEND. — [repo](https://github.com/scikit-learn-contrib/MAPIE)
- netcal (EFS-OpenSource/calibration-framework), Apache-2.0; calibration methods (classification, regression, Bayesian). Verdict: DEPEND. — [repo](https://github.com/EFS-OpenSource/calibration-framework)
- Hierarchical Bayesian modelling of hitting performance (Jensen, Wharton, 2009) is an older reference for batter-level shrinkage. — [PDF](https://faculty.wharton.upenn.edu/wp-content/uploads/2009/11/Shanejensen.traj09.pdf)
- Learning, Visualizing, and Exploiting a Model for the Intrinsic Value of a Batted Ball (arXiv 1603.00050, 2016): batted-ball value model, precursor to swing-quality / xwOBA-style models. — [arXiv](https://arxiv.org/pdf/1603.00050)
- Big Ideas in Sports Analytics and Statistical Tools for their Investigation (arXiv 2301.04001, 2023): survey. — [arXiv](https://arxiv.org/pdf/2301.04001)
- PySport open-source index lists other sports-analytics tools. — [PySport](https://opensource.pysport.org/)

### Inferences
- pybaseball code is MIT, but the underlying data come from MLB/Savant/FanGraphs/Baseball Reference, whose terms of use for a for-profit organization are separate and were not checked; a professional organization will likely have its own licensed data feed. Flag for legal review.

### Gaps
- Stan/CmdStanPy, ArviZ, scikit-learn license pages not opened (generally BSD/Apache, to be confirmed). PyMC release version/date not found.

## 5. Key papers summary table (year, takeaway)

### Takeaway
Most directly relevant: BART plate discipline (2023), Powers-Yurko bat tracking (2025), SSAC sequencing papers.

### Cited Findings
- 2023, BART plate discipline: per-pitch optimal swing decisions from contact, strike-call and run models — [arXiv 2305.05752](https://arxiv.org/pdf/2305.05752)
- 2025, Powers & Yurko bat tracking: hierarchical intention model plus IV for causal effect of bat speed — [arXiv 2507.01238](https://www.arxiv.org/abs/2507.01238)
- 2025, Discipline Score from league swing probability — [arXiv 2511.19672](https://arxiv.org/pdf/2511.19672)
- 2022, Bayesball: batters combine prior and observation by uncertainty — [bioRxiv](https://www.biorxiv.org/content/10.1101/2022.10.12.511934v2.full)
- 2016, Intrinsic value of a batted ball — [arXiv 1603.00050](https://arxiv.org/pdf/1603.00050)
- 2009, Hierarchical Bayesian hitting trajectories — [Wharton PDF](https://faculty.wharton.upenn.edu/wp-content/uploads/2009/11/Shanejensen.traj09.pdf)
- 2018, Modeling the probability of a batter/pitcher matchup event, Bayesian — [PLOS ONE](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0204874)
- SSAC pitch sequencing (graph embeddings; game theory; transformers) — see section 3.
- Decision-support-in-sport and Stuff-model academic papers: not found (see Gaps).

### Gaps
- No peer-reviewed Stuff+ methodology paper or decision-support-in-sport paper located; search effort was limited and arXiv/SSAC were blocked. 2024-2026 JQAS items were not surveyed.

## Verdicts

- DEPEND (permissive, verified on repo page): pybaseball (MIT), PyMC (Apache-2.0), MAPIE (BSD-3), netcal (Apache-2.0).
- READ, may copy with review: jakeyoung1/pitchquality (MIT); pitchpredict (MIT; baseline only, check weights and data terms).
- READ papers only (re-implement): BART plate discipline, Powers-Yurko, Bayesball, SSAC sequencing papers.
- AVOID: any repo with no license (all rights reserved). Count omitted for license reasons: 5.
