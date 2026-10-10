# Engine runbook: deploy, install, operate

Status in one paragraph. The service, the container image, and the browser flows are tested here (Chromium and WebKit, a real running container with a root-owned volume, a seeded organization, real clips). **Not done: no host account exists, nothing is deployed, and nothing has run on a real iPhone or iPad.** The first deploy is therefore the first test of the host; steps 2 and 7 below prove it before a hitter depends on it. Host choice and evidence: `docs/HOSTING_DECISION.md`.

## 1. Before you start
- A Render account (workspace), a password manager, and an S3-compatible bucket for offsite backups (Backblaze B2, Cloudflare R2 or AWS S3; a private bucket with versioning).
- Org approval for third-party hosting of hitter names and answers. Test profiles only (made-up names) need none.
- Consent wording: edit `config/consent.json`. The shipped text is a **draft, not reviewed by anyone at the organization**. Change `version` whenever the text changes; every hitter is asked again.

## 2. Deploy on Render
1. Push this repo to a GitHub repo Render can read. Render dashboard: New, Blueprint, choose the repo, file `deploy/render.yaml`.
2. Fill the secrets it asks for:
   - `ENGINE_SECRET`: 32+ random characters. Keys every stored hash. Save it in the password manager first. Changing it signs every hitter out.
   - `ENGINE_ADMIN_TOKEN`: your first staff login (24+ characters). Becomes the first Admin on first start.
   - `PUBLIC_URL`: the service address (`https://<name>.onrender.com`), so claim links and QR codes are right.
   - Offsite and replication: `OFFSITE_BUCKET`, `OFFSITE_ENDPOINT` (for B2 or R2), `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`. With these set the container streams the database to the bucket about once a second (Litestream) and, if it ever starts on an empty disk, restores itself first. Use a private, versioned bucket.
3. After it is live, open the service Shell and run the host check:
   `python -m gameplan.engine.diskcheck /data`
   All five lines must say PASS. If any fails, stop and switch host (`deploy/fly.toml` is ready); do not put real data on it.
4. Open `https://<name>.onrender.com/staff/login`, sign in with the admin token. Today page: the four jobs (starters, reconcile, backup, offsite) show a time within a few minutes.
5. Check `https://<name>.onrender.com/healthz/deep` says `"ok": true`.

Deploys: `autoDeploy` is off. Press Deploy yourself, off-hours; there are a few seconds of downtime and phones resend what they queued.

## 3. Test profiles
In the service Shell (creates a demo organization with made-up hitters; prints one claim link per hitter and tokens once):
`python -m gameplan.engine.seed --data /data --secret "$ENGINE_SECRET" --base-url "$PUBLIC_URL"`
It refuses to run on a database that already has teams. Add real people later on the Roster page (CSV import matches on `org_id`, never on name). All levels work: Admin, Teams, add a team with its level and MLB team id; each level gets its own cadence on Settings.

## 4. Install on a phone (the main route)
1. Roster, **Claim link** for the hitter; open it on his phone **in Safari**; confirm the name; tap yes.
2. Read and agree to the consent text (nothing is served before this).
3. Share, **Add to Home Screen**. Open the app from the icon; at the welcome screen use **Use pairing code** with the code shown in Safari. (iOS keeps home-screen storage separate from Safari; the code carries identity across.)
4. Do a few answers. Roster: his phone count, "Agreed: yes" and last answer time should all move.

## 5. Org iPads shared by many hitters
Personal phones are the primary route. A shared iPad works like this:
1. On the iPad open the site once in Safari, Add to Home Screen, open it. It shows "Who are you?".
2. A hitter opens the app on his own phone, Settings, **Use on a shared iPad**; the phone shows a code (valid 10 minutes, works once).
3. He types the code on the iPad. His phone stays signed in; the iPad shows "Done".
4. When finished he taps **Done**. If he walks away, the iPad flushes his answers and signs him out after 5 minutes without a touch. If he is offline then, his unsent answers wait on the iPad under his id and send the next time he signs in; no other hitter's sign-in sends them.
5. A coach can issue the same code from the Roster page (**iPad code**) for a hitter with no phone handy.
Limits: 3 live iPad sign-ins per hitter (the oldest is retired); an iPad sign-in untouched for 8 hours stops working. Rules to keep: he never types another hitter's code; never leave an iPad signed in overnight (the idle sign-out is a backstop, not permission).

## 6. Operate
- **Durability layers**: (1) Litestream, about a second behind, point-in-time restore; (2) verified database copy every 6 hours in `/data/backups` (60 kept), pushed offsite and size-checked; (3) Render's daily disk snapshot. Restoring from layer 1 or 2 is in the Restore bullet; layer 3 rolls the whole disk back and is the last resort. Set a lifecycle rule on the bucket for retention (for example 90 days); the code never deletes offsite files.
- **Monitoring**: point any uptime monitor (UptimeRobot free tier, Better Stack) at `/healthz/deep`, alert on a non-200. It goes red when the database check fails, Litestream stops syncing or reports errors, there is no good backup in 14 hours, or the offsite copy is configured but stale. It does not watch the content pipeline; check Today weekly.
- **Restore from Litestream** (empty disk): just start the service; the entrypoint restores first. To go back in time: `litestream restore -timestamp <ISO time> -config /tmp/litestream.yml /data/engine.db` on a stopped service.
- **Restore from a database copy** (service stopped; Render: suspend the service, open a shell on a one-off job with the disk, or restore into a fresh service):
  `python -m gameplan.engine.backup --restore /data/backups/engine-<stamp>.db --into /data/engine.db`
  The backup is checked first, the old file is kept as `engine.db.before-restore`, WAL leftovers are removed. Then start the service. Phones that still hold their answers notice at their next heartbeat that the server has fewer than they sent and resend everything; duplicates are ignored. A phone whose storage was also wiped cannot resend what it no longer has. Drill this once a month on a copy; the automated drill is in `tests/engine/test_durability.py`.
- **Secrets**: `ENGINE_SECRET` lives in the password manager and Render, nowhere else. Rotating it signs everyone out (they re-claim). Staff tokens: Admin page, add a new coach, revoke the old one. A leaked claim link works once and expires; a leaked staff token is revoked from Admin.
- **Delete a hitter's data**: Admin only. His page, bottom: type his full name, Delete everything. Removes answers, devices, codes and agreements; leaves an anonymous placeholder row so the audit log stays intact. Backups taken before that day still contain him until they age out (nightly copies after 14 days; set the bucket lifecycle to match what you promise hitters). Decide and write down the retention rule before real hitters join.
- **Upgrade**: take a backup, press Deploy. Schema changes apply on start and never run backwards (an older build refuses a newer database).

## 7. Real-device checklist (before any hitter relies on it)
1. iPhone: claim in Safari, agree, Add to Home Screen, pair, answer 10, see them on his player page.
2. Airplane mode: answer 5, reopen online, all 5 arrive once.
3. Force-close mid-answer; reopen; no duplicate, no loss.
4. Repeat 1 to 3 on an iPad. Then the shared-iPad flow in section 5 with two different hitters back to back; confirm hitter 2 sees none of hitter 1.
5. Leave the home-screen app unused for a week; reopen; confirm it still knows him. If not, record what iOS did; the pairing code is the fallback.
6. Staff pages on a phone: roster, player page, leaderboard readable.
7. Cut the signal mid-session on cellular, not Wi-Fi.

## 8. Proven here vs not
Proven (automated in this repo): identity rules and throttles; wrong-person trap; idempotent ingest; server-side scoring; consent gate (nothing served or stored before agreement, versioned, per hitter); shared-iPad sign-in leaves the phone signed in, expires, and attributes answers to the right hitter; playlist rules; staff scoping, CSRF and cookie rules; path hardening; mutation checks on four protections; `kill -9` loses no acknowledged answer; 80 and 800 hitter load with no lost rows; backup, restore and the restore command; offsite push with size verification and a deep health check; the image builds, runs from a root-owned volume, survives a restart, and passes a real-browser claim, consent and answer run (`qa/container_e2e.py`); Chromium and WebKit browser suites.

Not proven: any live host; the S3 leg of Litestream (drills used a folder replica); deletion reaching old backups and offsite copies; the offsite copy against a real bucket (tested with a stand-in); iOS home-screen storage over time; real cellular behavior; TLS and proxy headers on Render; org approval; consent wording; whether drawn pitches train recognition.

## The weekly routine (admin)
Details and the rules behind each step are in `docs/SCHEDULE_PLAN.md`.

**Monday (off day), about 10 minutes**
1. Staff > Schedule. Pick the week. For each affiliate and game date type the opposing starter's name, MLBAM player id and the opponent. Doubleheader: open "+ doubleheader". Save the week. Nothing is saved if any box is wrong; the page says which.
2. Wait a few minutes, reload. Each game shows `queued`, `building...`, then `ready`. Pitches are built automatically.
3. A game that says **no video or tracking found**: first click "upload his pitches or find a comp" and upload his TruMedia pitch export (his last three to six starts, CSV; Check the file, then Use these pitches). If there is no export, choose "find a comp" instead, paste his arsenal export (or type hand, release height and side, extension, arm angle and his pitches), pick the closest MLB pitcher, Use. The game rebuilds from that pitcher's video and tells hitters it is a comp.
4. Staff > Schedule > Preview. Every affiliate should say all hitters will see the starter's pitches. Fix anything it lists, or note it.
5. Today page: the Schedule block should read "Every affiliate has its next starter confirmed and built."

**During the week**
- Starter scratched: type the replacement over the box and Save. His pitches rebuild; the old ones stop being served. Answers already given still count.
- Game postponed: tick "clear" on that box (or type the makeup date's starter) and Save. Hitters move to the next confirmed game immediately.
- Rain delay or a game that runs past 9 pm: on the affiliate's row choose change > "Keep this starter until [time]". It ends by itself.
- Game over early and you want the next opponent now: change > "Show the next game now".
- Anything unusual: change > "Back to the clock" returns to the normal 9:00 pm Pacific switch.
- A build that says failed: retry. If it fails twice, read the reason on the Starters page and use a comp.

**What hitters see.** The app shows "Next up: starter vs opponent" and the pitches for that game. If the pitches are not ready it says so and shows practice pitches. If the phone has been offline since before the last switch it warns that its list is out of date.
