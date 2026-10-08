# Go / No-Go: plug-and-play architecture plan

Draft 2026-10-08. Plan only; nothing here is built or deployed. Vendor limits and prices are from memory and must be checked before committing.

## 1. What "plug and play" has to mean

A player taps a link in a text message. It opens, he picks his name, adds it to his home screen, and from then on it opens like an app, works in the dugout with no signal, has tomorrow's starter waiting, and his answers reach the staff without him doing anything. Nobody installs Python, runs a server, or exports a file. Updating the app or the content is a push to the repo or one command, never a visit to 40 phones.

That needs four things the prototype lacks: a public HTTPS host, a place for clips, a place for answers, and a way to know who is who.

## 2. Constraints that shape the design

| Constraint | Consequence |
|---|---|
| Players use iPhones | The web engine is WebKit. Chrome on iPhone is also WebKit. WebKit already broke our clip storage once. Real-device and WebKit testing are part of every release |
| The owner is not a full-time engineer | Managed services, few moving parts, everything reproducible from the repo, no server to patch |
| Visalia footage and TrackMan data are org property | Private storage, short-lived links, nothing public, org approval before any org data is used. The pilot can start on public MLB clips and be approved in parallel |
| MLB broadcast clips are MLB's | Same private handling; check the terms of use with the org before relying on them beyond internal tests |
| Roughly 30 to 60 players per affiliate, later maybe an organization | Tiny scale. Free or low tiers are likely enough; do not over-build |
| Player performance data is sensitive | Players see their own results; staff see the team; consent and who-can-see-what are designed in, not added later |
| The Artifact sandbox forbids service workers and install | It stays what it is now: a private demo link, not the product |

## 3. Options considered

| Option | What it is | For | Against |
|---|---|---|---|
| **A. Static app + managed backend (recommended for the pilot)** | The app as static files on a CDN host (Cloudflare Pages or similar), Supabase (Postgres, auth, private file storage, small server functions) | Everything is standard: SQL you can query from Power BI or Tableau, a dashboard you can read like a spreadsheet, row-level security so a player only ever sees his own rows, private clips with expiring links, auto-deploy from GitHub | Two vendors. A third-party service holds org data, so it needs approval |
| B. One-vendor Firebase | Hosting, Auth, Firestore, Storage from Google | One vendor, strong PWA tooling | Document database is awkward to analyze; leaving later is harder |
| C. Cloudflare only | Pages, R2 for clips, Workers, D1 | Cheapest, one vendor, no egress fees on clips | Auth and per-player rules are code we would write and test ourselves |
| D. The organization's own cloud | Whatever IT already runs (Azure, AWS, an internal app platform) | Clean on approvals and data residency | Unknown to me; slowest to start; I cannot see it from here |
| E. Native iOS app (TestFlight, later App Store) | Wrap the web app, for example with Capacitor | Better video, storage that is not evicted, push notifications | Apple developer account, builds, review, two release paths. Not needed to start |

Recommendation: **A for the pilot, built so it can move to D without a rewrite** (static files, standard Postgres, object storage, a few small functions). Revisit E only if the web app hits a hard limit on real phones.

## 4. Target architecture (option A)

```
Player's iPhone (installed web app, offline cache)
   |  HTTPS
   +--> Static host: app shell, fonts, icons      (auto-deployed from GitHub on every push)
   +--> Supabase Auth: pairing, session
   +--> Supabase Storage (private): clips, frames  (signed links that expire)
   +--> Supabase Postgres: players, packs, items, queue, answers
   +--> Edge functions: get_queue, submit_answers, score_assessment

Content side
   Public MLB: scheduled job (GitHub Actions cron) -> build packs -> upload -> register
   Visalia:    a small uploader run on a staff machine (TrackMan CSV + low-home clips) -> same upload and register
Staff side
   Dashboard (read-only to start): per-player recognition profile, team summary, session log
```

### Data model
- `players`: id, name, team, bats (L, R, S), pairing code, active.
- `packs`: id, kind (starter, random, assessment), title, mode (training, assessment), source (mlb, visalia), created, expires.
- `items`: id, pack, clip path, frame path, release time, pause offsets available, public metadata (type, location, speed and so on). Answer keys for assessment items live in a private table that no player query can read.
- `queue`: player, pack, order, available from. The "next starter" pack is whichever pack the staff, or the schedule automation, marks next for that side.
- `answers`: id, player, item, task, call, time, session, device, app version. Correctness for training is computed by a function, for assessment only after the window closes.
- Row-level rules: a player reads and writes only his own answers and reads only his own queue; staff read everything; keys are never selectable by a player.

### Plug-and-play access (no passwords)
1. Staff create the roster once. Each player gets his own link (`https://.../?k=<long random token>`), texted or shown as a QR.
2. Tapping it opens the app in Safari and signs him in.
3. **iPhone gotcha:** an app added to the home screen does not share Safari's stored data, so the token is not there. The first screen after install asks for a short pairing code that Safari showed before install. Designed in from the start; verify on a real phone.
4. Tokens can be revoked per player. A lost phone is one click.

### Content and queue automation
- **Next starter:** for MLB, the starter and his recent starts are already automated (`app_content`). For Visalia, staff enter or import the opponent's probable starter, because public schedules for the California League carry no tracking.
- **Random packs:** drawn from the opposing team's other pitchers in the pooled games, as now.
- **Assessment packs:** fixed forms A and B, balanced, built once per cycle, scored on the server after the window.
- A content build is idempotent: the same inputs produce the same pack id, so reruns replace, never duplicate.

### Releases and safety nets
- Every push runs the QA matrix on Chromium **and WebKit**, then deploys to a staging URL. Production is a deliberate promotion.
- The app shows an "update ready" banner; iPhone home-screen apps cache stubbornly and a stuck old version is a known failure.
- A small client log (errors, clip-load failures, sync failures, device and iOS version) is sent with answers, so problems on phones are visible without the player explaining them.
- Nightly database export to storage the org controls.
- Versioned queue schema, so an old installed app degrades to "update needed" instead of breaking.

### Rough cost (verify current pricing)
Free tiers probably cover a 40-player pilot: a few GB of clips, a small database, modest bandwidth. Plan for roughly $25 to $50 a month once it is in daily use and backups matter. Clip bandwidth is the thing to watch: about 1 MB per clip, downloaded once per phone and cached.

## 5. Video: how it should work on a phone

The prototype plays a clip and pauses it in code at release plus an offset. That depends on the phone's video decoder landing on exactly the right frame, and iPhones are the least predictable. Better:

1. **Cut the clip into two files at build time**: a lead-in that ends exactly at the chosen pause frame, and the rest. Also save the pause frame as a still image.
2. The phone plays the lead-in, shows the final frame as the still while the questions are open (so it cannot drift), then plays the rest. No timing code decides where the pause lands, so it is identical on every device.
3. Offsets (50, 100, 150 ms) become separate lead-in files per pack, chosen by the coach, not a player setting.
4. Encode for phones: H.264, constant frame rate, muted, about 540 to 720 px, keyframe at the first frame, `faststart`. Target well under 1 MB a clip. Visalia's 1080p, 60 fps source is the heavy case.
5. Download in the background on Wi-Fi, show what is ready, delete watched clips first when storage runs low.
6. Presentation (next phase, with real phones): portrait with the video full width, a landscape full-screen mode with thumb-reach buttons, how the result card and strike-zone drawing sit around the video, and whether a still of the pitch tracking is worth showing.

Timing accuracy of the answer itself (tap to decision time) needs measuring on real hardware; a screen refresh is about 8 to 17 ms and touch latency adds to it. Assume 20 to 40 ms of noise until measured.

## 6. Phases

| Phase | What | Who | Done when |
|---|---|---|---|
| 0. Decisions and accounts | Pick the stack, create the accounts, connect the repo to the host, put two keys in the repo's secrets | You, about an hour, with a checklist from me | I can deploy without asking you for anything else |
| 1. Foundation | Repo layout, database and rules, pairing and sign-in, install, offline, staging and production, QA gate in the pipeline | Me | A paired iPhone installs the app, answers a clip offline, and the answer shows in the database |
| 2. Content and queue service | Packs uploaded to private storage, queue per player, next-starter automation for MLB, signed links | Me | A new MLB starter appears on every paired phone without anyone touching a phone |
| 3. Video v2 | Two-file clips, still frame, encoding ladder, background download | Me, tested on your phone | Pause frame identical on every device; clips under budget |
| 4. Mobile look and feel | Portrait and landscape, video presentation, result card, thumb reach, loading and error states | Together, on real phones | You would hand it to a hitter |
| 5. Staff view | Recognition profiles and team summary from the database (read-only first), usable from Power BI or a plain page | Me | A coach can open a hitter and see the map |
| 6. Visalia content | TrackMan import, low-home clips through the uploader, clip join | Me, after approval | A Visalia starter pack built from real files |
| 7. Pilot | Staggered start per the V8 protocol | Org | Approval and hitters |

Phases 1 to 4 need no org data. They run on public MLB clips and give the org something real to approve.

## 7. Decisions I need from you

1. **Stack for the pilot:** A (Cloudflare Pages + Supabase) as recommended, or a different choice, or "ask IT first".
2. **Approval path:** is a third-party service acceptable for MLB-only pilot content right now, with the org's own approval sought before any Visalia footage or TrackMan data goes in?
3. **Who is the admin account**, and who else on staff should see player results (hitting coach, coordinator)?
4. **Player consent wording** and whether results are visible only to the player and a named staff group.
5. **Budget** ceiling per month, and whether a card on file is yours or the org's.
6. **A name and address** for the app (a short domain or a subdomain of one the club already owns).
7. **Native later?** Not now by default. Say so if the club already has an Apple developer account you can use.

## 8. Risks and what I would do about them

| Risk | Plan |
|---|---|
| iOS behaviors I cannot reproduce here (home-screen storage, video, evictions) | Real-device checklist every release; WebKit in the pipeline; client error log |
| Org says no to third-party hosting | The design is standard parts, so the same repo deploys to the org's cloud; D stays open |
| Clip rights (MLB footage) | Private storage and signed links from day one; keep public footage out of anything shared widely |
| Player trust: it looks like surveillance | Players see their own numbers first; assessment results are shared with the player; consent text agreed with the org |
| Scope creep into a full product | Phases are gated; staff view and native app wait until the player loop is solid |
| I cannot access your accounts or devices | Everything I build is deployable from the repo with one command or one push; the one-time setup is a checklist |
