# Phone app, 2026-10-08

`phone_app/` is an installable web app (no app store). A player opens a link once, adds it to the home screen, and from then on it opens like an app, works with no signal, and syncs answers when there is signal. It copies the coach viewer's design system (colors, JetBrains Mono bundled, pill tabs, hero card, label-left value-right rows, zone card). Two small deviations for the phone: text is 12px labels and 14px body (the viewer's are 11.5 and 13), and in dark theme the purple fills are darker so light text passes 4.5:1.

## What a player gets
- **Play**: a clip plays, pauses at release plus the chosen offset (default 100 ms), then asks two questions in random order: "Is it a strike?" and "Is it a fastball?" (GO or NO-GO each, timed separately). Training mode then shows the answers and a result card with the pitch's type and speed, where it crossed (and how far from the zone edge), ride and run in inches, spin, extension, flight time and the result, with the pitch drawn on the zone. Assessment mode shows none of that.
- **Queue**: next starter's pack first (his most-used pitches to the batter's side, from his recent starts pooled), then random packs of other pitchers on his team, then an optional assessment pack. Packs show done, on-phone and mode. "Run block" plays everything in random order.
- **Log**: this session's answers, accuracy for each question with counts, copy as CSV, download or share the CSV, sync now.
- **Keys**: set the truth for any pitch that shipped without an answer.
- **Setup**: player name or ID, batting side, mode, questions per clip (both, strike only, fastball only), pause offset, whether the rest of the clip plays, data on the phone.
- Keyboard: G, N, Space or Enter (for a desktop or a Bluetooth keyboard).

## Building content
`python -m gameplan.app_content --pitcher-id <id> --season <yr> --before <date> --starts N --random-packs 2 --assess-pitches 12 --work <dir> --content <dir>/content`
Writes `queue_L.json`, `queue_R.json` and one folder of small clips per pack (640 px wide, no audio, scoreboard cropped). Answer keys for assessment packs go to `<work>/private_keys.json`, never to `content/`.
MLB source today. For Visalia the same `build_pack` takes rows from the TrackMan + low-home path (`gameplan.visalia`); that wiring is not done.

## Running it
`python -m gameplan.app_server --content <dir>/content --data <dir>/data --keys <work>/private_keys.json [--token SECRET]`
Serves the app and content, accepts answers at `/api/trials` (idempotent by trial id), and writes `/api/trials.csv`, which is the format `gameplan.recognition_profile` reads. Assessment rows are scored here from the private keys.
For installs, offline use and the service worker, phones need HTTPS. This server is plain HTTP, so it is for a LAN, tests and local use. Production means the org's own HTTPS host (or any static host for the app and content, plus an endpoint for sync). Not decided, and not done here.
Without a sync server the app still works fully; use Download to share the CSV.

## Tested
- `tests/test_phone_app_e2e.py` (headless Chromium, 390x844 phone viewport, real built MLB content): player required; queue loads and the pack is listed once; clips download to the phone; the pause lands within 1.5 frames of the target; both questions asked in either order; result card has the location, pitch and characteristics and the zone drawing; two rows saved with the same clip trial; sync reaches the server; a reload with the network switched off still opens and plays a clip and shows "offline".
- `tests/test_app_server.py`: idempotent sync, token check, assessment rows scored from private keys, assessment packs ship no keys.
- Found and fixed while testing: the online/offline chip trusted `navigator.onLine` (now reflects real fetch results, including cached fallbacks); the pack list could render twice.

## Not tested or not done
- Real iPhone or Android. Headless Chromium stands in. iOS Safari quirks (autoplay, storage limits, install flow) need a real device.
- HTTPS hosting, and who may host org footage. MLB clips are broadcast footage and Visalia clips are the org's; none were published anywhere.
- Visalia content (TrackMan rows, low-home clips, the clip-to-pitch join) is not wired into `app_content`.
- No comparison with the pitcher's typical pitch on the result card, no per-hitter dashboard inside the app, no accounts. Names are stored as typed; use IDs.
- Storage: about 0.5 to 1 MB per clip, so a 30-clip queue is roughly 20 MB; iOS can evict storage for sites not installed to the home screen.
