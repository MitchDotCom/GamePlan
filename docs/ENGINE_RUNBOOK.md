# Engine runbook: deploy, install on phones, operate

Status: the service, tests and browser QA run here. **The container image has not been built (no Docker daemon in the build environment), nothing is deployed, and nothing has run on a real iPhone or iPad.** Steps 1 to 3 are the first time those parts are exercised, so treat the first deploy as the test.

## 1. Deploy (any host with a container, HTTPS and a persistent disk)
Needs: a persistent volume mounted at `/data`, HTTPS (iPhones refuse the app features without it), one instance only.

Environment variables:
| Name | Value |
|---|---|
| `ENGINE_SECRET` | 24+ random characters. Keys every stored hash. Losing or changing it signs everyone out. Store it in the host's secret store and in a second safe place. |
| `ENGINE_ADMIN_TOKEN` | Your first staff login. Used once, on first start, to create the Admin. |
| `PUBLIC_URL` | The public https address, so claim links and QR codes are correct. |
| `ENGINE_DATA` | `/data` (set in the Dockerfile). |
| `TRUST_PROXY` | `1` behind the host's proxy (set in the Dockerfile). |

Start command (already in the Dockerfile): `uvicorn gameplan.engine.app:create_app --factory --workers 1`. Do not raise the worker count; the scheduler, throttles and the single SQLite writer assume one process. `deploy/fly.toml` is a worked example.

Check: open `https://<host>/staff/login`, sign in with the admin token, confirm `/config.json` answers.

## 2. Set up the organization (Admin page and Roster page, no code)
1. Admin: add teams (name, level, MLB team id, sport id).
2. Admin: add coaches, each scoped to their teams. Each gets a one-time token; keep it out of chat logs.
3. Roster: import the CSV (`name,bats,team,org_id`). Players match on `org_id`, never on name.
4. Starters: confirm the opposing starter for each team's next game (the schedule only suggests), then build. A pack goes live only if every verification gate passes.
5. Settings: set each level's cadence and pause or view options.

Org approval and the privacy position (consent wording, who sees what) come before real names go in. Do not load org footage until that is settled.

## 3. Install on a phone or iPad
Per hitter, with the coach's Roster page open:
1. Roster: **Claim link** for the hitter (shows a link and QR). One use, expires.
2. On the hitter's device, open the link **in Safari**. Confirm the name shown is his.
3. Share, **Add to Home Screen**. Open the app from the icon. iOS gives the home-screen app its own storage, so the app shows an **8-digit pairing code** screen the first time; enter the code displayed in Safari. (This is the known iOS storage gap.)
4. Do 3 answers. On the Roster page the hitter shows a last-seen time and an answer count; both must move.

Wrong name or a lost phone: Roster, **Recovery code** (retires all other devices), or **Revoke** on one device. A hitter may have at most 2 active devices.

## 4. Operate
- Nightly: the scheduler takes a verified backup to `/data/backups` (14 kept) and runs reconcile. The Today page lists anything flagged (for example possible lost answers).
- **Offsite copy is on you.** Backups on the same volume die with the volume. Copy `/data/backups/engine-*.db` off the host weekly at minimum (host volume snapshot, or `fly ssh sftp`).
- Restore: stop the service, copy a backup over `/data/engine.db`, remove `engine.db-wal` and `engine.db-shm`, start. Phones replay unsent answers on their next open; duplicates are ignored.
- Export: Leaderboard page, **Export answers (CSV)**.
- Upgrades: redeploy the image. The schema migrates on start. Take a backup first.

## 5. Real-device checklist (run before any hitter relies on it)
1. Claim on iPhone Safari, add to Home Screen, pair, answer 10 items, see them on the player page.
2. Airplane mode: answer 5, reopen online, confirm all 5 arrive once.
3. Force-close the app mid-answer; reopen; no duplicate, no loss.
4. Same on an iPad.
5. One device, two hitters: the second hitter must open his own claim link; the app then refuses to send the first hitter's unsent answers under the second name. Confirm this once on a real device.
6. Leave the app unused for a week; reopen; confirm it still knows him (if not, record how iOS behaved; the pairing code is the fallback).
7. Staff pages on a phone: roster, hitter pocket map, leaderboard readable.

## 6. Proven here vs not
Proven (automated, in this repo): identity rules and throttles, wrong-person trap, idempotent ingest, server-side scoring, playlist rules, staff scoping, CSRF and cookie rules, path hardening, mutation checks on four protections, kill -9 with zero acknowledged answers lost, 80 and 800 hitter load with zero lost rows, backup restore drill, Chromium and WebKit browser flows.

Not proven: the container build and any live deploy, iOS home-screen storage over time, behavior on real cellular networks, TLS and proxy header handling on the chosen host, Postgres migration, whether drawn pitches train recognition, org policy approval.
