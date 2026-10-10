# Hosting and durability decision (second pass)

Horizon: the whole 2027 season and likely longer. 50 to 80 hitters now, designed for about 400, every level, answers that must never be lost or attached to the wrong person.

## What was wrong with the first pass
1. I chose in an afternoon from documentation snippets. I looked for incident history on the runner-up (Fly) but not on my pick (Render). Render's own record includes a March 2026 Ohio incident in which services failed with disk errors and were moved to new hosts ([trackers](https://pingoru.io/providers/render/outage-history); the authoritative record is status.render.com). A host with a disk incident is exactly the case the durability design has to survive, so "Render over Fly" is a weaker claim than I made.
2. I treated "SQLite on one disk with nightly backups" as the design and only compared hosts that suit it. I never priced the two real alternatives: **continuous replication of the same database** (Litestream) and **the same Python service on a managed Postgres**.
3. I dismissed Supabase partly because I could not run it in my environment. That is a fact about me, not about your needs.
4. My runbook said phones "resend whatever a restore missed". The code did not do that: phones resent only unsent answers. After a restore, answers the server had acknowledged were simply gone. Fixed (below) and tested.

## Requirements (from you, made explicit)
Durable: no acknowledged answer lost, or the loss is bounded and recoverable. Right person: identity cannot be confused. Lasts a year or more with one maintainer. Org-reviewable (SOC 2 or equivalent, data location, deletion). Portable: moving host or moving into an org tenant is a day, not a rewrite. Cost is not a constraint; effort and risk are.

## The options, as architectures
| | A. Render + SQLite + Litestream (chosen) | B. Same service on managed Postgres | C. Supabase as the whole backend | D. VPS you run | E. Org-hosted (their cloud) |
|---|---|---|---|---|---|
| Code change | none; added a sidecar | port SQL (about 30 SQLite-specific spots in 8 files), rerun every suite | rewrite identity and scoring as TypeScript functions + RLS policies; Python pipeline still needs a host | none | none (container) |
| Data loss on disk loss | about 1 second, plus phones resend (measured below) | near zero (managed) | near zero with PITR add-on | whatever you configure | whatever they configure |
| Extra monthly cost | small (bucket) | database tier; Supabase PITR (7-day) is about $100/month on top of compute per a third-party guide ([BackupDrill](https://backupdrill.com/guides/supabase-point-in-time-recovery)); Render Postgres includes PITR on paid plans, 3 days (Hobby workspace) or 7 days (Pro) ([Render docs](https://render.com/docs/postgresql-refresh)) | same Supabase costs plus a second host | cheapest | n/a |
| Operations | one container, dashboard | container plus database | two systems | OS patching, TLS, Docker | their IT |
| Scale ceiling | far above 400 hitters (800-hitter load test, zero lost rows) | higher, multiple app instances possible | high | host-limited | n/a |
| Biggest risk | single instance: downtime on host trouble | porting bugs; connection limits and cold starts on some providers (Neon autosuspend; [Neon FAQ](https://neon.com/faqs/postgres-hosting-options-auto-pause-database)) | silent policy mistakes leak one hitter's data to another | you are the sysadmin | approval timeline |

## Why A, now, with the exit defined
The durability gap that made B or C attractive is closed by Litestream: it streams every database change to the bucket about once a second, supports point-in-time restore, and the 0.5 line is current and maintained ([Litestream](https://litestream.io/how-it-works/), [project](https://github.com/benbjohnson/litestream)). It is disaster recovery, not high availability: one replica destination, and a disk failure can lose roughly the last second. Pinned to 0.5.11 in the image with a checksum.

Measured here, not quoted:
- **Lost-second test (4 trials).** Real engine ingest writing about 2,000 answers a second, Litestream syncing every second, then `kill -9` on the writer and Litestream, then the data folder deleted, then restore from the replica. Integrity check ok every time. Missing acknowledged answers: 1,881 to 1,983 per trial, which is the last second at that synthetic rate. At pilot rates (a few answers a minute) that is zero to a handful.
- **Container disaster drill.** Through the real API, 3,780 acknowledged answers; container killed with SIGKILL; its disk wiped; a fresh container started on the empty disk restored automatically; 0 missing; the hitter's existing sign-in still worked; ingest after the restore accepted the phone's resend.
- **Phones fill the gap.** The phone keeps its answers. Its heartbeat reports how many it sent; if the server holds fewer, the server asks it to resend everything and idempotent ingest stores only what is missing. Tested at API level and in Chromium and WebKit (E19).
- **Three layers:** Litestream (seconds), nightly-style database backups now every 6 hours with 60 kept plus offsite push, and Render's daily disk snapshot as last resort. `/healthz/deep` goes red if Litestream stops syncing, reports errors, or either backup layer goes stale; point an uptime monitor at it.

Why not B today: it fixes a problem A no longer has, at the price of porting and re-proving the identity and sync code. Why not C: unchanged from `docs/ENGINE_DECISION.md`, the core of the problem is custom code and the Python pipeline needs its own host anyway.

## When to move to Postgres (written down now so it is not decided in a crisis)
Any one of: the org requires a managed database or will not allow a self-run one; you need more than one app instance (zero-downtime deploys, high availability); ingest p99 stays above 500 ms in the load test at your real size; more than one organization shares the service. Cost of the move: a few days plus every suite rerun. The SQL was kept portable on purpose.

## Hosts compared (unchanged where the evidence was fine)
Out for this design: Heroku (ephemeral disk), DigitalOcean App Platform (no persistent disk), Google Cloud Run (no file locking on its storage mount), Azure Container Apps (SMB share; SQLite on it unverified), Koyeb (volumes "testing only"). Viable: Render, Fly.io, Railway, a VPS, an org tenant. Render stays the pick for a dashboard-run, one-instance service with SOC 2 Type II and ISO 27001; Fly is a one-file switch (`deploy/fly.toml`); so is any host that runs a container with a disk, because the replica lives in your bucket, not on the host.

## What is still not proven
- The S3 leg of Litestream (the drills used a folder replica; same code path for change capture, different transport).
- Restore time at season size. Rough size: about 580 bytes per answer, so a season is 0.25 GB at 80 hitters and about 1.3 GB at 400; restore is network-bound, likely minutes.
- Render itself (nothing has been deployed there), including whether its disk behaves under `diskcheck`.
- iOS home-screen storage over weeks. WebKit's seven-day cap applies to Safari tabs; home-screen apps count their own days of use, but a WebKit bug report describes a re-login after seven days on iOS 15.3 ([WebKit bug](https://bugs.webkit.org/show_bug.cgi?id=237350), [coverage](https://searchengineland.com/what-safaris-7-day-cap-on-script-writeable-storage-means-for-pwa-developers-332519)). The design assumes it can happen: the server is the source of truth, pairing and recovery codes exist, and a phone whose storage vanished loses only answers it had not sent.
- Litestream long-term maintenance beyond the current release line.

## Before Opening Day 2027
A four-week pilot on real devices; one full restore drill on the real Render service and real bucket; a decision on Render versus an org tenant once IT is asked; the consent wording and a written retention rule.
