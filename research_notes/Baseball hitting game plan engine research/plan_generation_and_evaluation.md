# Plan generation (A) and evaluation design (F) for a hitter game-plan decision-support engine

Scope note: about 15 tool calls. Search snippets only for most items; full-page fetches failed. Blocked by egress proxy (could not open): sciencedirect.com, pmc.ncbi.nlm.nih.gov / ncbi.nlm.nih.gov, arxiv.org, nfl.com. One search hit a rate limit and was not repeated. Licenses: license terms could not be checked for most pages. I cite facts only (no text reuse). No source with a visibly restrictive license was identified; omitted for license reasons: 0 (but license status is UNVERIFIED for nearly all items; the caller should check before reuse). Several low-quality blog/aggregator hits were dropped on quality grounds, not license.

## A1. How to produce a small set of near-optimal but meaningfully different options (Pareto, diverse top-k, robust, mixed)

### Takeaway
Recommender-systems literature has mature, directly transferable methods for "top-k with diversity" (MMR, determinantal point processes) and multi-objective literature gives Pareto/robust-Pareto framing; I found NO documented sport-specific use of these for option generation. The transfer to 2-3 hitter approaches is an inference.

### Cited Findings
- MMR scores each item by a linear combination of relevance and dissimilarity to already-selected items and picks greedily; DPPs model dissimilarity set-wise and assign higher probability to diverse sets. Both use greedy selection; DPP reported to do better on diversity, MMR is cheaper per the same source summary — [Result Diversification in Search and Recommendation: A Survey (arXiv 2212.14464)](https://arxiv.org/pdf/2212.14464); [Fast Greedy MAP Inference for DPP (NeurIPS 2018)](https://papers.neurips.cc/paper/7805-fast-greedy-map-inference-for-determinantal-point-process-to-improve-recommendation-diversity.pdf)
- Quality-diversity trade-off weights can be adapted per context (recent work on adaptive trade-offs for batch recommendation) — [Adaptive Quality-Diversity Trade-offs (arXiv 2602.02024)](https://arxiv.org/pdf/2602.02024)
- The Pareto front shows trade-offs between objectives; a survey covers methods to help a decision maker pick from it (the "what lies beyond the Pareto front" problem) — [Survey on Decision-Support Methods for Multi-Objective Optimization, IJCAI 2023](https://www.ijcai.org/proceedings/2023/0755.pdf)
- Robust multi-objective work defines robust Pareto fronts under uncertainty and scalarisation-based risk concepts (relevant because the engine's values carry uncertainty) — [Scalarisation-based risk concepts for robust multi-objective optimisation (arXiv 2405.10221)](https://arxiv.org/pdf/2405.10221)
- Thompson sampling selects the action optimal for a posterior draw ("probability matching"); this yields natural randomized, diverse choices from uncertain value estimates — [Chapelle & Li, Empirical Evaluation of Thompson Sampling](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/thompson.pdf)
- Public pitch-level swing-decision value models (count, location, run value; MLB's EAGLE described as comparing swing choices to league-average expectation) exist, so the engine's base model is in line with public practice — [Pinstripe Alley summary of MLB swing-decision metric](https://www.pinstripealley.com/2023/11/9/23953323/yankees-plate-discipline-aggression-patience-judge-stanton-torres) (secondary source)

### Inferences
- Plausible design: define 2-3 axes (hunt vs cover vs react; contact vs damage; zone aggressiveness), compute each candidate approach's value distribution from the swing/take model, filter to near-optimal (within a posterior-probability band of the best), then pick a diverse subset via MMR/DPP on a behavioral-distance metric (e.g., difference in swing-zone/pitch-type targeting), not on value alone.
- Risk-sensitive framing (mean vs lower-quantile value) gives a principled reason for "contact" vs "damage" paths to both be Pareto-reasonable.
- Posterior-sampling selection also makes logged recommendations stochastic, which helps later counterfactual evaluation (see A3).

### Gaps
- No team- or league-published description of Pareto/diverse top-k option generation in sport found. Team internal practice not public.
- Could not confirm sport-specific use of DPP/MMR anywhere.

## A2. Should hitters/teams vary approach? Mixed strategies in baseball (Kovash & Levitt and critics)

### Takeaway
Kovash & Levitt (2009) argued pitchers throw too many fastballs and that play-calling shows negative serial correlation, i.e., professionals deviate from minimax; a 2024 paper reports the opposite for most players on the swing/take versus inside/outside game. Evidence is contested, so the engine should not hard-code either "randomize" or "exploit predictability".

### Cited Findings
- Kovash & Levitt, NBER WP 15347 (2009): MLB pitchers throw too many fastballs and NFL teams pass too little; deviations from minimax, with negative serial correlation in play choice; correcting could be worth up to about two wins a year to an MLB franchise — [NBER w15347](https://www.nber.org/papers/w15347); summary via search of [NBER PDF](https://www.nber.org/system/files/working_papers/w15347/w15347.pdf)
- "Professionals do play Minimax: Revisiting the Nash equilibrium in MLB" (2024, ScienceDirect, journal page not opened): models a 2x2 game (batter swing/hold, pitcher inside/outside zone); equal payoffs across actions and no serial correlation hold for the majority of players; batters swing less than theory predicts and pitchers throw inside the zone more than predicted — [ScienceDirect abstract](https://www.sciencedirect.com/science/article/abs/pii/S2773161824000168) (snippet only)
- Pitch-type predictability: next-pitch type predicted with 74.5% average accuracy over 402 pitchers (2011-2013), with wide variation across pitchers — [Pitch Sequence Complexity and Long-Term Pitcher Performance, Sports 2015](https://doi.org/10.3390/sports3010040) (snippet; as the search summary states)
- Related mixed-strategy game work on pickoffs/steals — [Pick off Throws, Stolen Bases, and Southpaws](https://ideas.repec.org/a/kap/atlecj/v43y2015i3p319-335.html)

### Inferences
- Because a hitter's approach is chosen before the pitch and the pitcher adjusts over a game (times through the order), predictability costs matter mainly for fixed zone-hunting; offering coach-selectable paths that differ by count/situation is consistent with both sides of the debate.
- The question of whether a *hitter* varying approach has value is much less studied than pitcher mixing; I found no direct hitter-side test.

### Gaps
- Could not read the 2024 paper or the original paper's full text (blocked/snippet only); critiques other than the 2024 paper were not retrieved (e.g., earlier Palacios-Huerta-style work not searched).
- No evidence on hitter-side mixing value specifically.

## A3. Learning from overrides (preference learning, learning to defer, OPE)

### Takeaway
Learning-to-defer and off-policy evaluation (OPE) give formal tools; the key practical requirement is logging propensities (randomization or known policy) for the recommended options and the coach's choice. Override data alone is confounded (coach sees context the model lacks).

### Cited Findings
- Learning to defer: Mozannar & Sontag (ICML 2020) give a consistent surrogate loss for jointly learning a classifier and a rejector that decides when to defer to a human; extensions to multiple experts have consistency guarantees — [Mozannar & Sontag 2020](https://proceedings.mlr.press/v119/mozannar20b.html); [Verma, Barrejon, Nalisnick 2023](https://proceedings.mlr.press/v206/verma23a/verma23a.pdf); [Mao, Mohri, Zhong 2023](https://proceedings.neurips.cc/paper_files/paper/2023/file/0b17d256cf1fe1cc084922a8c6b565b7-Paper-Conference.pdf); [Mozannar et al. exact algorithms](https://proceedings.mlr.press/v206/mozannar23a/mozannar23a.pdf)
- OPE in contextual bandits: estimate a target policy's value from logs of a logging policy; direct method (low variance, biased), IPS (unbiased, high variance), doubly robust combines them — Dudik, Langford, Li, ICML 2011 and Statistical Science 2014 (as cited via search summary) — [Open Bandit Dataset and Pipeline](https://arxiv.org/pdf/2008.07146) for practical tooling; [Triply Robust OPE](https://arxiv.org/pdf/1911.05811)
- Under Thompson sampling, action propensities are not directly available but a general expression can be derived, needed for IPS-type estimators — [Counterfactual Inference under Thompson Sampling (ACM 2025)](https://dl.acm.org/doi/10.1145/3705328.3748011)
- Clinical decision support: alert override rates for drug-safety alerts range 49% to 96%; about half of overrides were appropriate, varying by alert type; free-text override reasons are a feedback source — [Appropriateness of Overridden Alerts, systematic review](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7400042/); [Why do users override alerts?](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11105133/) (snippets)
- A 2026 preprint proposes treating clinician overrides as implicit preference signals — [Learning from Disagreement (arXiv 2604.28010)](https://arxiv.org/pdf/2604.28010) (title/snippet only; not vetted)

### Inferences
- With only 2-3 paths per context, a contextual-bandit framing is feasible: log context, the shown option set, the chosen path, and propensity (model-driven sampling and/or a small randomized exploration share within the "viable" set). Coach choice is then a logging policy whose propensities can be estimated.
- Overrides should be logged with structured reason codes (clinical CDS evidence shows reasons matter), and not be treated as ground-truth labels of better action.
- Since hitter outcomes per count are noisy, OPE variance will be large; use doubly-robust with the existing swing/take value model as the direct-method component.

### Gaps
- No sport-specific study of learning from coach overrides found.
- Did not retrieve Dudik et al. directly (cited via secondary search summary).

## F1. Evaluation designs for a coach-facing tool with few hitters and small effects

### Takeaway
Stepped-wedge, crossover/N-of-1 hierarchical Bayesian designs, and process metrics fit few-unit settings; Bayesian analysis with weakly informative priors performs about as well as small-sample-corrected frequentist methods with few clusters. Power for outcome metrics will be low; plan to power process metrics and report posterior estimates.

### Cited Findings
- Stepped-wedge trials are often run with few clusters; REML/ML mixed models then give inflated type I error; Kenward-Roger or Bayesian with weakly informative priors on intracluster correlations performed comparably — [Evaluating Bayesian and REML for stepped wedge CRTs with few clusters, BMC Med Res Methodol 2022](https://link.springer.com/article/10.1186/s12874-022-01550-8)
- Review of extremely small stepped-wedge CRTs recommends small-sample methods (GEE/GLMM with corrections, Bayesian, permutation tests) — [Tong et al., Clinical Trials 2025](https://journals.sagepub.com/doi/abs/10.1177/17407745241276137)
- Informative priors on time effects substantially reduced the number of clusters needed in Bayesian stepped-wedge power calculations — [Improving efficiency in stepped-wedge via Bayesian modeling with informative prior for time effects](https://pmc.ncbi.nlm.nih.gov/articles/PMC8174015)
- N-of-1 / multiple crossover: each person is own control; series of N-of-1 trials combined by Bayesian hierarchical models borrow strength across individuals and need smaller samples than parallel RCTs — [Study protocol example](https://link.springer.com/article/10.1186/s12888-023-05184-y); [Sample size calculations for n-of-1 trials (arXiv 2110.08970)](https://arxiv.org/pdf/2110.08970); [Design/analysis with sequential monitoring](https://pmc.ncbi.nlm.nih.gov/articles/PMC12917751/)
- Counterfactual/OPE-based evaluation (A3) can supply an offline comparison of "model-recommended" versus "coach-chosen" paths without a randomized arm — see A3 sources.

### Inferences
- Candidate design: stepped-wedge over staggered start dates by hitter or by team/level (even a few hitters can be units), crossover by opponent-starter series (hitter acts as own control), Bayesian hierarchical model on a primary process metric (e.g., swing-decision run value per pitch vs. plan-consistent swing share) and a secondary outcome (wOBA/run value). Carryover is a real risk for hitter learning (development goal), so washout assumptions are weak; stepped-wedge (permanent switch) may suit development better than crossover.
- Power calculations were not run; any sample-size claim would need the engine's per-pitch variance.

### Gaps
- No power numbers specific to hitter outcomes in baseball found. Matched-comparison designs were not searched in depth.

## F2. Adoption and failure modes; lessons from team uses of game-plan tools

### Takeaway
Evidence I found is general and qualitative: resistance tied to autonomy loss, buy-in dependence, and delivery constraints; NFL fourth-down tools show that format and timing (pre-game planning, constrained delivery) shape use. Little published detail on team "option-generating" game-plan tools.

### Cited Findings
- Resistance to analytics often comes from skepticism, reliance on existing models, and fear of losing decision-making autonomy; experienced coaches are a noted barrier — [The Sport Journal: Evolving Role of Technology and Analytics in Coaching](https://thesportjournal.org/article/the-evolving-role-of-technology-and-analytics-in-coaching-transforming-practices-and-enhancing-the-impact-on-the-profession/) (low-rigor source)
- Review of playing-side analytics in team sports discusses multiple directions, opportunities and challenges — [Playing-Side Analytics in Team Sports (PMC8287128)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8287128/) (snippet only)
- NCAA coaching staff focus groups (5 groups, 17 staff): monitoring practices depended on coach buy-in and staff alignment; many had won without such technology — via search summary of [Frontiers in Sports and Active Living 2025](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1644099/full) (snippet; exact article attribution not confirmed)
- NFL Next Gen Stats Decision Guide: fourth-down and two-point advice built on ML models; league rules prohibit technology in the coach's booth so advice is delivered as printable documents, often a single card — [NFL.com announcement](https://www.nfl.com/news/introducing-the-next-gen-stats-decision-guide-a-new-analytics-tool-for-fourth-do) (not opened; via search snippet)
- Statistical critique: fourth-down model recommendations carry uncertainty that is often under-communicated — [Analytics, have some humility (arXiv 2311.03490)](https://arxiv.org/pdf/2311.03490) (title/snippet only)

### Inferences
- Lessons plausibly transferable: show uncertainty, keep the output to a glanceable card (2-3 paths), preserve coach autonomy (override is a feature), plan decisions before the game, secure staff buy-in early.

### Gaps
- No documented case of a team's option-generating "game plan" tool with measured outcomes found; MLB team practice is mostly non-public. Baseball Prospectus/FanGraphs library pages could not be reliably searched or opened.
