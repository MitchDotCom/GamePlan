# Minor-league data and tracking-system specifics for a Single-A (Visalia Rawhide) hitter-approach engine

Scope note: research was limited by the environment. Search worked (and was rate-limited once); page fetches were blocked for baseballamerica.com, mlbdatawarehouse.com, mlb.com, trackman.com, tht.fangraphs.com and baseballcloud.blog, so several findings rest on search-result summaries of those pages rather than full text. Only baseballsavant.mlb.com could be opened. License screen: 9 surfaced pages (Wikipedia and a Fandom wiki, share-alike) were omitted for license reasons. Other news/analyst pages carry no stated reuse license; I cite them only for facts (not text), which is an assumption the owner may want to confirm.

## 1. Tracking systems by level/league/park (2024-2026) and MLB takeover of data capture

### Takeaway
MLB announced it will become the single data collector for minor-league (and amateur) tracking, with Hawk-Eye as the target system, equal access for all 30 clubs, and capture for all minor-league games starting 2026. I found no source listing system by park for each Single-A league, and nothing park-specific for Valley Strong Ballpark (Visalia).

### Cited Findings
- MLB is standardizing analytical data capture and distribution across MiLB and amateur baseball; MLB will deal with the tech vendors and collect tracking, biomechanical and other data, with all 30 clubs having equal access. — [Baseball America via search summary (page blocked)](https://www.baseballamerica.com/stories/8-takeaways-from-mlbs-new-minor-league-data-regulation-plan/); [MLB Data Warehouse via search summary (page blocked)](https://www.mlbdatawarehouse.com/p/mlb-to-regulate-minor-league-data)
- Same sources (as summarized): every organization and minor-league park will be held to the same standards; where a park lacks Hawk-Eye cameras and other tech, MLB will buy, install and maintain them; data to be captured for all minor-league games starting 2026. — same two links above
- MLB has used Hawk-Eye cameras to power Statcast since 2020, and in 2026 uses the same infrastructure for ABS in the majors. — [TV Technology](https://www.tvtechnology.com/production/sports-production/baseball-2026-more-ai-better-viewing-choices)
- Minor-league Statcast (Hawk-Eye) on Savant covers only designated parks: Single-A was the Florida State League's 8 Statcast-enabled parks from 2021; Triple-A all games from 2023 — [Savant Minor League Statcast Search](https://baseballsavant.mlb.com/statcast-search-minors); [MLB.com via search summary](https://www.mlb.com/news/minor-league-statcast-data)
- Visalia: search found Valley Strong Ballpark is the smallest MLB-affiliated park (1,888 seats plus lawn); no result stated its tracking system. — [MiLB.com ballpark page](https://www.milb.com/visalia/ballpark) (no tracking info there per search)

### Inferences
- The "mostly TrackMan, some Hawk-Eye" assumption in the brief is consistent with the pre-2026 mixed state, but if MLB's 2026 plan was executed, Single-A parks should converge on Hawk-Eye; execution status as of Oct 2026 is unverified.
- Because the engine will see mixed systems for historical Visalia data (pre-2026) and possibly Hawk-Eye after, system must be a covariate or harmonization target.

### Gaps
- No full text of the Baseball America or MLB Data Warehouse pieces; no confirmation of which parks actually had Hawk-Eye installed in 2026, vendor contracts, whether TrackMan is retained, or what clubs may still collect privately.
- No source on tracking system by Single-A league (California, Carolina, Florida State) or specific park, nor Visalia specifically.
- Details of what clubs lose or gain (cost, data format/latency, access to raw feeds) not found.

## 2. Fields: TrackMan vs Hawk-Eye; known discrepancies; harmonization

### Takeaway
TrackMan is radar (infers release point and spin from the trajectory); Hawk-Eye is 12-camera optical (observes release, measures spin components directly, and provides skeletal and bat tracking). A published analysis found Hawk-Eye extensions about a third of a foot larger than TrackMan/PITCHf/x, with a consistent offset, so cross-system extension and release-point comparisons need a correction.

### Cited Findings
- Hawk-Eye uses 12 high-frame-rate cameras per park; TrackMan uses radar. — [FanGraphs/THT via search summary](https://tht.fangraphs.com/theres-lots-of-physics-to-do-now-that-hawk-eye-is-up-and-running/)
- At Hawk-Eye's 2020 debut, league-average extension was about 1/3 ft higher than TrackMan and PITCHf/x (~6 ft), and the disagreement looked relatively consistent. — [Baseball Cloud blog via search summary (page blocked)](https://baseballcloud.blog/2020/08/14/is-hawk-eye-inflating-extensions/)
- Radar infers release from the ball's deceleration; Hawk-Eye's cameras can see the ball leave the hand. — same blog, via search summary
- Hawk-Eye can measure spin components (backspin, sidespin, gyro) directly rather than inferring from movement. — [Baseball Cloud blog via search summary](https://baseballcloud.blog/2020/08/14/is-hawk-eye-inflating-extensions/); [Draysbay primer](https://www.draysbay.com/2022/5/26/23076575/an-optional-primer-on-pitch-shape-data) (surfaced, not opened)
- Hawk-Eye plate location was reported accurate to about 1/4 inch horizontally in preliminary measurements. — [ESPN](https://www.espn.com/mlb/story/_/id/26753650/robo-umps-not-fast-here-mlb-technology-upgrade-means) (via search summary)
- Bat tracking in MLB (swing speed, swing length etc.) is Hawk-Eye based, measured at the sweet spot six inches from the bat head; published from the second half of 2023 in MLB. — [JustBaseball via search summary](https://www.justbaseball.com/mlb/five-mlb-teams-stand-out-new-statcast-bat-speed-metrics-baseball-savant/); [Savant minors coverage summary](https://baseballsavant.mlb.com/statcast-search-minors)
- Savant minors search fields include pitch type/result, location zones, batted-ball direction/type, quality of contact, count, runners, handedness, venue and team filters. — [Savant](https://baseballsavant.mlb.com/statcast-search-minors)

### Inferences
- A per-system additive extension/release-height offset (estimated from pitchers who appear in both systems) is a plausible harmonization; none published for minors was found.
- Park-level random effects or a system indicator would be a defensible fallback.

### Gaps
- TrackMan's official field list (blocked), and published numeric discrepancies for spin rate, movement, plate location and zone height beyond the extension offset above, were not found.
- No published calibration/harmonization methodology across systems or parks found.

## 3. Public minor-league data and ABS status

### Takeaway
Public Savant minor-league Statcast is partial: Triple-A (all games from 2023; PCL plus Charlotte home in 2022) and Single-A only for the Florida State League's Statcast parks from 2021; no California League and no Double-A listed on the pages I could see. ABS challenge is established in Triple-A; I could not confirm 2025-26 status at Single-A.

### Cited Findings
- Savant coverage: Triple-A all games from 2023, PCL and Charlotte home 2022, FSL (Single-A) from 2021; the page says coverage is for "certain levels and ballparks". — [Savant](https://baseballsavant.mlb.com/statcast-search-minors)
- Earlier reporting: only eight Statcast-enabled FSL parks and no Double-A. — [MLB.com via search summary](https://www.mlb.com/news/minor-league-statcast-data)
- ABS tested in the Low-A Southeast League in 2021 (8 of 9 parks), Triple-A from 2022, all Triple-A from 2023; challenge system replaced full ABS by end of 2024; in 2025 both Triple-A leagues used two challenges, overturn rate 50%. — [ESPN](https://www.espn.com/mlb/story/_/id/40377474/abs-challenge-system-set-used-triple-starting-june-25); [Yahoo Sports](https://sports.yahoo.com/mlb/article/abs-challenge-system-is-coming-to-mlb-in-2026-heres-what-you-need-to-know-203356409.html)
- ABS challenge was adopted in MLB for 2026 (spring training, regular season, postseason), using Hawk-Eye cameras. — [MLB press release](https://www.mlb.com/press-release/press-release-mlb-announces-abs-challenge-system-coming-to-the-major-leagues-beginning-in-the-2026-season)
- Savant has an ABS Challenges leaderboard with a level filter (Triple-A selected in the URL), 2026. — [Savant](https://baseballsavant.mlb.com/leaderboard/abs-challenges?chalOrg=134&gameType=regular&year=2026&challengeType=batter&level=aaa&minChal=1&minOppChal=0)

### Inferences
- The Savant page text did not mention 2024-26 expansion; it may have been extended (the takeover plan implies it could), but I could not verify.
- Pitch-level public Statcast for Visalia likely does not exist for pre-2026; the engine's Single-A training data likely comes from club-internal feeds.

### Gaps
- Coverage by year for 2024-2026, whether bat tracking appears in public minors data, and ABS status at High-A/Low-A/Double-A for 2025-26 were not confirmed (rate-limited search; MLB.com blocked).

## 4. Single-A sample sizes, turnover, thin-data handling

### Takeaway
No source gave Single-A per-player tracked-swing or pitch counts, starter workloads or turnover figures; I can only supply general stabilization benchmarks.

### Cited Findings
- Search-summarized benchmarks: K% stabilizes around 60 PA, BB% about 120 PA, HR rate about 300 PA, ISO about 550 PA, AVG about 910 AB; a swing-decision metric (SOTO) median stabilization about 255 pitches (~51 PA). — [Athlon (2026)](https://athlonsports.com/fantasy/fantasy-baseball-when-do-batter-stats-matter-2026) and [Salorio swing decision model](https://adamsalorio.substack.com/p/introducing-my-swing-decision-model), via search summary (attribution of individual numbers to each page not verified)
- General principle: statistics do not stabilize at a single point; reliability accrues gradually. — [FanGraphs Library, Sample Size](https://library.fangraphs.com/principles/sample-size/)

### Inferences
- A Single-A hitter over a ~120-game season (roughly 450-550 PA, an assumption not sourced) sits near the K%/BB% stabilization range but far from ISO/AVG, so strong shrinkage to level/league priors (empirical-Bayes / hierarchical) is warranted for outcomes, while process metrics (swing decision, zone contact) lean more on the player's own data.
- Call-ups mean partial seasons and truncated histories; model should carry player latent traits across levels with level-specific priors.

### Gaps
- No data found on tracked swings per hitter, pitches per starter, starts per pitcher, or roster turnover at Single-A; no source on how organizations handle thin data (priors from level averages, scouting reports).
- A claim that bat speed becomes reliable in ~3 swings appeared in a search summary without an identifiable source; treat as unverified.

## 5. Platoon and level-of-competition effects

### Takeaway
Run environments vary widely within Single-A; the California League has historically been the most hitter-friendly full-season league, so MLB-fit priors must be refit by level and league (and park).

### Cited Findings
- Historical analysis: the California League had the most runs per game of any full-season league (more than 5 R/G in 2007-2009), the Florida State League the fewest, more than a run lower; a .256/.324/.374 FSL hitter would project around .271/.339/.418 in the Cal League. — [FanGraphs/THT, Minor league run environments (via search summary; page blocked)](https://tht.fangraphs.com/minor-league-run-environments/)
- Park effects can be extreme within the Cal League (e.g., San Jose's strikeout rate was the highest in the minors, attributed to the hitting background). — same source, via search summary
- MiLB.com publishes Single-A park-effect pieces ([X-Factors: A Advanced park effects](https://www.milb.com/news/gcs-66911570)); not opened.

### Inferences
- Those numbers are from 2007-2009 and may not reflect today (league realignment in 2021-22 and rule changes such as pitch clock, bigger bases).
- Hierarchical priors with level, league and park effects, refit each season, is the implied approach.

### Gaps
- No current (2023-2026) run-environment, pitcher-quality or platoon-split data by level found; no published level-adjustment translation for approach metrics.

## 6. Metrics available by system

### Takeaway
Inferred from sections 2-3 rather than from one source: Hawk-Eye gives the full set (pitch release/extension/spin components, batted-ball, bat tracking); TrackMan gives pitch trajectory/movement/location and batted-ball but not optical release/spin direction or bat tracking; with no bat tracking, swing-decision and contact-quality metrics from pitch location plus outcomes remain.

### Cited Findings
- Bat tracking is Hawk-Eye-derived. — [JustBaseball via search summary](https://www.justbaseball.com/mlb/five-mlb-teams-stand-out-new-statcast-bat-speed-metrics-baseball-savant/)
- TrackMan is radar-based, extension inferred. — see section 2 citations.

### Inferences
- Reliable on TrackMan only: pitch velocity, movement, location, batted-ball exit velocity/launch angle/direction, swing-decision metrics (location-based); less reliable: extension, release point, spin axis/gyro.
- Hawk-Eye: all of the above plus bat speed, swing length, attack angle, and direct spin.
- No bat tracking: use swing/take decisions, zone contact, and exit-velocity-based proxies; bat speed unavailable.

### Gaps
- No documented TrackMan field list, and no source on whether bat-tracking metrics are published at Single-A parks.
