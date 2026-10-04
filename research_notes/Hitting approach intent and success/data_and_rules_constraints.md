# Data and rules constraints for a Single-A (California League) hitting tool

Research date: 2026-10-04. Method note: search snippets were available for many sources, but direct fetch of mlb.com, milb.com, wikipedia, ajc.com and several news sites was blocked by the network proxy. Only baseballsavant.mlb.com pages were fetched directly. Claims below rest on search-result summaries unless marked "fetched". Tiers: A primary rule/data source, B reputable report, C vendor/marketing, D opinion. Confidence: H/M/L.

## 1. Is ABS (automated ball-strike) used at Single-A, including the California League, in 2025-2026?

### Takeaway
No source I found places ABS in the California League in 2025 or 2026, which is consistent with the product owner's statement (human umpires). Confidence: M (absence of evidence, plus the one 2026 source I found lists only the PCL). ABS history at Single-A is limited to the Florida State League (FSL), 2021-2022 trials, and its status there in 2025-26 was not verified.

### Cited Findings
- 2021: ABS challenge system tried at 8 of 9 FSL parks (then called Low-A Southeast); moved to Triple-A in 2022. Hawk-Eye cameras. [Tier B, search summary of AP-style coverage; M] — [Search result: thescore.com/mlb/news/3352429](https://thescore.com/mlb/news/3352429) and [news4jax 2025-09-23](https://www.news4jax.com/sports/2025/09/23/robot-umpires-approved-for-mlb-in-2026-as-part-of-challenge-system/)
- 2026 minor-league rule release: "ABS Challenge System and Check-Swing Adjudication coming to the Pacific Coast League," same rules as MLB (2 challenges per team, retained on success); check-swing challenge from May 5, 2026. [Tier A (MLB.com/MiLB official release) as reported in search snippet; page itself not fetched; M] — [MLB.com: Here are the new rules coming to the Minors this season](https://www.mlb.com/milb/news/new-rule-changes-coming-to-minor-leagues-in-2026)
- MLB approved the ABS Challenge System for MLB spring training, regular season, and postseason from 2026 (announced 2025-09-23). 12 Hawk-Eye cameras per park; T-Mobile private 5G. [Tier A press release, snippet only; H] — [MLB press release](https://www.mlb.com/press-release/press-release-mlb-announces-abs-challenge-system-coming-to-the-major-leagues-beginning-in-the-2026-season)
- A search summary said ABS is used "at Triple-A and the Single-A Florida State League." This appears to come from older (c. 2022-23) coverage and is not dated; treat as stale. [Tier B/unclear; L] — [Wikipedia: Automated Ball-Strike System](https://en.wikipedia.org/wiki/Automated_Ball-Strike_System) (not fetched)
- Independent/partner league: Yuba-Sutter Freebirds (Pioneer League, MLB Partner League) run full ABS for all 2026 home games. This is not the California League. [Tier B local news, 2026-04-14; M] — [Gridley Herald](https://www.gridleyherald.com/2026/04/14/569501/automated-strike-zone-debuts-in-bryant-field)
- Search results contained a wrong statement that the California League is an independent league. It is the MLB-affiliated Single-A league; disregard that summary.

### Inferences
- The 2026 official list naming only the PCL suggests no Single-A league has ABS in 2026. Not confirmed from the full text.
- Because Savant's tracking-derived pitch location in 2026 was re-referenced to the ABS plate-middle (see Q2), ABS-style zone logic may be reflected in data fields even where umpires call the game.

### Gaps
- Full text of the 2026 MiLB rules release (blocked); whether the FSL still used ABS in 2023-2026; any statement specific to California League umpiring. No evidence either way beyond the above.

## 2. Park tracking tech (TrackMan / Hawk-Eye) and public minor-league Statcast coverage

### Takeaway
Public minor-league Statcast on Baseball Savant covers Triple-A and, at Single-A, only the Florida State League. The California League is not listed. Per-park vendor/field availability for California League parks was not found. Confidence: M-H for Savant coverage (fetched directly), L for park-level technology.

### Cited Findings
- Savant Minor League Search (fetched 2026-10-04): Triple-A all games from 2023 (plus PCL games and Charlotte home games from 2022); Single-A listed as Florida State League games from 2021. Player lists span 2021-2026. [Tier A, H] — [Baseball Savant Minor League Search](https://baseballsavant.mlb.com/statcast-search-minors)
- MLB.com explainer: "For Single-A, the data dates back to 2021, but only for the eight Statcast-enabled Florida State League parks"; FSL data available again for 2023; access by toggling to Single-A on Gamefeed. Article date not confirmed (likely 2023). [Tier A/B, M] — [MLB.com: 8 ways to appreciate the gap between Majors and Minors](https://www.mlb.com/amp/news/minor-league-statcast-data-compared-to-mlb.html); [MLB.com: Statcast data on prospects](https://www.mlb.com/news/minor-league-statcast-data)
- Savant's site menu lists "Minor League Search" alongside Major League and WBC search; leaderboards cover 2015-2026 for MLB (fetched). [Tier A, H] — [Baseball Savant](https://baseballsavant.mlb.com/about)
- Savant CSV documentation (fetched): fields include release_speed, release_pos_x/z, spin_rate, launch_speed, launch_angle, hit_distance, plate_x/plate_z, bat-tracking fields attack_angle, swing_path_tilt and batter-ball contact point. "Through 2025 [plate_x/z] was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system." [Tier A, H, but describes the MLB schema generally; minor-league availability of each field not stated] — [Savant CSV docs](https://baseballsavant.mlb.com/csv-docs)
- Bat tracking: public on Savant from MLB data beginning second half of 2023, released May 13, 2024. Metrics: bat speed, swing length, squared-up rate; bat speed measured 6 inches from barrel end. [Tier A/B, H] — [Savant bat tracking](https://baseballsavant.mlb.com/leaderboard/bat-tracking); [SABR summary](https://sabr.org/latest/2024-sabr-analytics-watch-highlights-from-mlb-statcast-updates-weather-and-bat-tracking/)
- Savant bat-tracking page did not state minor-league coverage (fetched). No source found that bat tracking is public for any minor-league level.
- Hawk-Eye data is cited as collected "across the minor leagues" for org-level Hit+/Stuff+ rankings (Baseball America newsletter, date not confirmed). [Tier B, L] — [Baseball America Statcast Farm System Rankings](https://baseballamerica.beehiiv.com/p/statcast-farm-system-rankings)
- A search summary stated Hawk-Eye is "currently used exclusively in MLB"; this conflicts with the ABS and Triple-A Hawk-Eye facts above and the Baseball America item. Disregard it.

### Inferences
- California League is probably absent from public Savant data; hence the tool cannot rely on public pitch-level Cal League data unless the club supplies its own feed.
- Release, movement, and spin fields exist in the schema; per-level reliability is unverified.

### Gaps
- Which Cal League parks have TrackMan/Hawk-Eye/neither; whether any 2025-26 expansion occurred; Savant's own coverage text beyond the search page. The Savant "level" dropdown values were not rendered in the fetch, so Low-A/A+ options cannot be confirmed.

## 3. Does public minor-league data include the California League?

### Takeaway
Based on Savant's Minor League Search description, public Statcast includes the FSL as its only Single-A league; no California League coverage found. Confidence: M. (Traditional box-score/play-by-play stats on MiLB.com/MLB Stats API are a separate matter and do include all full-season leagues, but I did not verify this in this session.)

### Cited Findings
- See Q2: [Savant Minor League Search](https://baseballsavant.mlb.com/statcast-search-minors) (fetched, Tier A).

### Inferences
- If the owner wants pitch-level data for Cal League games, public Statcast will not provide it.

### Gaps
- Direct confirmation by inspecting Savant's league dropdown for 2025/2026.

## 4. Rules and norms: public data use while employed by a club; MLB data terms

### Takeaway
MLB's published Gameday/MLBAM terms permit only individual, non-commercial, non-bulk use; other use needs written authorization. I could not read MLB's current Terms of Use or Savant-specific terms directly, and found no public rule on club employees building personal tools. Confidence: M on the MLBAM clause, L on anything employment-related.

### Cited Findings
- MLBAM Gameday notice: materials are MLBAM proprietary; "only individual, non-commercial, non-bulk use of the Materials is permitted"; other use prohibited without prior written authorization; commercial use prohibited unless authorized. [Tier A as quoted via third-party documentation and search snippets; M; the wording is old (Gameday API era, c. 2010s)] — [Gameday API docs (rubydoc)](https://www.rubydoc.info/gems/gameday_api/0.5.3)
- MLB.com Terms of Use and MiLB.com terms exist and govern site use (not read): [mlb.com/tou](https://mlb.com/tou), [milb.com/about/terms](https://www.milb.com/about/terms).
- Savant CSV download is a built-in feature (CSV docs page fetched), implying personal analysis is an intended use. [Tier A, inference only]

### Inferences
- A tool used internally by a club staffer for the club's competitive purposes could be viewed as commercial or bulk use under MLBAM terms; clubs get data via league agreements, so the safe path is to use club-provided data feeds and obtain club IT/legal sign-off. This is my inference, not a sourced rule.
- Employer IP/confidentiality: club employment agreements typically cover work product and proprietary information; no public text found. Treat as unverified.

### Gaps
- Current MLB TOU text on scraping, automated access and rate limits; Savant-specific usage terms; any club or league policy on employee side projects. Recommend legal/club review.

## 5. Electronics and tools in the dugout (minor league)

### Takeaway
Public text found concerns MLB only. No public MiLB or Professional Baseball Agreement text on dugout electronics was found. Confidence: H for MLB facts, L for minors applicability.

### Cited Findings
- 2015-2016: MLB allowed iPads in dugouts for charts, stats and scouting reports; no Wi-Fi; only information loaded before first pitch. [Tier B, M (old)] — [Mactrast 2015](https://www.mactrast.com/2015/09/major-league-baseball-to-allow-ipads-in-dugouts-with-limitations/amp/); [SBJ 2016-03-30](https://www.sportsbusinessdaily.com/Daily/Issues/2016/03/30/Marketing-and-Sponsorship/Apple-MLB.aspx)
- 2026: league memo dated June 11, effective at the resumption after the All-Star break (about July 15, 2026), made dugout-iPad custom tabs inaccessible and barred AI recommendations on substitutions, pitch calling and other in-game decisions. About one-third of clubs had custom apps. [Tier B (AP wire), H] — [AP via WSLS 2026-07-17](https://www.wsls.com/sports/2026/07/17/mlb-restricts-dugout-ipad-use-to-prevent-use-of-ai-to-make-decisions/); [ABC News](https://abcnews.com/Sports/wireStory/mlb-restricts-dugout-ipad-prevent-ai-make-decisions-134856939)
- Coverage did not say whether the restriction applies to minor leagues.

### Inferences
- A decision-support hitting tool used live in the dugout (pitch-by-pitch swing/take recommendations) would conflict with the spirit of the MLB 2026 policy if mirrored in the minors; a pre-game or post-game tool carries much less risk. Unverified for MiLB.

### Gaps
- MiLB/PBA text on in-game electronics; whether MLB's 2026 AI restriction extends to affiliates.

## 6. 2026 rule changes relevant to hitters at Single-A

### Takeaway
2026 Single-A pitch-clock changes tighten batter timeouts, and ABS challenge is limited to the PCL in the minors. For California League hitters this means a human-called zone with a stricter clock. Confidence: M (search summary of official release).

### Cited Findings
- Single-A: no batter timeouts except special circumstances such as equipment issues; High-A allows time with runners on base; AA/AAA allow time but umpires do not wait for the batter to restart the clock. [Tier A snippet, M] — [MLB.com 2026 MiLB rule changes](https://www.mlb.com/news/new-rule-changes-coming-to-minor-leagues-in-2026)
- Catcher standing to give a mound visit or signals no longer resets the pitch clock; automatic ball if the catcher is not in position at 9 seconds. [Tier A snippet, M] — same source.
- ABS Challenge and check-swing challenge: PCL only among minor leagues per the release summary (see Q1).
- MLB ABS Challenge rules: 2 challenges per team, retained if successful ([MLB press release](https://www.mlb.com/press-release/press-release-mlb-announces-abs-challenge-system-coming-to-the-major-leagues-beginning-in-the-2026-season)).

### Inferences
- Without challenges, Single-A hitters face umpire-zone variability; a swing-versus-take model should not assume the Hawk-Eye zone defines called strikes. Shorter clock may reduce between-pitch information time.

### Gaps
- Exact pitch-clock seconds for Single-A in 2026 and any Cal League-specific variants (release page not fetched); whether 2026 changes carried into postseason.
