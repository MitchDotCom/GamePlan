# Other-sport analogs for capturing intent vs execution vs outcome (for hitting approach per count vs a specific starter)

Method caveat: WebFetch was blocked by the egress proxy for arxiv.org, pff.com, springer, kuleuven, tennisabstract and aiimpacts. Every finding below rests on WebSearch result snippets only, not on full-text reads. Dates are given where the snippet showed them, otherwise "date not confirmed". Evidence tiers: A peer-reviewed or primary data, B named practitioner account, C vendor or marketing, D opinion. Verdict lines are my inference, not sourced claims. Not found anywhere: a public pre-game plan log that a coach writes and is graded afterward (see last section).

## American football: play call vs assignment grading, charting, fourth-down tools

### Takeaway
Football has the closest published analog to "intent vs execution": PFF grades every player on every play against expectation for his assignment, separate from the result. Fourth-down tools (bots, decision guides) grade the call itself against a win-probability model, and they moved coach behavior slowly over about 15 years. Unit of intent is the play call and the player's assignment on it.

### Cited Findings
- PFF grades each event on a -2 to +2 scale in 0.5 steps, where 0 is the expected grade; each player gets a grade on every play "based on their assignment and execution" (tier C, vendor) — [PFF](https://www.pff.com/news/nfl-quarterback-play-level-data); [Gradient/PFF FC grades](https://www.gradientsports.com/how-we-grade)
- PFF measures "performance relative to expectation", and states consistent repeated execution of the assignment matters more than highlight plays (tier C) — same sources
- PFF quality control: strict grading guide, under 10% of data collectors become graders, 5-7 graders per facet for natural auditing, flagging of uncertain grades to seniors (tier C; self-reported, no independent reliability figure seen) — [PFF FC grades explained](https://www.blog.fc.pff.com/blog/pff-fc-grades-explained)
- Romer's fourth-down analysis (expected-points framework): of 1,068 fourth downs where the numbers favored going for it, teams went only 109 times (tier A, as relayed by a secondary page; original paper not read) — [Fourth Down Decisions PDF](https://ruscio.pages.tcnj.edu/files/2021/01/Fourth-Down-Decisions.pdf); [Scientific American summary](https://www.scientificamerican.com/article/fact-or-fiction-nfl-teams-4th-downs)
- League go-for-it rate sat near 10% from 2006 to 2017 despite a 2014 NYT real-time bot, then rose; fourth-and-1 attempts reached 57% in 2018 vs 44% in 2017 (tier D/B, journalism summarized by search; unverified) — [Scientific American](https://www.scientificamerican.com/article/fact-or-fiction-nfl-teams-4th-downs)
- Ben Baldwin's 4th-down bot tweets a recommended action per decision from score, time, success rate and field position; NFL Next Gen Stats has a "Decision Guide" that grades each coach decision (tier B/C) — [NFL.com Decision Guide](https://www.nfl.com/news/next-gen-stats-decision-guide-fourth-down-superlatives-at-midpoint-of-2021-nfl-s); [Pride of Detroit](https://www.prideofdetroit.com/2021/12/29/22858941/dan-campbell-leads-nfl-analytically-correct-fourth-down-decisioons)
- Adoption was driven by a specific coach: Dan Campbell's Lions posted the three highest single-season go-for-it rates (29.5%, 29.6%, 30.5%, 2021-2023), while predecessor Matt Patricia followed strong go-for-it recommendations on 38% of opportunities (tier B/D) — [Pride of Detroit](https://www.prideofdetroit.com/2021/12/29/22858941/dan-campbell-leads-nfl-analytically-correct-fourth-down-decisioons); [NFL.com](https://nfl.com/news/week-1-s-biggest-fourth-down-decisions-lions-get-bold-cowboys-play-it-safe)
- Disconfirming / failure: a BYU study found coaches still more conservative than the numbers suggest (tier A/B, snippet only) — [BYU News](https://news.byu.edu/intellect/risk-it-or-kick-it-byu-research-analyzes-nfl-coaches-risk-tolerance-on-fourth-down). Kingsbury kicked field goals on four fourth-and-manageable situations inside the 5 early in a season and drew analytics criticism (tier D) — [Cardinals.com](https://www.azcardinals.com/news/kliff-kingsbury-s-fourth-down-shift). Belichick's failed 2009 fourth-and-2 became the canonical "resulting" example, where a defensible call was judged by outcome (tier D) — [Stuyspec](https://stuyspec.com/article/where-statistics-meet-football-the-fourth-down-dilemma)

### Inferences
- The PFF design (grade vs expectation for assignment, zero = did the job, multiple graders audit) is the closest template for grading hitter execution of a stated approach separately from batted-ball result. Its weakness: grades are human judgments from film with no public inter-rater numbers.
- Fourth-down tools grade the decision against a model, not against the coach's stated reason, so they grade "was the call right" not "was the call executed". Both are needed for the hitting case.
- Behavior change needed a decision-maker who personally bought in, not better numbers alone. Expect the same with hitting coaches.
- Verdict for hitting approach per count vs a given starter: HIGH transferability of the assignment-plus-expectation grading idea; MEDIUM for the decision-bot idea (needs a count-leverage model of swing/take value).

### Gaps
- PFF full methodology and any inter-grader reliability data not read (fetch blocked).
- No public example of a football coach logging a pre-game call plan that was later graded; call-sheet schema not found.

## Basketball: play-type tagging, EPV, shot quality

### Takeaway
Tracking-based systems auto-tag play types and sub-actions (e.g., pick-and-roll ball handler take/reject, screener roll/pop, defender show/switch/blitz) and let coaches query outcomes by tag. EPV values every moment and decision of a possession, which is a decision-vs-result separation, but it models what players did, not what the coach drew up.

### Cited Findings
- Second Spectrum uses cameras to capture each player's actions and automatically identify play types; the NBA has used it since 2017-18; coaches query in their own vocabulary and get video in seconds (tier C/B, news) — [Boston Globe, 2015](https://www.bostonglobe.com/sports/2015/08/22/analytics-emerging-coaching-tool/s48TbOisEr35kjyLeAlzFP/story.html); [Sports Business Daily, 2015-08-25](https://www.sportsbusinessdaily.com/Daily/Issues/2015/08/25/Leagues-and-Governing-Bodies/Second-Spectrum.aspx); [BestPractice.ai case study](https://www.bestpractice.ai/ai-case-study-best-practice/the_nba_optimises_team_and_players_strategy_in_games_with_machine_learning_and_vision_enabled_analytics_)
- Pick-and-roll tagging records take/reject, roll/pop and defensive coverage, then reports shooting percentage per combination (tier C) — same Boston Globe/BestPractice sources
- EPV (Cervone, D'Amour, Bornn, Goldsberry, "POINTWISE", MIT Sloan 2014): assigns an expected points value to each moment of a possession from SportVU tracking (about 800 million locations, 14 arenas), so every pass, dribble or shot decision can be valued; addresses that most metrics only see end-of-possession events (tier A; also JASA version) — [arXiv 1408.0777](https://arxiv.org/abs/1408.0777); [Harvard Gazette, 2014-03](https://news.harvard.edu/gazette/story/2014/03/bringing-order-to-the-court/)
- Academic work on identifying basketball plays from tracking (play registration/warping) shows play-type labels are inferred after the fact from motion, not logged by coaches (tier A, snippet only) — [Squared2020 on play registration, 2019-09-09](https://squared2020.com/2019/09/09/warping-play-registration/); [Aalborg PDF](https://vbn.aau.dk/ws/files/267528400/IntentifyingBasketballPlaysDAPSdef.pdf)
- Disconfirming: I found no public evidence that EPV was adopted as a coach-facing grading tool; the commercial products surfaced were tagging and query tools (absence of evidence from search only).

### Inferences
- Intent unit is the set/play type (tagged by software or by Synergy-style human taggers), and the success metric is points per possession by tag. The tag is inferred from motion, so "intended play" and "executed play" are not separated.
- EPV's decision-value-at-each-moment is the closest formal analog to scoring a swing/take decision per pitch by expected run value, using the count as state.
- Verdict: MEDIUM-HIGH for the "state-value change per decision" idea (count-state run expectancy already exists in baseball); LOW for automatic play-type tagging as a measure of intent.

### Gaps
- Second Spectrum technical documentation, tag accuracy rates and coach-reaction accounts beyond marketing not found.
- Shot-quality models (qSQ etc.) not researched in this pass.

## Soccer: possession value, pitch control, set pieces

### Takeaway
VAEP and xT value actions by change in scoring/conceding probability, which gives a result-independent value of the action chosen. Pitch control adds off-ball context. Set-piece "playbooks" exist but no public schema of planned vs executed routines was found.

### Cited Findings
- VAEP (Decroos et al., KDD 2019; arXiv 1802.07127): values each action by change in probability of scoring and conceding in the next few actions, using two probability models and the action's context (tier A) — [arXiv 1802.07127](https://arxiv.org/pdf/1802.07127); [KU Leuven DTAI VAEP page](https://dtai.cs.kuleuven.be/sports/vaep)
- Expected Threat (Karun Singh): assigns a scoring probability to each pitch zone and values passes/carries by change in zone value (tier B practitioner origin; later academic variants) — [xT explainer](https://databallpy.readthedocs.io/en/latest/features/xt_models.html); [Soccerment](https://blog.soccerment.com/?p=17932)
- KU Leuven published a critical comparison of xT and VAEP (tier A/B, content not read) — [DTAI blog](https://dtai.cs.kuleuven.be/sports/blog/valuing-on-the-ball-actions-in-soccer-a-critical-comparison-of-xt-and-vaep)
- Spearman, "Beyond Expected Goals" (MIT Sloan 2018): pitch control and off-ball scoring opportunity (OBSO), decomposed into probability of the next on-ball event at a location, probability of control, and probability of scoring there; Spearman is Liverpool's lead data scientist (tier A paper plus tier B practitioner talk) — [Training Ground Guru interview](https://archive.trainingground.guru/articles/william-spearman-how-liverpool-create-pitch-control); [Liverpool FC profile](https://www.liverpoolfc.com/news/first-team/450917-the-weird-journey-of-william-spearman-liverpool-s-lead-data-scientist)
- Set pieces: reporting says clubs copy each other's corner routines (Liverpool borrowing Arsenal's) and employ set-piece coaches; evidence is news/low-quality aggregator pages (tier D) — [Sky Sports](https://www.skysports.com/football/news/12040/13514315/liverpool-have-transformed-their-set-piece-record-by-copying-key-trend-sweeping-the-premier-league)
- Disconfirming: the KU Leuven group posted critiques of other possession-value metrics (e.g., American Soccer Analysis g+), indicating these models are contested on validity (tier B) — [DTAI blog on g+](https://dtai.cs.kuleuven.be/sports/blog/our-thoughts-on-american-soccer-analysis'-g+-metric)

### Inferences
- Unit of intent in these models is nil: they value what happened, never what the manager asked. They are decision-value-vs-outcome tools, not plan-adherence tools.
- Verdict: MEDIUM. Valuing each action by change in state probability transfers directly (count-state to count-state), but there is no intent layer to borrow. Pitch control has no hitting analog except pitch-location/zone value.

### Gaps
- Tactical-instruction logging (pressing triggers, build-up shape) and any graded set-piece log schema: not found.

## Tennis: match charting and serve-plus-one

### Takeaway
The open Match Charting Project codes every shot (type, direction, depth, error type, outcome), which makes serve-plus-one patterns and per-situation tendencies measurable. It records what was done, not what was planned.

### Cited Findings
- Volunteers annotate point-by-point data from video using a standard code: match state, server, winner, and per-shot type/direction/location and point-ending outcome; more than 10k matches (tier A/B, open data) — [Match Charting Project quick start](https://www.tennisabstract.com/blog/2015/09/23/the-match-charting-project-quick-start-guide/); [MCP update post](https://www.tennisabstract.com/blog/2013/12/02/match-charting-project-update-tutorial-tracking-tools/)
- "Serve plus one" statistics: points won on the serve or the third shot (tier B) — [MCP serve stats glossary](https://www.tennisabstract.com/blog/?p=3711)
- Reliability of volunteer charting is itself a research question (a university thesis proposal on match-charting reliability exists; no results seen) (tier D) — [Saarland proposal](https://www.uni-saarland.de/fileadmin/upload/fachrichtung/swi/Sports_analytics/Thesis_proposals/Thesis_proposal_match_charting_reliabiltiy.pdf)

### Inferences
- Closest structural analog to hitting: a repeated, short, sequenced contest (serve then return then shot 3) with an identifiable server, state and per-pitch shot coding. A tennis tactical plan ("serve wide, then forehand to open court") has the same shape as "fastball away early, then sit on breaking ball".
- Verdict: MEDIUM-HIGH for the coding schema (state plus sequence plus outcome); no intent field to copy.

### Gaps
- No published example of a tennis coach's pre-match tactical plan graded post hoc.

## Cricket: batting approach vs bowler type

### Takeaway
Public cricket analytics frame approach as strike rate vs dismissal rate by phase and bowler type, not as a logged intent; I found no formal published intent framework in the searched sources.

### Cited Findings
- Practitioner posts describe a strike-rate vs dismissal-rate view by phase, with dependencies on bowler type, pitch, field restrictions and match state, and clusters of players by role (tier D, blog-quality) — [Intent and impact post](https://arnavj.substack.com/p/solving-the-intent-and-impact-equation); [Batting performance page](https://gravitee.io/corpus/gen-963/2025-rangpur-riders-season/batting-performance.html)
- A 2026 systematic review of cricket analytics exists (not read) — [University of Sunderland/OARS PDF](https://oars.uos.ac.uk/5569/1/2026.%20Systematic%20Review%20Cricket.pdf)

### Inferences
- "Intent" in cricket is usually inferred from outcome (strike rate, control %), which is circular for our purpose.
- Verdict: LOW as a method source; useful only as confirmation that phase-by-bowler-type splits are the standard unit.

### Gaps
- No peer-reviewed intent framework found; "control percentage" and shot-intent tagging by providers not verified.

## Golf: strokes gained and decision quality

### Takeaway
Strokes gained (Broadie) gives each shot a value against a baseline and supports choosing the aim point that maximizes expected strokes gained, which is an explicit decision-quality benchmark separate from the shot result. Evidence shows golfers do not follow it well.

### Cited Findings
- Broadie's strokes gained uses PGA Tour ShotLink data since 2003; PGA Tour adopted strokes gained putting in 2011 and tee-to-green later (tier A/B) — [Columbia Business School release](https://business.columbia.edu/press-release/cbs-press-releases/new-book-columbia-business-school-professor-shows-golfers-all); book "Every Shot Counts" (2014)
- Target selection rule: choose the target with the lowest expected strokes to finish, i.e., highest expected strokes gained given your dispersion (tier B/C, secondary summary) — [Titleist Learning Lab](https://www.titleist.com/learning-lab/performance/strokes-gained)
- Experiment (TrackMan simulator, handicap golfers): participants did not shift aim points to account for a penalty region despite large expected-payoff gains (tier A, snippet only) — [Fore-getting the Risk, JEMS](https://scapps.org/jems/index.php/1/article/view/3881)
- Rational score-minimization model of golf behavior (tier A, working paper, date not confirmed) — [Harvard](https://scholar.harvard.edu/sites/scholar.harvard.edu/files/mack/files/a_model_of_score_minimization_and_rational_golf_course_behavior.pdf)

### Inferences
- Golf's decision benchmark depends on the player's own dispersion, which is the exact analog of a hitter's own swing-decision and contact profile vs a pitch type/location; the best aim point differs by player. Fits "approach per count" as an optimization given personal skill.
- Verdict: HIGH conceptually (optimal choice given own skill vs this opponent's distribution); needs a per-hitter run-value-by-pitch-zone-by-count surface.

### Gaps
- Springer 2025 paper surfaced (s00180-025-01659-6) but content unread; relevance unknown.

## Poker, chess, forecasting: separating decision quality from outcome

### Takeaway
All three have a decision-quality measure that does not depend on the single result: poker's "resulting" concept, chess engine centipawn loss, and forecasting Brier score. Poker's is conceptual only; chess and forecasting have scored, repeatable metrics.

### Cited Findings
- "Resulting": judging a decision by its outcome; Annie Duke (Thinking in Bets, 2018) argues good decisions can have bad outcomes and vice versa (tier B) — [Annie Duke site](https://www.annieduke.com/?p=3108); [summary](https://evansamek.substack.com/p/thinking-in-bets-by-annie-duke?open=false)
- Chess: centipawn loss is the distance between the played move and the engine's best move; averages can mislead, since consistent small losses can lose a game with no blunder (tier B/C) — [ChessBase](https://en.chessbase.com/post/106064); [Chessitup](https://chessitup.com/blog/centipawn-loss-explained)
- Disconfirming: players and forums report "perfect" engine accuracy scores in lost games and odd accuracy numbers, so the metric is a weak proxy for game result and depends on engine and depth (tier D) — [Lichess forum](https://lichess.org/forum/lichess-feedback/perfect-playing-according-to-lichess-but-one-player-lost-the-game); [Chess.com forum](https://www.chess.com/forum/view/general/strange-accuracy-score?lc=1)
- Forecasting: Tetlock/Good Judgment Project tournaments scored with Brier scores; under one hour of "CHAMPS KNOW" training improved accuracy 6 to 11% over control (tier A via Chen et al. 2016, Judgment and Decision Making, snippet only) — [IDEAS/RePEc entry](https://ideas.repec.org/a/cup/judgdm/v11y2016i5p509-526_8.html); [AI Impacts summary](https://aiimpacts.org/?p=1260)

### Inferences
- Key transferable idea: record a probability or intended action before the event, score it against an external benchmark, and aggregate over many trials because single outcomes are noisy. Forecasting is the only domain here where the pre-event log is itself the graded object.
- Chess shows the benchmark is only as good as the engine; for hitting, the "engine" is a run-value model and its errors become the grade's errors.
- Verdict: HIGH for the log-then-score discipline (Brier-style scoring of "plan: take until strike two" as a probabilistic commitment); LOW for poker's concept beyond vocabulary.

### Gaps
- Original Duke and Chen papers not read; no evidence found that resulting-awareness training improves sport decisions.

## Any sport where a plan is logged pre-game and graded afterward

### Takeaway
I did not find a public log schema for a coach's pre-game plan graded afterward in any sport. Closest items are rugby/football KPI lists and the football assignment grading above.

### Cited Findings
- Rugby coaching guidance: coaches pick KPIs that fit their game plan and opposition from an effectively unlimited set (tier B) — [Rugby Toolbox](https://www.rugbytoolbox.co.nz/resources-education/learn-more/articles/snook-on-coaching/keyperformanceindicators)
- Retrospective rugby study across 65 matches with 19 PIs; "ruck quick" had the largest positive effect on match outcome (tier A, snippet only) — [Retrospective evaluation, LIDA](https://lida.sport-iat.de/ta/Record/4029023?lng=en)
- Rugby performance analysis review (tier A) — [PMC6962412](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6962412/)
- Disconfirming: a South African study of coaches' engagement with performance analysis exists (content not read), consistent with coach uptake being a known problem (tier A, title only) — [Stellenbosch](https://scholar.sun.ac.za:443/handle/10019.1/98094)

### Inferences
- KPIs are chosen retrospectively by analysts and correlated with winning; this is outcome-correlation, not plan-vs-execution.
- A workable schema for hitting would need to be designed, borrowing: assignment plus expectation grade (PFF), state before the event (count, pitcher, game leverage), a probability or confidence at logging (forecasting), and a decision-value benchmark (strokes gained / EPV style).

### Gaps
- Pre-registered plan schema from any sport: not found. Possibly exists inside clubs privately.

## Baseball-specific context found incidentally
- Rob Orr's SEAGER (SElective Aggression Engagement Rate) measures approach as aggressive swings on hittable pitches and selectivity on non-hittable ones, accounting for count (tier B/D) — [Phillies Minor Thoughts](https://philliesminorthoughts.com/phillies-hitters-and-swing-decisions-a-riff-on-rob-orrs-seager/)
- Baseball Prospectus has used per-batter decision trees to describe approach (tier B) — [BP](https://baseballprospectus.com/?p=54310)
- Both infer approach from swing behavior, not from a logged plan, so they share the circularity noted in cricket.

## Verdict table (transferability to hitting approach per count vs a specific starter)
| Analog | Unit of intent | Execution graded separately? | Success metric | Verdict |
|---|---|---|---|---|
| Football PFF | Assignment on a called play | Yes, grade vs expectation | Grade (-2 to +2), human, unaudited externally | High (schema idea) |
| Football 4th-down tools | Coach's call | Decision vs model, not execution | Win probability | Medium |
| Basketball tagging/EPV | Play type (inferred) / each decision | Decision value separate from result in EPV | Points per possession, EPV | Medium-high (state-value) |
| Soccer VAEP/xT/pitch control | None (action as observed) | Value of action, not plan | Change in score/concede probability | Medium |
| Tennis charting | None (observed shot sequence) | No | Point won, serve+1 | Medium-high (schema) |
| Cricket | None public | No | Strike rate vs dismissal rate | Low |
| Golf strokes gained | Aim point / club choice | Yes, optimum given own dispersion | Expected strokes | High (concept) |
| Poker/chess/forecasting | Action or probability committed before event | Yes | Brier / centipawn loss | High (log-then-score) |
