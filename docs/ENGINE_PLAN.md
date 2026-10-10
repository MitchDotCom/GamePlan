# Recognition engine: plan to take the pilot app to a working, verified system for 50 to 80+ hitters

Draft 2026-10-10. Plan only. Nothing in sections 5 to 12 is built yet except where it says so. Cost is not a constraint (owner's instruction), so choices favor reliability over price. Vendor limits below are from search summaries, not official pages, and must be checked before a commitment.

## 1. What "done" means

A hitter taps one link, once. After that, every time he opens the app it already knows who he is, shows him the playlist his coaches set for his level and his next opposing starter, he answers strike or ball and which pitch, and the answers reach the server under his name even if the phone was offline, restarted, updated, or lost. A coach opens a page and sees, for any hitter or the whole group, where he recognizes pitches and where he does not, how that is changing over the season, and how many answers each number rests on. Nothing in that chain can silently assign an answer to the wrong person, drop an answer, or show a number it cannot support.

Success is measured, not asserted: section 10 lists the tests that must pass before each stage ships.

## 2. Where the pilot app stands against that definition

| Need | Today | Gap |
|---|---|---|
| Know who he is | A free-text name box saved on the phone | Typos and case differences split one hitter into several; two hitters can share a name; nothing ties a name to a person; a home-screen install does not share Safari's storage, so the name can be lost |
| Right content per hitter | Queue by batting side only | No level, no team, no personal history, no daily dose, no assessment schedule |
| Upcoming starter | Chosen by hand with a pitcher id | Resolver exists (`next_starter.py`) and works; no schedule job, no confirm screen, no handling of "starter not listed yet" |
| Record answers | Phone stores answers; syncs to one Python process that appends a file | Single process on one machine, one shared token, no per-player login, no database, no reconciliation |
| Scoring | Training scored on the phone; assessment keys withheld and scored by the server | Works, but the key store is a file |
| Coach views | `recognition_profile.py` and `season_ledger.py` produce static pages from a CSV | Not served, no login, no per-coach scope, never run on real data |
| Pressure testing | 52 phone checks and 17 drawn-pitch checks on emulated browsers, plus unit tests | No load, soak, fault-injection, identity or real-device testing; nothing measures data loss |

The pilot proved the interaction works (the owner tested it on a phone). It did not prove the data path.

## 3. Verified constraints that shape the design

| Fact | Source | Consequence |
|---|---|---|
| A website cannot read an iPhone's identity. iOS gives web apps no device id, name or Apple id | platform design; no workaround found | "Knows who he is based on his iPhone" has to be a **one-time claim** that leaves a secret credential on the phone. There is no device lookup to rely on, and a native app does not change this |
| Home-screen web apps keep their own storage and their own 7-day inactivity timer; WebKit says it does not expect their data to be deleted, but a 2022 bug report shows a home-screen app losing a login cookie after 7 days of regular use. `navigator.storage.persist()` is reported to help but Apple does not document that it overrides the rule ([Apple forums](https://developer.apple.com/forums/thread/710157), [WebKit bug 237350](https://bugs.webkit.org/show_bug.cgi?id=237350), [Register on the 7-day rule](https://www.theregister.com/2020/03/26/apple_relax_were_not_totally/)) | The phone can lose its credential or its unsent answers. **The server is the system of record; the phone is a cache with an outbox**, and a lost credential must be recoverable by a coach in under a minute |
| iOS Safari has no Background Sync. Queued writes go out only when the app is open ([Apple forums](https://developer.apple.com/forums/thread/694805), [WebKit bug 201866](https://bugs.webkit.org/show_bug.cgi?id=201866)) | Answers can sit on a phone for days if nobody reopens the app | Flush the outbox on open, on becoming visible, on regaining signal and after every pitch; show an "N answers not sent" banner; add a coach alert for any hitter with unsent data older than a set age |
| Web Push works for installed home-screen apps on iOS 16.4 and later, needs a tap to grant permission, and some vendors report it stopping unexpectedly ([WebKit](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados)) | Usable for reminders, not for anything the system depends on | Reminders are a convenience. Nothing may rely on a push being delivered |
| The schedule lists a probable pitcher for MLB 192 of 192 team-games, Triple-A 163 of 182, Double-A 174 of 186, High-A 173 of 186, Single-A 144 of 186, Rookie 0 of 364 (week of 2025-07-22, tested directly). For Visalia in July 2025 the opponent's probable was listed for 12 of 24 games, apparently only when the opponent is the home team | Stats API test run 2026-10-10 | The resolver will return "not listed" for a large share of Single-A games and always for Rookie ball. **A staff confirmation step is a required part of the flow**, not an exception |
| Tracking data and video by level: MLB has both (broadcast clip only, home feed). Triple-A and Florida State League have tracking, no clips. Carolina and California League have no public tracking. No public low-home or pitcher-front video exists | earlier tests in this repo (`MILB_STRESS_TEST.md`, `RECOGNITION_LOOP.md`) | Content comes from interchangeable **source adapters** chosen per affiliate (section 6). For the California League the only sources are org TrackMan data and org video, which need approval |
| Row-level security and per-user claims are the supported way to restrict who reads which rows in Supabase ([RBAC guide](https://supabase.com/docs/guides/database/postgres/custom-claims-and-role-based-access-control-rbac)). Auth email limits, anonymous sign-in limits and Pro connection counts conflict between sources | search summaries | Use RLS. **Do not depend on email magic links** for hitters (hitters may not have org email on their phone, and email send limits are tight). Check current limits on the dashboard before building on any of them |
| k6 supports open-model (arrival-rate) tests with per-scenario thresholds, which measure tail latency more honestly than a fixed number of users | search summaries; confirm syntax in official docs | Basis for the load tests in section 10 |

## 4. Design rules

1. **Never guess who someone is.** An answer is accepted only with a credential that was issued to one hitter. No credential, no storage.
2. **The server is the source of truth.** The phone holds a cache and an outbox. Anything on a phone can vanish.
3. **Append-only.** Answers are never edited or deleted. A mistake is corrected by a new row that voids the old one, with a reason and an author.
4. **Idempotent everywhere.** The same answer sent twice, ten times, or out of order produces one row.
5. **Fail closed.** If a check cannot be satisfied (starter unconfirmed, clip fails a gate, identity unclear), the system shows nothing new and says why. It never substitutes a guess.
6. **Every number carries its n.** No leaderboard cell appears without its count and an interval.
7. **Rebuildable.** Every coach number can be recomputed from the raw answer log. A nightly job proves it.
8. **Versioned.** App version, content version, rule version and schema version travel with every answer.

## 5. Identity and assignment (the part that must not fail)

### 5.1 The problem stated precisely
Three separate questions: (a) who is this person in our records, (b) does this phone belong to him, (c) which of his records does today's answer belong to (his team, level, side he is batting). A mistake in any of them corrupts the data invisibly, which is worse than a crash.

### 5.2 Recommended design: roster-backed claim links
1. **Roster is the source of identity.** Staff import the roster (CSV: org player id, MLBAM id if known, name, team, level, bats L/R/S, throws, active). Every hitter is a `player` row with a permanent internal id. Names are display only and never used as keys.
2. **Each hitter gets a personal claim link and QR code** (a long random token, single use, expires in 7 days if unused). Texted or shown on a staff screen at the park.
3. **First open claims the account.** The token is exchanged for a **device credential** (a long random secret stored in the app's storage, only its hash on the server). The page asks him to confirm: "You are Jordan Smith, Visalia, bats left. Is that you?" with a photo if the org supplies one. Wrong person: tell a coach (never a self-service rename).
4. **Home-screen install gap.** Because an installed app does not share Safari's storage, the claim page shows a **6-digit pairing code** valid for 10 minutes. After adding to the Home Screen he opens the app and enters the code, which re-issues the credential inside the installed app. (Design from the start; verify on real phones.)
5. **Each credential belongs to one player and one device.** Up to 2 active credentials per player (phone and a backup). A coach can revoke any credential with one tap; revoked credentials are refused at the next sync and the app shows "ask a coach for a new link".
6. **Recovery:** credential lost or storage wiped: the app shows "Who are you?" with a roster picker limited to his team, and he must enter a **coach-issued 6-digit recovery code** (or the coach re-sends the claim link). Unsent answers on the old install are lost if the data is gone; this is why the outbox flushes constantly.
7. **Shared devices (clubhouse iPad):** a kiosk mode with roster picker plus a 4-digit personal PIN per hitter. Every session records the device id and the identification method, so coaches can filter kiosk data if they want.
8. **Every session starts by showing his name** in the header, and the first screen after a long gap asks "Still Jordan?" with a one-tap "Not me" that logs out. The name on screen is the name on the data.
9. **Each answer is stamped server-side** with player id, credential id, device label, the team and level assignment active on the answer date (not today's), app version, content version.

### 5.3 Cases to handle explicitly
| Case | Rule |
|---|---|
| Promotion, demotion, trade, release | Player id never changes. An **assignment** row (team, level, start date, end date) says where he is. Playlists follow the current assignment; history stays with the player and carries its level tag, so the ledger can show "at Single-A" and "at Double-A" separately |
| Switch hitter | Both sides get playlists; each answer records the side he faced. Leaderboards split by side |
| Same name, different players | Impossible to confuse: links and ids carry identity, names do not |
| Hitter not on the roster yet (signing, tryout) | Staff create a provisional player; merge later with a logged merge that moves answers to the real id |
| Two phones, one hitter | Allowed up to 2 credentials; answers merge by player id; device label kept |
| One phone, two hitters (brother, teammate borrowing) | A credential is single-player; second person must claim their own account (a "switch user" path requires that person's recovery code or PIN) |
| Credential leaked (link forwarded) | Claim links are single-use and expire; a second claim attempt alerts staff and does not bind |
| Clock wrong on the phone | Server receive time is the record; device time is kept as a separate field; answers more than 24 hours "from the future" or the past are flagged, not discarded |
| Offline claim | Claim requires signal once. Everything after works offline |
| Org wants SSO | The design keeps identity separate from the credential, so SSO can replace the link later. Ask IT early (section 13) |

### 5.4 What can go wrong and how it is caught
A daily **identity audit** lists: credentials unused for 14 days, hitters with answers from 2 or more credentials, answers whose assignment date has no active assignment, claim attempts that failed, and any hitter with zero answers in an active week. A coach sees these as a short "attention" list.

## 6. Surfacing the right pitches (level, team, starter, hitter)

### 6.1 Inputs per hitter
Team and level (assignment), side(s) he bats, the opposing starter for the team's next game, his own history (weak pockets and pitch types from the ledger), what he has already seen (no pitch repeats), the coach's dosage setting, and the assessment calendar.

### 6.2 Source adapters (per affiliate, chosen by what exists)
| Adapter | Gives | Works for | Needs |
|---|---|---|---|
| mlb_video | Broadcast clips with tracking keys | MLB opponents | nothing new (built) |
| tracking_drawn | Pitches drawn from tracking (hitter's eye or low behind home) | Any game with tracking: Triple-A, Florida State League, MLB | built; perceptual value untested |
| org_trackman | Pitches from the org's TrackMan export, drawn or with org video | Any affiliate whose TrackMan data the org shares | adapter exists for the data (`trackman.py`); **org approval and the file feed** |
| org_lowhome | Low-home video with TrackMan join | Visalia | **org approval**; clip join and held-out release test not yet done |

A **capability matrix** (affiliate by adapter, with the date each was last verified) decides what each level shows. If a level has no adapter for an opponent's pitcher (California League opponents have no public tracking), the engine says "no pitches available for this starter" and falls back to the team's own org data or a generic arsenal pack, labeled as such.

### 6.3 The starter, confirmed by a person
1. A nightly job asks the schedule for each affiliate's next game and the opponent's probable pitcher (resolver built). Result: confirmed, tbd, or no game.
2. **tbd is common** (23 percent of Single-A team-games, and half of Visalia's in the July sample), so staff get a **confirm screen**: the suggested starter or an empty slot, with a search box; they enter or confirm the starter once. Confirmation is stamped with who and when.
3. The prep pipeline (built, with its gates) runs only on a confirmed starter. The game-day recheck re-resolves and flags a change.
4. If the starter changes after packs are built, the old playlist stays visible as "previous starter" and the new one appears when ready; nothing is deleted.

### 6.4 The hitter's playlist (composition rules to be tuned in a pilot)
Per day a hitter sees a **session** built from: the next-starter pack for his side(s), the Edges pack (hard strike or ball calls), a personal **review** block drawn from his weakest pockets and pitch types (only once he has enough answers to name a weakness; otherwise skipped), and, on schedule, an **assessment** (fixed forms, no feedback, same pitches for everyone at that level so scores compare). Rules: no pitch repeats for a hitter within a form; training and assessment pitches never overlap (enforced and gated); a daily cap set by the coach; the pause point and view (hitter's eye or low home) set per level by the coach, not by the player. Starting values for the pause offsets and dose are guesses until the pilot; the engine logs them with every answer so they can be analysed.

### 6.5 Content as immutable versions
A pack is built once, hashed, and published as `pack@hash`. Phones download by hash; answers cite the hash. If a pack is rebuilt, it gets a new hash; old answers still point at the exact content shown. Clips are cached on a CDN; the same clip serves the whole team. Measured size on the pilot: about 8.5 MB for 76 clips (roughly 110 KB each), so a hitter's daily set is a few megabytes.

### 6.6 If the pipeline fails
Hitters see the last good playlist with a banner ("Starter not confirmed yet, showing last series"), staff get an alert listing the failed gate. A failed build never replaces a good one.

## 7. Recording: sustainable, assigned to the right person

### 7.1 The data model (Postgres)
`orgs`, `teams` (level, mlb team id), `players` (id, org id, mlbam id, name, bats, throws, active), `assignments` (player, team, level, start, end), `credentials` (player, hash, device label, created, revoked), `claim_tokens`, `staff` and `staff_scopes` (which teams a coach can see), `starters` (team, game, pitcher, source, confirmed by, confirmed at), `packs` (id, hash, source adapter, camera type, starter, level, built at, gate report), `items` (pack, pitch tracking facts, clip path or drawn parameters, public metadata), `item_keys` (answer keys; no player-facing access), `playlists` (player, date, ordered pack list, rule version), `sessions` (player, credential, device, app version), `answers` (below), `voids`, `audit_log`.

`answers` (append-only): id (client uuid), player, credential, session, pack hash, item, task (zone or pitch), call, options shown, decision time, pause used, camera type, view, mode (train or assess), key (assessment filled by the server after submit), correct, device time, server time, app version, content version, assignment (team, level) at that time.

### 7.2 The sync path
Client: write each answer to local storage, then send; keep it in the outbox until the server returns its id. Server: accept only with a valid credential; insert on conflict do nothing (idempotent on answer id); score assessment rows from `item_keys`; return the stored ids. Client marks sent only on that response. A **reconciliation** job compares counts per player per day between what phones report in a periodic heartbeat (answers stored, answers sent) and what the server has; any gap raises a coach alert and an engineer alert.

### 7.3 Corrections and retention
Void instead of delete (`voids` with reason, author, time). Nothing is ever rewritten. Nightly database export to storage the org controls; restore drill each quarter (section 10). Data export per player and per team on request.

### 7.4 Consent and visibility
Hitters see their own numbers first. Who else sees them, and the consent wording, are decisions to take with the org before launch (section 13). The design supports a named staff group per team via row-level security.

## 8. What coaches see

### 8.1 Views
- **Hitter page:** a 3 by 3 pocket map (as the batter sees it) of strike-or-ball accuracy, a second map for edge pitches, pitch-type recall and what he named instead, decision time, and a monthly trend, each cell with its n and interval; weak cells are listed as places to look at on video, not as findings.
- **Team board and level board:** ranked by assessment answers only, one board per camera type (broadcast, hitter's eye, low home), 30 scored answers to be ranked, tier against the group (above, below, not distinguishable), accuracy versus peers on the same pitches.
- **Attention list:** hitters who have not done a session, unsent data, failed claims, pending starter confirmations.
- **Compare:** a hitter against himself across time and across levels.

### 8.2 Rules that keep the numbers honest (built in `season_ledger.py`, to be carried over)
Assessment-only ranking; never pool across camera types; minimum n; Wilson intervals; peer-adjusted accuracy; no cell shown below the minimum count. These are tested with planted skill and planted traps.

### 8.3 How the numbers are produced
Derived tables are rebuilt from the raw `answers` log by a deterministic job, run nightly and on demand. A test rebuilds from scratch and compares with the live tables; they must be identical.

### 8.4 Access (row-level security)
Player: own rows only. Coach: players on the teams in his scope. Admin: everything and the audit log. Keys are never selectable by a player. This is enforced in the database, not the page, and is tested with an attacker script (section 10).

## 9. Architecture

```
Phone (installed web app: outbox, cached packs)
   | HTTPS
   +--> static host (app files)               +--> CDN (clips, drawn-pitch json by pack hash)
   +--> API (small server functions): claim, sync, playlist, confirm-starter, coach reads
          |
          +--> Postgres (RLS): players, assignments, answers, packs, ledgers, audit
Content side (scheduled jobs, run as code, gated):
   schedule -> resolver -> [staff confirm] -> source adapter -> prepare + gates -> publish pack@hash
Analytics: nightly deterministic rebuild of ledger tables from `answers`
Monitoring: error log, sync heartbeat, reconciliation, alerts (coach list and engineer list)
```

**Stack recommendation.** Keep the architecture already planned (`ARCHITECTURE_PLAN.md`): static host plus managed Postgres with row-level security and small server functions. Reasons: standard SQL the org's BI tools can read, row-level security matches the access rules, and the pieces move to org-run infrastructure without a rewrite. Alternatives: org-hosted cloud (best on approvals, unknown to me, slowest to start); all-in-one platform (fewer vendors, harder to leave).

**Native wrapper decision gate.** A native shell would give reliable local storage (no eviction), background upload, and more dependable push. It would not give device identity (iOS does not hand apps a reliable person-level id, so the claim step stays). Decide at the end of phase 4 from real-device results: if credentials or unsent answers are lost on real phones more than a set rate, wrap it. Requires an Apple developer account and a release path.

## 10. Pressure testing (installed from phase 1, run on every release)

Principle: every guarantee in sections 4 to 8 gets a test that tries to break it. A release does not ship if any gate below fails.

### 10.1 Test layers
| Layer | What it proves | Tool and method | Gate |
|---|---|---|---|
| Unit and property tests | scoring, ledger maths, gates, sim geometry | existing pytest; add property tests (random answers, any order, any duplication gives the same ledger) | all pass |
| Identity tests | right person, always | scripted: claim, double claim, expired token, revoked credential, two devices, forged credential, wrong-hitter recovery code, promotion mid-week, name collision | zero answers stored under the wrong player; zero accepted without a credential |
| Sync fault injection | no loss, no duplicates | browser tests on Chromium and WebKit: go offline mid-answer, kill the page, kill the server mid-request, drop the response after the server stored the row, replay the outbox twice, reorder, reload during sync, 5000-answer backlog | server rows equal client answers exactly; duplicates 0; loss 0 |
| Storage loss | recovery path works | wipe the phone storage between sessions; recover with a coach code; confirm unsent answers are the only loss and the banner warned | recovery under 60 seconds with no coach tools beyond the roster page |
| Load | 80 hitters at once | k6 open-model: all hitters finish a session and sync within 5 minutes (80 x 80 answers = 6,400 rows, about 20 per second sustained, a few hundred per second for a burst); then 10 times that | p95 sync under 1 s, error rate under 0.1 percent, 0 lost rows |
| Soak | nothing degrades | 8 to 24 hours at expected load with periodic restarts and a database failover test | flat latency, no connection exhaustion, no memory growth |
| Content pipeline fuzz | bad input cannot reach a hitter | feed the prep pipeline missing fields, wrong coordinates, repeated pitches, one-pitch-type pitchers, corrupt clips, schedule changes mid-build | every bad case ends in a named gate failure; a good pack is never replaced by a failed build |
| Security | hitters cannot read each other | attacker script against the API and database: read others' rows, read keys, forge ids, SQL and script injection in names, CSV injection in exports, brute-force a claim token, oversized bodies | 0 successful cross-player reads; keys unreachable; injection neutralized (already tested for names and CSV) |
| Data integrity | the numbers are what the log says | nightly: rebuild ledgers from raw, compare with live, compare phone heartbeats with server counts | identical; any gap alerts |
| Real-device matrix | the thing works on the phones in use | real iPhones, not emulators: oldest iOS in use, newest, a small-screen model, low-power mode, poor signal, a weekend of no opening, an iOS update in the middle of a season, app added to the Home Screen versus in Safari; use a device cloud plus 4 to 6 phones kept for testing | every item in the checklist passes on every device in the matrix |
| Usability under pressure | players can use it | 10 hitters, 2 weeks, observe: can each one start unaided; where does he stall | 10 of 10 start unaided; first-pitch time measured |
| Disaster recovery | the data survives | restore last night's export into a clean environment; compare row counts and a sample of players | restore under 1 hour, 0 rows missing |
| Observability | problems surface before a coach finds them | alerts on: sync failure rate, hitters with unsent data over 24 hours, pipeline gate failures, claim failures, p95 latency | alert fires in a staged failure test |

### 10.2 What can be built and run now, without accounts
Property tests and fault-injection tests against the existing Python server and the phone app; a k6 load test against a local server; the identity design as a prototype in the local server; the reconciliation and ledger-rebuild jobs; the content-pipeline fuzz tests. These do not need any outside service and they harden the design before money or approval is spent.

### 10.3 Known measurement gaps to close with the real-device work
Whether credentials and IndexedDB survive a week with no opening on current iOS; whether `persist()` is granted; touch and screen timing noise (assume 20 to 40 ms until measured); battery and heat over a 15-minute session; video start time on cellular.

## 11. Capacity (to size, then verify)

| Quantity | Estimate | Basis |
|---|---|---|
| Hitters | 80 now, design for 400 | owner's range |
| Answers per hitter per day | about 80 (40 pitches, 2 questions) | assumption; set by coaches |
| Answers per season | about 1.2 million (80 hitters x 80 x 6 days x 30 weeks) | arithmetic |
| Storage | a few hundred MB for the answer log | about 300 bytes per row |
| Peak write rate | 6,400 rows in a few minutes | everyone syncing after a session |
| Video per playlist | a few MB | about 110 KB per clip measured on the pilot |
| Distinct content sets | one per affiliate per starter | same starter serves every hitter on the team |

None of this is large. The risk is not volume; it is identity, loss and silent error, which is why the test layers above weight them most.

## 12. Phases, with exit criteria

Opening Day 2027 is about 25 weeks away. Durations are my estimates and depend on the decisions in section 13.

| Phase | Weeks | What | Exit gate |
|---|---|---|---|
| 0. Decisions and accounts | 1 to 2 | Section 13 answered; accounts created; org approval path started in parallel | Decisions recorded in the repo |
| 1. Identity and record keeping | 2 to 8 | Postgres schema and security rules; roster import; claim links, pairing code, credentials, revoke and recovery; sync with outbox, idempotency and server scoring; reconciliation; the identity, sync-fault, security and storage-loss test layers | All of those layers green on Chromium, WebKit and 3 real iPhones; zero wrong-player rows in 10,000 fuzzed answers |
| 2. Content engine as a service | 8 to 13 | Capability matrix; nightly resolver; staff confirm screen; adapters (mlb_video, tracking_drawn first); immutable packs; per-hitter playlist generator; failure fallback; pipeline fuzz tests | A new starter confirmed by staff reaches every paired phone with no manual step; every bad-input case ends in a named failure |
| 3. Coach views | 11 to 16 | Served hitter page, pocket maps, team and level boards, attention list, scope-limited access; ledger rebuild test; export | A coach opens a hitter and sees his map with n and intervals; attacker script cannot read another team |
| 4. Pressure and real-device program | 14 to 20 | Load, soak, disaster recovery drill, full device matrix, 10-hitter usability trial | Every section 10 gate passes; native-wrapper decision recorded |
| 5. Pilot hardening | 20 to 25 | Staggered start per the pilot protocol, daily reconciliation reviewed by a human, monitoring live | 2 clean weeks with 0 unreconciled answers; coaches use the views |
| 6. Org data (after approval) | parallel | org_trackman and org_lowhome adapters, Visalia | Held-out acceptance test for low-home release detection (30 or more labeled clips, two labelers) |

## 13. Decisions and unknowns

Needed from the owner:
1. **Stack for the engine**: the planned static host plus managed Postgres, or org-hosted, or all-in-one. (Recommendation: the planned stack, built so it can move.)
2. **Org approval**: is a third-party service acceptable for MLB-only content while approval for any Visalia or TrackMan data is sought?
3. **Identity method**: claim link plus pairing code (recommended) versus org SSO if IT offers it; are hitters on org-issued phones or personal phones; is a roster export with player ids available?
4. **Who sees what**: admin, coaches per team, whether hitters see their rank or only their own numbers; consent wording; retention period.
5. **Levels in scope** for the pilot (Visalia only, or the whole system) and the weekly cadence.
6. **Staff roles**: who confirms the starter each day; who handles recovery requests.
7. **Native app**: whether the org already has an Apple developer account.

Unknowns I cannot resolve from here: the org's IT and device policy; whether the California League parks share TrackMan data across clubs (decides whether any opponent's pitcher can be drawn at Single-A); the real iOS behavior of storage and credentials over a week; whether drawn pitches or broadcast clips train recognition at all (no evidence yet); the right pause and dose settings (guesses until the pilot); whether recognition on this test relates to game performance (untested).

## 14. What changes in the repository first

If the plan is approved, the first work needs no accounts: (a) the identity prototype in `app_server.py` (roster import, claim and recovery codes, per-player credentials, answers refused without one); (b) an outbox rewrite on the phone (flush on open and on becoming visible, retries with backoff, unsent banner, heartbeat); (c) fault-injection and property tests for both; (d) a k6 load script; (e) the reconciliation and ledger-rebuild jobs. These are the layers that decide whether the data can be trusted, and they are the same code that moves to the hosted stack.
