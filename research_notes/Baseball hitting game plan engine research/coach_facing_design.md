# Coach-facing design and approach vocabulary for a baseball hitting game-plan tool

Research limits: only search-result snippets were readable. WebFetch was blocked (egress proxy) for drivelinebaseball.com, thebanner.com and mlb.com, so every finding below comes from search-engine summaries, not full-page reads. No ABCA, coaching-book or clinic primary text was reached. Treat definitions as secondary summaries to verify. Licensing: I could not check licenses for the pages cited (most are ordinary copyrighted web pages). I cite facts and ideas only, with links, and reproduce no text. I excluded ResearchGate/Academia mirror copies as a precaution; no source I knew to be non-commercial/share-alike is used, so the count omitted for license reasons is 0 known, but license status is unverified for all cited pages (the report writer may want to treat that as an open compliance item).

## Approach vocabulary used by coaches and in the literature

### Takeaway
Core terms are consistent across sources: hunt a location, sit on a pitch type/timing, adjust off it, selective aggression, and two-strike modifications (shorten, protect, expand). Modern coaches split on whether to "expand" the zone with two strikes, which supports tag-based rather than aggressive/passive naming.

### Cited Findings
- Driveline (secondary summary): rather than guessing "fastball," the hitter "hunts" a location such as middle-in and does not swing if the pitch is not there. — [Driveline, Developing a Baseball Hitting Approach](https://www.drivelinebaseball.com/2022/08/developing-a-baseball-hitting-approach/) (via search summary; page not opened)
- Driveline: with two strikes, sit on the high fastball (common with two strikes in MLB); a top-down, up-the-middle line-drive approach; sitting high makes the low-away slider less appealing. — same source (via search summary)
- Timing principle behind "sit fast, adjust slow": if timed for the fastball a hitter can slow down for offspeed, but cannot speed up if timed for the changeup. — [Applied Vision Baseball / related results](https://appliedvisionbaseball.com/best-way-to-hit-fast-pitching/) (search summary; exact attribution of the phrase to Driveline not confirmed)
- Two-strike vocabulary: choke up/shorten the swing, widen the stance, expand the zone ("swing at anything close," not chase wildly), "protect the plate." — [GRB Academy, The Art of Two-Strike Hitting](https://grbacademy.com/2025/02/24/the-art-of-two-strike-hitting/); [Moonshot](https://blog.moonshotsocial.com/two-strike-approach-for-hitters/); [Seams Up](https://seamsup.com/blog/what-s-the-best-two-strike-approach-for-baseball-and-softball-hitters)
- Disagreement: some modern coaches say hitters should not expand to protect the plate, "shorten up but stay selectively aggressive" instead. — summarized in the search result for the two-strike query (above sources)
- Zone-based hitting ("zone hitting," leveraging an at-bat by region) is a common coach framing. — [Chase Glaum, Medium](https://chaseglaum.medium.com/zone-hitting-leveraging-your-at-bat-6bd0079a60d2) (title only seen)
- Statcast swing/take uses four zone regions: heart, shadow, chase, waste; damage is credited by pitch location, count and swing/take decision. — [Baseball Savant Swing/Take](https://baseballsavant.mlb.com/swing-take) and a summary of it in search results

### Inferences
- Suggested tag axes (each approach path carries several tags): Target (zone/location hunt: inner, middle, away, up, down, middle-out), Pitch-type basis (sit FB, sit offspeed, react/no sit), Timing (sit-fast, adjust-slow), Zone width (hunt-narrow, standard, expanded/protect), Swing intent (damage, contact/shorten, situational: move runner/sac fly), Count role (hitter's count, even, two-strike). Two "aggressive" paths then differ in tags, e.g. "hunt away FB damage" vs "hunt inner FB damage".
- "React / see-it-hit-it," "cover a zone," "working the count" and "damage vs contact" were not directly sourced here; use them as coach-validated vocabulary only after review by the actual coach.

### Gaps
- No ABCA, MLB.com, or coaching-book definitions retrieved (blocked or not found). Definitions of "selective aggression," "hitter's count approach," "move the runner" lack primary citations.

## How teams build pregame hitter plans; post-game swing-decision review

### Takeaway
Publicly described practice is light on detail: a hitting-coach-led group meeting of up to about 15 minutes (Yankees), or an individualized model where reports are sent the night before and hitters meet coaches one-on-one (Orioles). Contents center on pitch usage by count and location.

### Cited Findings
- Yankees' hitting coach leads a hitters' meeting lasting up to 15 minutes to discuss approaches before each matchup. — [MLB.com, Yankees Magazine: Anatomy of a Doubleheader](https://www.mlb.com/news/yankees-doubleheader-behind-the-scenes) (search summary)
- Orioles put onus on hitters to study reports sent the night before, then meet individually with coaches at the park; hitting coaches send the advance report and possible attack plans via a WhatsApp group. — [The Banner](https://www.thebanner.com/sports/orioles-mlb/orioles-hitting-meetings-individual-approach-FLG3E7UP2REEBFCGRM3PRC5VSI/) (search summary)
- Advance reports show what pitches to expect, how the pitcher attacks in certain counts, and where he locates pitches; teams break down video hitter by hitter and pitcher by pitcher. — [FanGraphs, Tigers, Red Sox and Advance Scouting](https://blogs.fangraphs.com/the-tigers-the-red-sox-and-advance-scouting/) (search summary)
- Plan building requires knowing where the pitcher locates each pitch: inner/outer half, upper/lower zone. — search summary of the MLB advance scouting results above
- Swing-decision metrics exist for review: PLV Decision Value rates each swing/take using velocity, location and movement. — [Pitcher List, Decision Value](https://pitcherlist.com/using-plvs-decision-value-to-evaluate-hitter-ability-power-edition/)
- Video and tools (HitTrax, Rapsodo, Blast) used by player-development staff for post-game review. — [Hitters Baseball Academy](https://hittersbaseballacademy.com/role-of-analytics-in-modern-baseball/) (vendor/academy marketing; weak evidence)

### Inferences
- A 15-minute group slot implies roughly 9 hitters x under 2 minutes each if done in a block, so per-hitter content must fit a glance; the Orioles model suggests a pre-read plus per-hitter conversation, which fits a board that works both as handout and meeting screen.
- Post-game review can reuse the same tags: compare the planned path by count to the swing-decision outcome (swing/take, zone region), framing it as development feedback, not compliance scoring.

### Gaps
- Typical report length/page count and format (PDF, binder, app) were not found. No public detail on development-focused use of swing-decision review beyond metrics descriptions.

## Human factors: option counts, defaults, uncertainty, trust, override

### Takeaway
Evidence says more options are not reliably harmful; overload depends on task difficulty, set complexity, preference uncertainty and goals. So 2 to 3 options with grouping and a transparent default is defensible. Explanations do not reliably prevent over-reliance, so override must be easy and logged.

### Cited Findings
- Meta-analysis (63 conditions, 50 experiments, 5,036 participants): average choice-overload effect near zero with large between-study variation. — [Scheibehenne, Greifeneder & Todd 2010](https://www.academia.edu/646655/Can_there_ever_be_too_many_options_A_meta_analytic_review_of_choice_overload) (mirror link; the paper is a journal article)
- Second meta-analysis (99 observations, 7,202 participants): overload risk tied to decision task difficulty, choice set complexity, preference uncertainty, decision goals. — [Chernev, Böckenholt & Goodman 2015](https://chernev.com/wp-content/uploads/2017/02/ChoiceOverload_JCP_2015.pdf)
- Large sets can push people toward a default; recommended designs test grouped options, aligned comparison, guided narrowing, or a transparent default. — [Dean, Ravindran & Stoye, A Better Test of Choice Overload](https://bfi.uchicago.edu/wp-content/uploads/2024/08/Dean.A-Better-Test-of-Choice-Overload80.pdf) (search summary)
- Automation bias: in a clinical DSS study, clinicians overrode their own correct decisions in 12% of cases in favor of erroneous advice (another figure of 6% appears in the summary; the two numbers are not reconciled in my snippet). — summary of [Automation bias in clinical decision support](https://www.researchgate.net/publication/49849912_Automation_bias_-_A_hidden_issue_for_clinical_decision_support_system_use) (low confidence; verify)
- Explanations did not reduce automation bias and sometimes increased it. — [Vered et al. 2023, effects of explanations on automation bias](https://psychologicalsciences.unimelb.edu.au/__data/assets/pdf_file/0019/5252131/2023Vered.pdf)
- Trust vs. self-confidence balance is a key driver of automation bias; risk is higher under time pressure. — same search results

### Inferences
- Keep 2-3 options per count, aligned in identical slots (same tag rows) so comparison is easy; mark one as the default recommendation but show it as a suggestion.
- Show uncertainty as sample size/confidence badges (e.g., "n=38 pitches") rather than false-precision numbers; hide cells below a minimum sample.
- Override: one tap to pick a different path or write a coach's own, with reason tags; log for post-game review, never penalize. Given the explanation findings, show evidence ("why") alongside but avoid persuasive framing.
- Dugout capacity limits were not sourced; assume a single glance per count and design for the pregame meeting first.

### Gaps
- No HCI evidence found on small multiples for coaches, dugout information limits, or sports-specific decision-support trust. Tufte/small-multiples sources not retrieved.

## Zone-plan display: heat maps, color accessibility, public tools

### Takeaway
Baseball Savant sets the convention coaches already know: catcher/batter-view zone, red good / blue bad. Accessible practice favors perceptually uniform sequential palettes and not relying on hue alone.

### Cited Findings
- Savant Swing/Take shows a Zone Profile, pitch-frequency circles, swing/take percentage chart and run-value graph; zone shown from the batter's point of view with red good, blue bad. — [Baseball Savant](https://baseballsavant.mlb.com/swing-take) and a search-result summary of it
- Viridis/cividis are colorblind-safe perceptually uniform sequential palettes that stay legible in grayscale; lightness-based sequential scales survive color-vision deficiency. — [colorblind.io guide](https://colorblind.io/guides/colorblind-safe-palettes) (secondary); [Gotelli lab viridis note](https://gotellilab.github.io/GotelliLabMeetingHacks/NickGotelli/ViridisColorPalette.html)
- Suggested check: at least 30 CIELAB lightness units between category colors; test with a CVD simulator. — colorblind.io guide above (single secondary source)
- Other public tools: Baseball Hitting Charts ("Hitting Approach") [hittingapproach.com](https://www.hittingapproach.com/hitting-approach-blog/64ltt6h31eoom8ffreq1cyj8mtqz7l) appears to offer approach charts (not opened).

### Inferences
- Red-blue diverging maps are familiar but problematic for red-green deficiency (blue-red is generally okay; verify with simulator). Use a diverging blue-orange scale or lightness-led scale plus numeric labels in cells and thick outline for the planned "hunt" zone.
- Plan boards should draw the intended zone as an outlined region/shape over a faint damage heat map, rather than encode the plan itself in color.

### Gaps
- No evidence on what coaches themselves find usable (no coach interviews or usability studies found). Savant page not opened directly.

## Recommendations: tag taxonomy and board layout

### Takeaway
Use multi-axis tags per path and a fixed-slot board; these are design proposals built on the findings above, not validated with coaches.

### Cited Findings
- Vocabulary basis: see sections above (Driveline hunt/sit, two-strike terms, Savant zone regions).

### Inferences
- Tag axes: Zone target; Pitch basis; Timing; Zone width; Intent (damage/contact/situational); Risk note (e.g., chase risk). Two paths can share "damage" yet differ on target; no path is called aggressive/passive.
- Board: one row per hitter (9), count selector across (0-0 ... 3-2, or grouped into hitter's / even / two-strike), 2-3 path cards per count with identical tag slots, an outlined mini zone on each card, small multiples across counts so patterns are visible at once, a sample-size badge, and a default marker plus "choose other / own" control that records the override.
- Two modes: pregame (all 9, printable) and post-game review (planned path vs actual swing/take by zone, development notes).
- Present counts in groups to limit load; confirm with the coach which grouping they use.
- Assumption: development-first means tags and review show decision quality and skill-building focus (e.g., "practice target"), with win-probability secondary.

### Gaps
- Needs coach validation; no source tested these layouts.
