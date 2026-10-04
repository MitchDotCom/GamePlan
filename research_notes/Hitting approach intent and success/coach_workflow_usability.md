# Coach and player-development workflow, devices, report formats, and input design (GamePlan usability rules)

Method note: WebFetch was blocked by the network proxy for nearly every domain (mlb.com, masnsports.com, journal-news.com, teamworkonline.com, ericcressey.com, local10.com, pmc.ncbi.nlm.nih.gov). Everything below comes from WebSearch result summaries, not full-page reads. Retrieval date for all items: 2026-10-04. Article dates are taken from the URL where it carries one; otherwise marked "date not confirmed". Evidence tiers: A peer-reviewed or primary rule/data text, B named practitioner account, C vendor/marketing, D opinion. Many items are secondary reports of a primary source (labelled "secondary"). Nothing here describes any club's private systems.

## 1. Daily schedule and time available for information

### Takeaway
Public sources describe a sequence of morning/early-afternoon prep, pregame work with players, an offensive meeting after BP and glove work, then the game. There are no public minute-level time budgets for minor-league staff; the usable information windows are inferred. I found no named-staff source with explicit "I have X seconds" statements.

### Cited Findings
- A hitting coach arrives before noon, reviews the opposing starter's recent outings on computer against scouting reports, and watches the previous night's video to check hitters' timing and positioning, taking notes (tier B/D, secondary summary of a feature; date not confirmed) — [Dayton Dragons / Reds hitting coach feature via Journal-News](https://www.journal-news.com/sports/dayton-dragons-meet-the-hit-doctor-behind-the-reds-next-generation/article_a4d8fd6e-b1dd-5052-a992-5a2e45816468.html)
- Players arrive about 1:45 p.m. for pregame routines and one-on-one time with the coach; when glove work and BP end outside, an offensive meeting is held inside to set the game plan (same source and tier).
- BP is structured as four rounds of five swings; from round two coaches throw a mix including breaking balls and changeups emphasising what hitters will face that night (tier B, secondary summary; Orioles farm feature, date not confirmed) — [MASN, "On O's farm, hitters take BP routine..."](https://masnsports.com/blog/on-o-s-farm-hitters-take-bp-routine-and-turn-it-into-runs)
- Hitting coaches try to keep players "emotionally flat-lined" day to day because of the daily grind (tier B, same Dayton source).
- Club job postings describe the minor-league hitting coach role as working directly on mechanics and plate discipline and integrating modern analytics (tier C, job posting) — [Miami Marlins posting on Teamwork Online](https://www.teamworkonline.com/baseball-jobs/miamibaseball/miami-marlins/minor-league-hitting-coach-2184897) (posting text not read in full; that posting is a public ad and says nothing about private systems).

### Inferences
- The only structured group moment for the approach is the post-BP offensive meeting; GamePlan's laptop view should be built for that single window and the one-on-one pregame time.
- The hitting coach's pre-noon prep is the only solitary desk time; heavier review (opposing starter tendencies) belongs there, not in the dugout.

### Gaps
- No source found giving durations of the pregame meeting, dugout look-up windows, or postgame video sessions at the minor-league level.
- No named staff interview on Baseball America / The Athletic detailing a minor-league day was retrievable.

## 2. Devices, tools, and what is allowed in the dugout

### Takeaway
MLB dugouts use league-supplied iPads with video and league data; they have been offline-restricted since 2015-16 and in July 2026 MLB disabled the custom tab where clubs ran their own programs, including AI recommendations. I found no primary MiLB rule text; MiLB-specific rules are unconfirmed.

### Cited Findings
- MLB piloted dugout iPads late in the 2015 season with restrictions and expanded in 2016 under an Apple deal (tier A/B, secondary report) — [MacTrast, 2015](https://www.mactrast.com/2015/09/major-league-baseball-to-allow-ipads-in-dugouts-with-limitations/amp/); [MLB.com announcement of iPad Pro and MLB Dugout app, 2016](https://www.mlb.com/news/mlb-apple-bring-ipad-pro-into-dugout-c169682940)
- Authorized devices cannot connect to Wi-Fi, and teams can use only information transferred before the first pitch (tier A/B, secondary report of league rule) — same MLB.com / MacTrast sources, summarised in search result.
- The 2016 MLB Dugout app let staff view stats, pitcher-hitter matchups, spray charts, and cue past video (tier C/B, league/Apple announcement) — [MLB.com, 2016](https://www.mlb.com/news/mlb-apple-bring-ipad-pro-into-dugout-c169682940)
- Video was eliminated in 2020 after the Astros sign-stealing scandal and returned in 2021 (tier B, AP report) — [Ground News summary of AP](https://ground.news/article/mlb-reportedly-outlaws-use-of-dugout-ipads-to-access-ai-for-in-game-strategy)
- A June 11, 2026 memo from MLB EVP Morgan Sword said the custom tab had expanded iPad use to recommendations on substitutions, pitch calling and other in-game decisions; MLB made custom tabs inaccessible from the start of the second half of 2026; reportedly about one-third of teams had installed custom apps with AI recommendations; MLB found no sign-stealing or electronic-device rule violations (tier A for the memo as reported, B for the report; AP, 2026-07-17) — [WTOP/AP](https://wtop.com/mlb/2026/07/mlb-restricts-dugout-ipad-use-to-prevent-use-of-ai-to-make-decisions/); [AJC](https://www.ajc.com/news/2026/07/mlb-restricts-dugout-ipad-use-to-prevent-ai-to-make-decisions/)
- Adam Ottavino said on his "Baseball & Coffee" stream that the Mets used AI and cited owner spending (tier D, one person's claim, relayed by AP) — [WTOP/AP](https://wtop.com/mlb/2026/07/mlb-restricts-dugout-ipad-use-to-prevent-use-of-ai-to-make-decisions/)

### Inferences
- Any in-dugout GamePlan feature at an MLB-affiliated club risks being treated as an unauthorized decision aid if it recommends in-game actions or needs live connectivity. Pre-loaded, offline, non-recommending (a plan the coach already wrote) is the safest design, but compliance for the target club's league must be confirmed with the club; the notes cannot establish MiLB rules.
- The target club's stated approach is "mostly verbal"; a tablet view should be treated as an aide-memoire, not a new in-game screen habit.

### Gaps
- No primary text of the MLB/MiLB electronic-equipment regulation was retrievable; no MiLB-specific dugout device rule found.
- No named-staff comments on screen use during games found, beyond the policy reporting above.

## 3. Information designs coaches read (text vs graphics, heat maps, color)

### Takeaway
Sparse baseball-specific evidence. General research suggests graphics help find critical items while text helps extract exact values or actions, and that experts sometimes decide better from short expert-written text than from standard charts. This is from other domains and is a transferable hypothesis, not baseball evidence.

### Cited Findings
- In clinical studies, staff chose significantly more appropriate actions after reading expert-written textual summaries than standard time-series graphs (tier A, secondary summary; study date not confirmed) — [BPS Research Digest](https://bps.org.uk/research-digest/hospital-staff-make-better-decisions-using-textual-information-rather-medical)
- Visualization makes critical information easier to identify, while once identified it is easier to extract from text; users do not integrate well across the two when shown together (tier A, secondary summary; the underlying paper was not identified) — search result for "text vs graphics expert decision making"; underlying source not confirmed.
- A study on decision-statement depiction found graphics can suit non-programmers better than programmers, who have experience with text notation (tier A, secondary) — [Miami University repository](https://sc.lib.miamioh.edu/items/e0f5913a-feb1-4407-85ca-d10f324dc6fb)
- Spray charts and matchup views are the standard dugout iPad content (tier C/B) — [MLB.com, 2016](https://www.mlb.com/news/mlb-apple-bring-ipad-pro-into-dugout-c169682940)

### Inferences
- A one-page plan could pair a short plain-language sentence per hitter (the action) with one small zone graphic (the pattern), rather than a dense chart alone.
- Heat-map color and zone-diagram conventions: I found no citable baseball source; do not assert a convention.

### Gaps
- No evidence found on scouting-card or one-page-plan formats actually used by pro hitting staff.
- No baseball-specific heat-map color convention research found.
- Underlying peer-reviewed papers for the text-vs-graphics claims were not read directly.

## 4. Handoff to the player (language, hitter-facing apps, clips)

### Takeaway
Practitioner commentary stresses translation and simplicity: keep data introduction simple so as not to slow player buy-in, and make the coach the translator. Little public evidence on hitter-facing apps or clips specifically.

### Cited Findings
- "The most important job of hitting instructors is translation"—packaging the science into language and drills players can use (tier D, instruction-business opinion) — [The Hitting Vault](https://thehittingvault.com/?p=5700)
- Overwhelming athletes with too much data too early slows buy-in; players need not understand every metric on day one (tier C, Rapsodo vendor blog) — [Rapsodo playbook](https://rapsodo.com/blogs/baseball/the-ultimate-rapsodo-playbook-for-coaches-build-better-players-smarter-sessions-and-stronger-recruiting-profiles)
- Analysts and players often "speak two different languages"; teams look for coaches who translate data into each player's terms and have tried liaison roles and a traveling quant analyst (tier B/D, secondary summary; includes Mike Elias, Sam Fuld material) — [MASN: Elias on getting data to players](https://masnsports.com/blog/mike-elias-on-getting-data-and-analytics-to-the-players); [Eric Cressey podcast with Sam Fuld](https://ericcressey.com/csp-elite-baseball-development-podcast-using-data-for-development-with-sam-fuld); [MIT Sloan, 2018](https://news.mit.edu/2018/mit-sloan-sports-analytics-conference-explores-data-share-0226)

### Inferences
- Plan wording should be the coach's own words, one action per hitter; the tool should help the coach say it, not replace the verbal handoff.

### Gaps
- No named-coach account of hitter-facing apps or clip workflows retrieved; direct quotes from Elias and Fuld were not read (fetch blocked), so only the summary above is supported.

## 5. Input design and logging compliance

### Takeaway
No baseball-specific logging-compliance evidence found. The closest analogue (self-monitoring of diet) shows adherence declines over time and lower burden predicts sustained logging.

### Cited Findings
- Adherence to dietary self-monitoring consistently declines over time (systematic review, 22 studies) (tier A, secondary summary) — search result citing [PMC6856872](https://pmc.ncbi.nlm.nih.gov/articles/PMC6856872)
- At six months, smartphone users were adherent about 62% of the time versus 51% PDA and 34% paper diary (tier A, secondary news summary) — [Live Science](https://www.livescience.com/52730-tracking-diet-smartphones-methods.html)
- Ease of use predicts sustained monitoring; participants who found logging easier kept it up longer (tier A, secondary summary) — [PMC7593856](https://pmc.ncbi.nlm.nih.gov/articles/PMC7593856)

### Inferences
- Expect decay over a long season; design for minimum taps (defaults pre-filled from the plan, one-tap outcome), allow post-hoc capture in the postgame video session, and avoid mandatory fields.
- Voice capture: no evidence found either way.

### Gaps
- No evidence on in-dugout logging by baseball staff; diet-study results may not transfer to a few-second baseball decision log.

## 6. Documented reasons analytics tools are ignored

### Takeaway
Reported reasons are communication and usability: data solutions not easily usable by coaches and players, language mismatch, information overload.

### Cited Findings
- Front-office data solutions are not easily usable by coaches and players; front office and players often speak "two different languages" (tier D/B, secondary summary of MIT Sloan panel and features) — [MIT Sloan, 2018](https://news.mit.edu/2018/mit-sloan-sports-analytics-conference-explores-data-share-0226)
- Players have said front-office communication did not connect with what they felt should be done (tier B, news feature, secondary) — [Inquirer, 2016](https://www.inquirer.com/philly/sports/phillies/20160426_Phillies_trying_to_balance_data_and_instincts.html); [SI on a Yankees player citing a clubhouse rift](https://www.si.com/mlb/yankees/news/ex-new-york-yankees-star-says-analytics-caused-rift-in-clubhouse)
- Too much data too early slows buy-in (tier C, Rapsodo, above).

### Inferences
- Adoption risk is highest if GamePlan adds work without removing any, or speaks in analyst vocabulary rather than the coach's.

### Gaps
- Pre-2019 sources dominate here; no 2019-2026 named-staff account of why a specific tool was dropped was retrieved.

## 7. Accessibility and glanceability for outdoor tablet use

### Takeaway
Generic standards exist; none are baseball-specific. Sunlight readability is a system problem, and gloves defeat some touch screens.

### Cited Findings
- Apple HIG recommends 44x44 pt touch targets; WCAG 2.2 AA requires 24x24 CSS px (or spacing), AAA 44x44; Material suggests 48 dp (tier A for WCAG, tier C/D for secondary summaries) — [Front-End Checklist, touch targets](https://frontendchecklist.io/rules/accessibility/touch-targets)
- Body text should meet a 4.5:1 contrast ratio for WCAG AA (tier A, secondary) — [Passiro mobile accessibility](https://passiro.com/web-accessibility/developers/mobile-accessibility)
- Sunlight readability depends on sun angle, glass reflection, content contrast, and heat, not brightness alone (tier C, vendor) — [Winmate](https://www.winmate.com/en/blog/blog64-sunlight-readable-rugged-tablet-technology-winmate-s101mt)
- Cold reduces screen brightness and touch sensitivity, especially with gloves; capacitive screens may not respond to gloved touch (tier C, vendor) — [E3 Displays](https://www.e3displays.com/reads/capacitive-vs.-resistive-technology-in-sunlight-readable-touch-screens)

### Inferences
- Use high-contrast, large-type, large-target layouts well above the minimums, avoid reliance on color alone, keep one-handed thumb-reachable controls; test on the actual iPad with a matte screen protector in sun.

### Gaps
- No ballpark-specific outdoor tablet usability study found.
