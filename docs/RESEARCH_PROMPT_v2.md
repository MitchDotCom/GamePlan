# Deep research prompt v2: capturing intent and measuring success in a hitting decision tool

Paste this to a research agent or run it through the deep-research skill. Written 2026-10-04. Scope questions at the end are open; answers change which parts run first.

---

## Role and goal

You are researching how a baseball hitting-development tool should capture a coach's intent and measure whether the tool is working, using what baseball and other sports have already learned. The output feeds design decisions for a real tool, so prefer concrete, checkable findings over general advice.

## The product (so you can judge relevance)

GamePlan is a laptop and tablet tool for minor-league hitting coaches and staff (first target: Single-A, California League). For a lineup against a specific starter it shows, per hitter and count, where to swing and where to take, 1 to 3 distinguishable approach paths (a confident "value" plan, a contact-first plan, a "decide every pitch" plan), and reviews each pitch afterwards against the plan. The mission is to develop hitters first and win second. Hitters only, starters only. Public MLB and minor-league data first; TrackMan and Hawk-Eye data later. The coach picks a path or overrides; the choice is logged.

What exists: a swing-versus-take value model validated on 2025 MLB data, a plate-appearance value calculation, a path generator, a game library with per-game pages, a skip control for non-representative at-bats, a decision log, and a post-game review that labels each pitch (followed plan, hitter beat model, deviation cost, umpire miss, plan silent).

What the team found missing (from a code review): the coach's choice is saved but nothing downstream uses it; success is measured as agreement with the model, not as development; coaches cannot state intent in their own words; and nothing tracks a hitter across games.

## Core questions, in priority order

### 1. Capturing intent
1. How do hitting coaches and front offices describe and record a hitter's approach for a game or an at-bat today? Find real examples: advance-scouting packets, hitter one-pagers, pregame meeting formats, dugout cards, notes apps, Hudl or Sportscode tags, TrackMan or Rapsodo or Blast reports. What fields do they actually fill in?
2. What vocabularies exist for "approach" (for example hunt a zone or pitch, work the count, take until strike, two-strike approach, situational approach)? Which are used consistently across clubs and which are idiosyncratic? Is there published research or practitioner material that tries to standardize them?
3. How do other sports capture a coach's intended play and then compare it with execution? Cover at least: American football (play call versus assignment grading, charting services), basketball (play types, Second Spectrum-style tagging), soccer (tactical instructions, possession-value models), tennis (match charting and serve-plus-one patterns), cricket (batting approach by bowler type), golf (course-management and strokes-gained decision analysis), and pitch calling in baseball (game plans, PitchCom, catcher game-plan sheets).
4. What are the proven low-friction capture methods for busy coaches (default selections, taps over typing, voice, templates, capture after the fact)? What happens to logging compliance over a season in comparable tools?
5. How is intent separated from outcome so that a good decision with a bad result is not graded as a failure? Look at poker, chess, forecasting and sports analytics literature on decision quality versus results.

### 2. Measuring success
1. What process metrics for hitters have published evidence of reliability and predictive value (swing decisions, chase, zone contact, swing-take run value, decision-quality scores)? Give reliability numbers (split-half, year over year) and sample sizes needed. Include what is publicly documented for Statcast swing/take and plate-discipline measures, and what other published decision metrics exist. Flag anything you cannot verify.
2. What does credible evidence look like that a decision-support tool changed behavior and then outcomes in a player-development setting? Search for published or well-documented examples in baseball and other sports of tools evaluated for adoption, behavior change, and results. Include failures and abandoned tools.
3. How should a small-sample setting (a Single-A hitter has a few hundred plate appearances per season) evaluate change: single-case designs, stepped rollout, Bayesian hierarchical tracking, control charts? What is the minimum detectable change for common process metrics at that sample size?
4. Which adoption metrics matter (coach opens the tool, picks a path, overrides, returns, shares with a hitter)? What predicts that a coach keeps using a tool after the first month?
5. How is trust calibrated? Find evidence on how experts respond to model recommendations, algorithm aversion, overreliance, and showing uncertainty (for example whether showing a confidence range helps or hurts).

### 3. Making it usable for coaches and hitting staff
1. Time and device reality in minor-league ball: when do coaches look at information (pregame meeting, between innings, postgame video session), on what device, with how much time? Find first-hand accounts, team-staff interviews, conference talks and job descriptions.
2. Information design for rapid expert decisions: examples of effective one-page hitter plans, scouting cards, and heat-map conventions that coaches actually read. What is the evidence on text versus graphics for this audience?
3. How do successful tools handle the coach-to-player handoff (what the hitter sees, in what words)? Include hitter-facing apps and language coaches use.
4. What causes analytics tools to be ignored by staff? Gather documented cases (for example mismatches in vocabulary, extra work, distrust, bad timing).

### 4. Data and rules constraints (verify before building)
1. Is automated ball-strike calling used in the California League or in any Single-A league in 2025 or 2026? Which levels and parks use it, and since when? This changes the called-strike model.
2. Which Single-A parks have TrackMan, Hawk-Eye, or neither, and which fields (bat tracking, release, approach angle) are available? What is public through MLB's minor-league Statcast data?
3. What are the rules and norms on sharing player data and analysis tools inside a club, and on personal projects using public data?

## Method requirements

- Use only public, citable sources: peer-reviewed papers, conference papers (MIT Sloan, SABR, Saberseminar, Cloud Computing and sports analytics venues), practitioner and club-staff writing, vendor documentation, podcasts and talks with named speakers. Do not use or reproduce any restricted-license code or data. Only methods that are openly licensed or published may be proposed for re-implementation.
- Label every claim with an evidence tier: A peer-reviewed or primary data, B documented practitioner account with named source, C vendor or marketing, D opinion. Give the URL and date for each source. State when a claim could not be verified.
- Prefer 2022 to 2026 for tooling and rules; use older sources for method and theory.
- Search for disconfirming evidence on each major recommendation.
- Do not infer anything about any specific club's internal systems that is not public.

## Deliverable

A report with these sections:
1. **Intent capture**: the three or four patterns that work, what fields coaches will fill in, a recommended minimal log schema (field names, types, defaults), and what to avoid.
2. **Success measurement**: a recommended metric set in three layers (adoption, behavior or process, outcome), each with reliability, minimum sample, and how to display it to a coach. Include what not to claim.
3. **Analog table**: for each other sport and tool studied, what problem it solved, what the equivalent of "intent" and "success" was, and what transfers to baseball hitting. One line each, sorted by transferability.
4. **Usability findings**: ranked list of design rules with sources, plus documented reasons tools fail.
5. **Constraint checks**: answers to section 4 with sources.
6. **Implications for GamePlan**: specific changes to the log, the review labels, the path picker, and the evaluation plan; what to build first; what to drop. Mark each as supported, plausible, or speculative.
7. **Open questions** that only coaches can answer, written as questions for a coach interview of 20 minutes.

Length: thorough but scannable. Tables where items are parallel, short prose elsewhere.

## Scope questions to settle before running (answers change the order)

1. Is the tool judged mainly by hitter development, by coach adoption, or by wins in the first season?
2. Where will it be used most: a pregame meeting on a laptop, the dugout on a tablet, or a postgame video session?
3. Does Visalia currently write down an approach for each hitter before a series, and in what form?
4. Is automated ball-strike calling used in the California League? (If you know, it settles section 4.1.)
