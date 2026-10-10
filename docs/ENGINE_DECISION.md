# Engine decision: three candidate designs, the holes in each, and the pick

2026-10-10. Requirement set (from the owner): the whole loop must work end to end (identity, level and starter-based playlists, video and drawn pitches, strike/ball and pitch-type answers, durable recording, coach views); installable on a phone or iPad within days; sustainable and scalable to 80 to 400 hitters; no reinvented wheels; cost is not a constraint. Constraints verified in `ENGINE_PLAN.md` section 3 (iOS storage can be lost, no background sync on iOS Safari, probable pitchers missing for a large share of Single-A games, no device identity on the web).

What this environment can and cannot do matters, because anything I cannot run here I cannot test: I can run Python services, SQLite, Chromium and WebKit; I cannot run a Postgres server, the Supabase tooling, Xcode or a device farm, and I cannot create hosting accounts.

## Option A: Backend-as-a-service (Supabase) plus static app

Static PWA on a CDN host; Supabase for Postgres, row-level security, auth, storage and server functions.

For: managed Postgres and backups; row-level security is the right model for "coach sees only his team"; storage and CDN for clips; the pieces are standard.

Holes:
1. **The core of the problem is custom anyway.** Roster-backed claim links, pairing codes, recovery codes and per-player device credentials are not what the built-in auth does. They would be written as server functions in TypeScript on Deno, a new language and runtime for this project.
2. **I cannot run it here.** No Supabase tooling and no Postgres server in this environment. Every identity and sync test would wait for an account and run against a live service, or be written blind.
3. **The existing Python work does not fit.** The content pipeline (schedule, clips, ffmpeg cuts, gates), the ledger and the profile code are Python. They would need a second runner outside the platform, so there would be two backends instead of one.
4. **Limits I could not verify.** Auth email and anonymous sign-in limits and connection counts conflict between sources. Hitters cannot be assumed to have org email.
5. **Policy mistakes are silent.** A wrong row-level-security policy leaks one hitter's data to another and nothing crashes. It needs the attacker tests anyway.
6. **Time.** Before the first test: accounts, project setup, functions, local emulation. Several days of setup that produce no hitter-facing value.

Verdict: good long-term home for the database, wrong place to start.

## Option B: One Python service with its own database, deployed to a hosting platform

A single web service (FastAPI) that serves the phone app, the player API, the staff pages and the scheduled jobs; SQLite in WAL mode on a persistent volume with scheduled off-site backups; deployed from a container to a platform that gives HTTPS and a volume.

For: the existing Python code (prep, gates, ledger, profile, resolver, tracking) runs inside the service unchanged; everything runs and is testable here, including identity, sync fault injection, load and security tests; one deploy target; installable as soon as it has an HTTPS address; the SQL is portable to Postgres.

Holes:
1. **Single instance.** If it is down, hitters cannot sync. Mitigation: the phone outbox holds answers (an outage of hours is invisible), a health check restarts it, the volume is snapshotted, the database is copied off-site nightly, and a restore drill is a release gate.
2. **We own the identity code.** That is the highest-risk code in the system. Mitigation: it is small (a few hundred lines), uses only standard primitives (random tokens, hashed at rest, constant-time compare, expiry, attempt limits), and is covered first by the identity and security test layers.
3. **SQLite has one writer.** The expected peak is about 20 writes per second sustained and a few hundred in a burst, which SQLite handles; this is measured by the load test, not assumed. Trigger for moving to Postgres: more than one instance needed, direct BI connection wanted, or write latency above the gate.
4. **We maintain a service.** Mitigation: one container, no moving parts beyond it, a runbook.
5. **Video and drawn-pitch files served from the same instance.** Clips are about 110 KB each, content is immutable and cached by hash; a CDN in front is a later switch, not a rewrite.
6. **Platform lock-in.** Low: a container and a volume run on any of the common platforms.

Verdict: fastest path to a real, testable, installable engine; the only option I can verify end to end before it touches a host.

## Option C: Native iOS app (wrapped web app or SwiftUI) plus any backend

For: reliable local storage (no eviction), true background upload, more dependable push, an App Store or TestFlight install.

Holes:
1. **It still needs a backend.** C is B plus a native shell, not an alternative to it.
2. **Cannot be built or signed here.** No Xcode, no signing, no devices. Requires an Apple developer account, builds, TestFlight processing and review.
3. **Weeks, not days.** Misses the "within the next few days" requirement.
4. **Does not solve identity.** iOS gives apps no reliable person-level identifier either; the claim step stays.
5. **Two release paths** to maintain (web and native).

Verdict: a real option for later. Decision gate is after real-device testing (section 12 of the plan): if credentials or unsent answers are lost on real phones above a set rate, wrap the same web app.

## Pick: Option B, with the database design portable to Postgres

Why B and not a blend: it is the only design whose every guarantee I can prove before deployment, and it reuses the most existing, already-tested code. A and C are not discarded: A becomes the database host if the Postgres trigger fires; C is the shell if the device tests demand it.

### What is bought, not built
Web framework (FastAPI), database (SQLite now, Postgres later), QR codes (segno), HTTPS and a volume (the hosting platform), load testing (a script now, k6 later), browsers for testing (Playwright). Not built: login with passwords, email delivery, a push system, a native app, a CDN, a message queue.

### What is built (small, because the rest is bought)
Roster import; claim, pairing and recovery; per-player credentials; the answer endpoint; the playlist composer; starter confirmation; the pack registry; staff pages; backup, reconcile and ledger-rebuild jobs; the phone app's identity screens and outbox. Each has tests before it is trusted.

### Scope of the first installable version
Everything on the owner's list, in a minimal form that works: identity (claim link, QR, pairing code, recovery, revoke, switch user), teams and levels with assignments, staff-confirmed starters, packs built by the existing pipeline and registered immutably, a per-hitter daily playlist from level settings, history and weak spots, the phone app with an outbox that cannot lose or duplicate answers, server-side scoring, and staff pages for roster, starters, per-hitter pocket maps and leaderboards with their sample sizes. Deferred and recorded: shared-device kiosk mode with PINs, push reminders, SSO, CDN, Postgres.
