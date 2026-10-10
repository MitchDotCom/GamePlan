# Hosting decision

Pick: **Render** (one Docker web service, one persistent disk). Runner-up: Fly.io. Chosen on the evidence below; **not tested on any host** (no accounts here, and the build sandbox cannot reach fly.io or render.com), so the first deploy runs `diskcheck` on the real volume before anyone relies on it.

## What the engine needs from a host
1. One instance with a **local block disk** that survives restarts and deploys. SQLite in WAL mode needs working file locks and fsync; network file shares are the known failure case.
2. Docker (the image is built and tested: `Dockerfile`).
3. HTTPS with a stable address. iPhones and iPads will not install or keep the app without it.
4. Daily disk snapshots, plus our own offsite copy (`OFFSITE_*`), because a snapshot is a fallback, not a backup.
5. No sleeping, no ephemeral disk, US region, and as little server administration as possible. One person runs this.

## Ten options against those needs
| Option | Verdict | Why (source) |
|---|---|---|
| Heroku | Out | Filesystem is ephemeral and is cleared at least daily; Heroku's own SQLite article says use Postgres ([Heroku Dev Center](https://devcenter.heroku.com/articles/sqlite3)). |
| DigitalOcean App Platform | Out | No persistent local storage; files vanish on deploy; 4 GiB local limit ([DO docs](https://docs.digitalocean.com/products/app-platform/how-to/store-data/)). |
| Google Cloud Run | Out | Persistent mount is Cloud Storage FUSE: no file locking, last write wins, not POSIX ([Cloud Run docs](https://docs.cloud.google.com/run/docs/tutorials/network-filesystems-fuse)). |
| Azure Container Apps | Out | Persistent storage is an SMB/NFS file share. I found no Microsoft statement on SQLite locking there, and a report of "database is locked" on a similar Azure Files mount ([Microsoft Learn](https://learn.microsoft.com/da-dk/azure/container-apps/storage-mounts), [InfluxData forum](https://community.influxdata.com/t/database-is-locked-on-container-instance-installation/22754)). Unverified, so not worth the risk. |
| Koyeb | Out for now | Volumes are in preview, 1 to 10 GB, only two regions, and the docs say "only suitable for testing" ([Koyeb docs](https://www.koyeb.com/docs/reference/volumes)). |
| Northflank | Unclear | Persistent volumes exist; I found nothing on SQLite or replica behavior, and scheduled backups were "not currently supported" on the page I saw ([Northflank docs](https://northflank.com/docs/v1/application/databases-and-persistence/backup-and-clone-volumes)). |
| Railway | Viable, second tier | Volumes with daily, weekly and monthly incremental backups, 3,000 IOPS ([Railway docs](https://docs.railway.com/volumes/backups)). Sources disagree on whether it holds a SOC 2 report, so an org security review would stall ([comparison](https://vibe-eval.com/comparisons/railway-vs-flyio-security/)). |
| VPS (Hetzner, AWS Lightsail, DigitalOcean Droplet) | Viable, most work | Cheapest and most control; a real disk and snapshots (Lightsail: daily automatic snapshots, [AWS docs](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-configuring-automatic-snapshots.html)). You would own OS patching, firewall, TLS renewal and Docker upkeep. Wrong trade for one person. |
| Fly.io | Viable, runner-up | Volumes at $0.15/GB, daily snapshots kept 5 days by default (1 to 60 settable), SOC 2 Type 2 report on request ([Fly pricing](https://fly.io/pricing.md), [snapshots](https://fly.io/docs/volumes/snapshots/), [compliance](https://fly.io/compliance.md)). Fly's own staff say volumes are not durable long-term storage and snapshots are not a primary backup. Third-party trackers list several 2026 incidents, including a 9-hour machine-start failure in one region ([isdown](https://isdown.app/status/fly-io/outage-history)). Operated mostly from a command-line tool. |
| **Render** | **Pick** | Docker web service with a persistent disk; disk snapshots every 24 hours, kept at least 7 days; single instance, which is exactly our model; paid instances do not sleep ([Render disks](https://docs.render.com/disks)). SOC 2 Type II and ISO 27001; the report is available to Organization-tier workspaces ([Render](https://render-web.onrender.com/blog/render-soc2-compliance)). Operated from a dashboard. Price: Standard $25/month plus disk $0.25/GB ([Render cost guide](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses)). |

## Why Render beats Fly.io for this case
Both meet the hard requirements. The difference is who does the work and how bad a bad day is. Render is dashboard-first, keeps snapshots longer by default (7 days against 5), and its model is one instance with one disk, which is our design. Fly's volume is tied to one physical host and is run from a command line, and its public incident record in 2026 is longer. Fly is cheaper and has a faster edge; neither matters for 80 hitters.

## What Render costs us
- Every deploy has a few seconds of downtime (a disk cannot move between two live instances). Phones queue answers and resend. Deploy off-hours; `autoDeploy` is off in `deploy/render.yaml`.
- Restoring a snapshot rolls the whole disk back and Render warns against it for databases. Our real backup is the nightly SQLite backup copied offsite; the snapshot is the second layer.
- The SOC 2 report itself may need the Organization tier. Ask Render before the org security review.

## Proof I can and cannot give
Cannot: deploy or time anything on Render or Fly from here.
Can, and did: the image is identical on every host, and `python -m gameplan.engine.diskcheck /data` checks the properties the host must provide (locks, WAL, fsync speed, 4 concurrent writers, `kill -9` loses nothing). It passed here and inside the container on a mounted volume. **Run it on the Render shell the first time; if it fails, move to Fly or a VPS without changing code.**

## Switching later
Nothing in the code is Render-specific. Moving host means: copy `engine.db` from the latest backup, set the same `ENGINE_SECRET`, start the same image. Phones keep working because credentials are verified against the secret, not the host.
