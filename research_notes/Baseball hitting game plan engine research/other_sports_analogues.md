# Other-sport analogues for opponent-specific tactical option generation and decision-vs-execution separation

Scope note. Research was done with WebSearch snippets plus WebFetch. WebFetch was blocked (egress) for arxiv.org, springer.com, sagepub.com, nfl4th.com, hudl.com, johnwooders.com and cricviz.com, so most claims below rest on search-result summaries, not full-text reads. Treat every finding as "snippet-level" unless it says otherwise. Licenses could not be verified on any page. As a conservative approximation of the license rule, 14 sources (arXiv-hosted preprints, Wikipedia, ResearchGate mirrors, Substack and aggregator blogs) were omitted for license reasons; the sources kept are league, publisher, or author-hosted pages whose license the caller should still screen.

## NFL: expected points, win probability, fourth-down models, and coach adherence

### Takeaway
The NFL pattern is "enumerate the discrete options, estimate outcome probabilities, convert each outcome to a common value (EP or win probability), rank by expected value." The documented gap between model and coach is large and persistent, and it is explained mainly by incentives (job risk), not by model disagreement. Adherence rose in the 2020s.

### Cited Findings
- Burke (2009) compared Expected Points of punt, field goal and go-for-it at every field position and distance, using 2000-2008 gamebook data; 4th-down conversion rates were supplemented with 3rd-down rates because 4th-down attempts are rare. In his worked example (4th-and-3 at the opponent's 37, tied, early 2nd quarter) the model favored going and coaches punted 100% of the time. — [Advanced Football Analytics, 4th Down Study](http://www.advancedfootballanalytics.com/2009/09/4th-down-study-part-3.html)
- Romer's EP-based analysis found that of 1,575 fourth downs where kicking was better, teams went for it 7 times; of 1,100 where going was better, teams went for it only 108 times (under 10%). He attributes this to coaches maximizing job security, since a failed conventional kick is blamed on players while a failed gamble is blamed on the coach. The same source notes no known evidence that decisions changed after Romer (2006). — [Romer, "Do Firms Maximize?"](https://eml.berkeley.edu/~dromer/papers/PAPER_NFL_JULY05_FORWEB_CORRECTED.pdf); summary of the counts via [Ruscio/TCNJ fourth-down paper](https://ruscio.pages.tcnj.edu/files/2021/01/Fourth-Down-Decisions.pdf)
- League tool: the Next Gen Stats Decision Guide combines win probability under each outcome (convert, fail, field goal, punt) with separate conversion-probability models (4th down vs 2-point) and field goal probability, and ranks the options by win probability. It runs live on SageMaker ML models. — [NFL.com, Introducing the Decision Guide](https://www.nfl.com/news/introducing-the-next-gen-stats-decision-guide-a-new-analytics-tool-for-fourth-do); [AWS ML blog](https://aws.amazon.com/blogs/machine-learning/next-gen-stats-decision-guide-predicting-fourth-down-conversion)
- Adherence data (secondary, journalistic; treat as indicative): in 2023, 4th-and-1 was converted 71.3% league-wide but attempted only 48.6% of the time; a 4th-and-1 go at midfield is cited as worth about +3.2 win-probability points on average; Matt LaFleur followed the recommended decision about 60% of the time in 2020-23 and 72.7% in 2025. — [Study summaries via search: Cheesehead TV, NFL Draft Diamonds, StudyFinds](https://nfldraftdiamonds.com/2025/04/fourth-down/). Numbers not verified against primary data.
- Critical caveat on model confidence: Lopez's early commentary on the public 4th-down bot questioned treating model outputs as precise. — [Lopez, "My quick thoughts on the 4th down bot"](https://statsbylopez.com/2013/12/04/my-quick-thoughts-on-the-4th-down-bot/)

### Inferences
- Transferable: present each option as expected value with its outcome tree (success, failure, partial), and show the key probability inputs so the coach can disagree with a specific input, not the whole answer.
- Transferable: the adherence gap is incentive-driven, so logging coach overrides plus the reason code is the right design; do not read overrides as errors. Hitter-development framing (coach is not judged on a single result) reduces the Romer-type job-risk bias.
- Does not transfer directly: NFL has a single decision-maker and a few discrete options at a high-leverage moment; baseball hitting approach per count is a high-frequency, low-leverage repeated decision with smaller per-decision gains, so adherence should be tracked in aggregate, not per decision.
- Rare-event data problem (4th-down sparsity borrowed from 3rd-down) parallels sparse hitter-vs-starter-by-count samples; borrowing strength across similar states is a precedent.

### Gaps
- Could not open Yam and Lopez (2019, JSA, "What was lost?") for the causal estimate of win probability left on the table; only the title was seen.
- No peer-reviewed measurement found of how coach-model agreement affects outcomes after adoption (as opposed to go-rate trends).
- Could not open nfl4th.com research page (blocked).

## NBA: shot quality vs shot probability (decision vs execution), matchup tools

### Takeaway
Second Spectrum's qSQ is the clearest published example of separating decision quality from execution: shot quality is what an average shooter would make given location and defender context, and the shooter's actual result minus that is shooter impact. 

### Cited Findings
- qSQ ("quantified shot quality") is the probability a shot goes in given player and defender positions and movement, independent of the shooter's ability, on the same scale as eFG%. qSP adds shooter ability. qSI compares actual output to the qSQ expectation, i.e. execution above or below what shot difficulty implies. — [ESPN fantasy analytics glossary](https://www.espn.co.uk/fantasy/basketball/story/_/id/20712582/fantasy-basketball-analytics-glossary); [Second Spectrum on X](https://x.com/secondspectrum/status/973305041435029504); [Nylon Calculus](https://fansided.com/2018/06/28/second-spectrum-redesigning-nba/)
- Shot-selection logic: expected points per shot = make probability x shot value; rim and three-point shots have the highest value, and Houston's "Moreyball" pruned mid-range shots. — [The Ringer](https://www.theringer.com/2021/12/07/nba/nba-shot-quality-midrange-kevin-durant-brooklyn-nets)
- The NBA moved from SportVU (2013-14) to Second Spectrum tracking as the data source. — [Nylon Calculus](https://fansided.com/2018/06/28/second-spectrum-redesigning-nba/)

### Inferences
- Core transfer: score every swing/take option with a context-conditional expected value for an average hitter (the decision), and separately compare the hitter's realized outcome to that expectation (the execution). Logging both lets the tool credit a good decision with a bad result.
- Lesson from "Moreyball": a league-average value surface can push every player toward the same option; hitter-development tool should weight the individual hitter's own distribution, with the average as a shrinkage prior.

### Gaps
- No published validation of qSQ (calibration or out-of-sample) found; vendor methods are proprietary.
- Found nothing documented on how NBA coaches consume shot-selection recommendations or adherence rates. Matchup-tool documentation not found.

## Soccer: xT, VAEP, possession value; opponent plans and set pieces

### Takeaway
Possession-value models value each action by the change in the probability of scoring or conceding, which is a state-value approach analogous to count-state run expectancy. VAEP is peer-reviewed; xT is a simpler grid-based Markov model. Published evidence on opponent-specific plans and set pieces was thin.

### Cited Findings
- VAEP values a game state as P(scores) minus P(concedes) over a short horizon and rates an action by the change it causes; it emphasizes role- and context-specific modeling. Paper: Decroos, Bransen, Van Haaren, Davis, KDD 2019. — [VAEP paper](https://janvanhaaren.be/assets/papers/kdd-2019-vaep.pdf); [IJCAI 2020 overview](https://www.ijcai.org/proceedings/2020/0648.pdf)
- xT (Karun Singh, 2018) lays a value surface over pitch zones; an action's value is the xT change from its start zone to its end zone. — [Hudl explainer via search](https://www.hudl.com/blog/possession-value-models-explained)
- A critical comparison of xT and VAEP exists (Decroos). — [xT vs VAEP report](https://tomdecroos.github.io/reports/xt_vs_vaep.pdf)
- Extensions: Dynamic Expected Threat (DxT) addresses xT's lack of realism. — [MDPI Applied Sciences 2025](https://www.mdpi.com/2076-3417/15/8/4151)

### Inferences
- Transfer: the "value of a state, credit by change in state value" structure maps directly to count states (0-0, 1-2 etc.) and gives a consistent currency for comparing swing vs take within a count.
- Limit: soccer action-valuation is retrospective player credit. I found no documented option-ranking against a named opponent in these sources, so soccer offers evaluation method more than option-generation method.

### Gaps
- Could not find sourced documentation of how clubs use xT/VAEP for opponent-specific plans or set-piece design; claims in vendor marketing not verified.
- Published club-level adoption or out-of-sample validation of decision quality not found.

## Tennis: serve and return strategy, mixed-strategy and Bayesian hierarchical models

### Takeaway
Tennis supplies the best-developed theory for opponent-specific choice under uncertainty: minimax/mixed strategy tests on serve direction and Bayesian hierarchical models of intended serve direction using Hawk-Eye data. Evidence suggests top players are near, but not at, equilibrium, which affects how strongly to recommend a single approach.

### Cited Findings
- Using nearly half a million serves from over 3,000 matches, researchers tested the minimax hypothesis for serve direction (Walker-Wooders, and Gauriot-Page work on the same data). — [Gauriot, Page, Wooders, "Nash at Wimbledon"](https://www.johnwooders.com/papers/NashAtWimbledon.pdf) (search snippet only)
- A Bayesian hierarchical model of intended serve direction using Roland Garros Hawk-Eye data found left- and right-handed servers differ; analysis provides some evidence top players use mixed strategies and that fatigue plays a role; higher-ranked men show less serial correlation in direction. — [Swartz et al., SFU draft](https://www.sfu.ca/~tswartz/papers/tennis1.pdf); [published in Annals of Operations Research](https://link.springer.com/article/10.1007/s10479-021-04481-7)
- Mixed-strategy equilibrium work in tennis serves. — [Wiles, Duke](https://sites.duke.edu/djepapers/files/2016/10/Wiles.pdf)

### Inferences
- Transfer: hierarchical shrinkage (player within tour/handedness group) is the standard answer to small samples; matches the per-hitter, per-count sparsity.
- Transfer: if a pitcher's pitch selection by count is near-mixed, a hitter's best approach is a distribution over targets, not a fixed guess; the tool should surface the predictability of the pitcher by count as an input, with uncertainty.
- Limit: tennis serve-return is nearly simultaneous with clear zones; baseball hitters guess a pitch type/zone before the pitcher's choice, so the equilibrium framing applies but the information structure differs.

### Gaps
- Could not read full texts (blocked). No sourced details on point-importance-by-score weighting or scouting-report formats used by tour players or coaches.
- A 2026 arXiv paper on stated vs realized vs optimal aiming in collegiate tennis serves appeared in search but could not be opened and was omitted for license reasons.

## Cricket: bowler-batter matchups, pitch maps, T20 analytics

### Takeaway
Cricket's ball-tracking expected-runs/expected-wickets models score each delivery by line, length and context, which is the closest published analogue to "target zone plus sequence with expected outcome per option." Details were only partially accessible.

### Cited Findings
- CricViz xR and xW models use ball-tracking data and the outcomes of similar historical balls to measure the threat and control of each delivery. — [CricViz](https://cricviz.com/cricviz-develops-new-batting-and-bowling-metrics-for-the-world-cup/) (search snippet only)

### Inferences
- Transfer: nearest-neighbor outcome estimation on tracked locations is a simple, explainable way to give expected outcome by zone; pairing with pitcher pitch-location maps by count gives a hitter-side analogue of a bowler plan.

### Gaps
- Could not verify wagon-wheel/pitch-map plan formats, franchise analytics workflows, validation, or coach consumption. A 2026 context-adjusted T20 expected-runs paper with line/length multipliers was found but omitted for license reasons.

## Hockey, golf, esports, others

### Takeaway
Not researched in depth. No sourced findings.

### Cited Findings
- None retained.

### Gaps
- Searches for these were not run within the tool budget; no claim is made.
