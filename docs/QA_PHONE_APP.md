# Phone app QA release gate, 2026-10-08

Runner: `qa/phone_app_qa.py` (Playwright, real built MLB content, a fresh browser context per check). Final run on the final code: Chromium 52 of 52, WebKit 52 of 52 pass. WebKit is the engine behind iOS Safari (emulated as an iPhone 13). Raw results: `qa/results_chromium.json`, `qa/results_webkit.json`.

## Defects found by this QA and fixed

| # | Severity | Defect | Found by | Fix |
|---|---|---|---|---|
| 1 | S1 | Safari/WebKit could not save clips on the phone (Blob in IndexedDB fails) | WebKit | clips stored as raw bytes |
| 2 | S1 | Fix for 1 opened the storage transaction before reading the bytes, so no clip saved at all | QA matrix | read bytes first |
| 3 | S1 | Double tap on GO recorded three answers | F1 | single-answer lock |
| 4 | S1 | Tapping Start twice could hang the app | F2 | single-start lock |
| 5 | S1 | A player name starting with `=` reached the CSV as a spreadsheet formula (app and server exports) | D7 | cells neutralised |
| 6 | S1 | The server could read files outside its folders | J1 | paths resolved and confined |
| 7 | S1 | Pack titles and tracking text were put into the page unescaped (script injection) | J4 | all outside text escaped |
| 8 | S1 | Setup tab scrolled sideways by 156 to 248 px on every phone width | G1 | stacked layout |
| 9 | S1 | GO and NO-GO below the screen on small phones and in landscape | G1, F6 | focus mode while a pitch is on |
| 10 | S2 | Online/offline chip trusted the phone's radio flag and cached answers | A4/E2 | based on real request results |
| 11 | S2 | Pack list could render twice | screenshot review | latest render wins |
| 12 | S2 | Tab buttons 33 px tall (below 44) | G2 | 44 px on touch screens |
| 13 | S2 | Server accepted oversize and malformed bodies | J2 | size limit, shape checks |
| 14 | S2 | A clip that fails to decode could leave the app stuck | F5 | watchdog and error recovery |

## Final matrix

| ID | Area | Check | Chromium | WebKit | Evidence (Chromium) |
|---|---|---|---|---|---|
| A1 | Install | Manifest has name, standalone display, start_url and both icons that exist with the declared sizes | PASS | PASS | icons [192, 512] |
| A2 | Install | Service worker registers, activates and controls the page after one reload | PASS | PASS | controller active after reload |
| A3 | Install | iOS home-screen tags present (apple-touch-icon 180px, capable, status bar, title) and theme-color set | PASS | PASS | {'touch': True, 'cap': 'yes', 'theme': '#5f249f', 'title': 'Go/No-Go', 'vp': 'width=device-width,initial-scale=1,viewport-fit=cover'} |
| A4 | Install | With the SERVER STOPPED, the installed shell still opens, shows the cached queue and plays a cached clip | PASS | PASS | opened and played with the server down; chip said offline |
| B1 | First run | Start with no player name: blocked with a message, no answer is recorded | PASS | PASS | Enter a player name or ID first |
| B2 | First run | Empty content folder (no queue yet): app opens, says so, no script errors | PASS | PASS | queue says 'No queue yet. Connect once to load it.', play says 'No pitches yet. Connect once to load the queue.' |
| B3 | First run | Very first load while offline (nothing cached): fails safely, no crash loop | PASS | PASS | browser shows its offline page; the app needs one online visit to install (documented) |
| C1 | Core | Both questions per clip: 2 rows, same clip_trial, q_order 1 and 2, different tasks | PASS | PASS | questions asked: ['Fastball?', 'Strike?'] |
| C2 | Core | Question order is randomized: across the pack both orders occur, and the same clip keeps the same order | PASS | PASS | first questions over 8 clips: ['Strike?', 'Strike?', 'Strike?', 'Strike?', 'Fastball?', 'Strike?', 'Strike?', 'Fastball?'] |
| C3a | Core | Ask 'zone' only: one row per clip, task zone | PASS | PASS |  |
| C3b | Core | Ask 'pitch' only: one row per clip, task pitch | PASS | PASS |  |
| C4 | Core | Training: each answer is scored against the shipped key; verdicts on screen match the stored correct flag | PASS | PASS | 0 of 2 correct, screen agrees |
| C5 | Core | Assessment: no feedback, no reveal playback, no answers in the page or the queue file, stored key is blank | PASS | PASS | mode=assess, video paused=False |
| C6 | Core | Run block: plays every pitch in the queue once, auto-advances, ends with 'Done' | PASS | PASS | 24 pitches answered, 23 distinct clips |
| C7 | Core | Keyboard: G, N and Space work (for a desktop or Bluetooth keyboard) | PASS | PASS |  |
| C8 | Core | Pack completion: the Start button comes back and the queue marks the pitches done after a reload | PASS | PASS | hero now says: NEXT UP: RANDOM: SCOTT BARLOW |
| D1 | Data | Every stored answer has all fields; times are plausible; ids unique | PASS | PASS | 6 rows |
| D2 | Data | Sync twice and concurrently: server holds exactly the local count, nothing duplicated | PASS | PASS | local 2, server 2, chip '0 to sync' |
| D3 | Data | Server CSV is read by the recognition profile code and produces a profile (end to end, no exceptions) | PASS | PASS | 8 rows, zone n=4, pitch n=4 |
| D4 | Data | Reload keeps answers, settings and the 'done' state | PASS | PASS | {'player': 'Persist Test', 'bats': 'L', 'ask': 'zone', 'off': '0.150'} |
| D5 | Data | Erase on this phone really clears answers and resets the sync chip | PASS | PASS |  |
| D6 | Data | Server unreachable during sync: clear message, answers stay unsynced, later sync succeeds with nothing lost | PASS | PASS | failed sync -> chip '1 to sync', net 'offline'; retry stored 1 |
| D7 | Data | CSV formula injection: a player name like =cmd|... must not reach a spreadsheet cell as a formula (app export and server CSV) | PASS | PASS | neutralised in both exports |
| E1 | Offline | Clip not on the phone and no signal: a clear message, no crash, state recovers | PASS | PASS | This clip is not on the phone and there is no signal. |
| E2 | Offline | The server disappears right after a clip starts: the pitch, the question and the answer all still work (server really stopped, not browser offline emulation) | PASS | PASS |  |
| F1 | Robustness | Double-tapping GO records ONE answer for that question | PASS | PASS |  |
| F2 | Robustness | Start tapped repeatedly: one playback, one set of trials | PASS | PASS |  |
| F3 | Robustness | During a pitch the tab bar is hidden (focus mode); the question appears and is answered; the tabs return afterwards | PASS | PASS |  |
| F4 | Robustness | Reload in the middle of a question: no half-written answers, app recovers to idle | PASS | PASS | kept the one completed answer; the unfinished clip is simply asked again |
| F5 | Robustness | Corrupt clip file in storage: the app reports it and recovers, it does not hang in 'playing' | PASS | PASS | state after corrupt clip: idle; message 'Tap Start pitch to allow video' |
| F6 | Robustness | Landscape orientation: question buttons are on screen without scrolling | PASS | PASS | [278.390625, 355.390625, 390] |
| G1-320 | Layout | iPhone SE 1st gen 320x568: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows | PASS | PASS | overflow {'play': 0, 'queue': 0, 'log': 0, 'keys': 0, 'set': 0}; buttons bottom 392/568, height 77 |
| G1-360 | Layout | small Android 360x640: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows | PASS | PASS | overflow {'play': 0, 'queue': 0, 'log': 0, 'keys': 0, 'set': 0}; buttons bottom 415/640, height 77 |
| G1-375 | Layout | iPhone SE 2/3 375x667: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows | PASS | PASS | overflow {'play': 0, 'queue': 0, 'log': 0, 'keys': 0, 'set': 0}; buttons bottom 423/667, height 77 |
| G1-390 | Layout | iPhone 14 390x844: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows | PASS | PASS | overflow {'play': 0, 'queue': 0, 'log': 0, 'keys': 0, 'set': 0}; buttons bottom 432/844, height 77 |
| G1-412 | Layout | Pixel 7 412x915: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows | PASS | PASS | overflow {'play': 0, 'queue': 0, 'log': 0, 'keys': 0, 'set': 0}; buttons bottom 444/915, height 77 |
| G1-820 | Layout | iPad 820x1180: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows | PASS | PASS | overflow {'play': 0, 'queue': 0, 'log': 0, 'keys': 0, 'set': 0}; buttons bottom 527/1180, height 77 |
| G2 | Accessibility | Tap targets: GO, NO-GO, Start, tabs and sync are at least 44 px tall | PASS | PASS | {'bgo': 77, 'bno': 77, 'sync': 44} |
| G3 | Accessibility | Controls have accessible names; images/svg labelled; page has a title and lang | PASS | PASS | {'lang': 'en', 'title': 'Go / No-Go', 'unnamed': [], 'svg': True} |
| G4-light | Layout | light theme: every tab renders, no script or console errors | PASS | PASS | background rgb(255, 255, 255) |
| G4-dark | Layout | dark theme: every tab renders, no script or console errors | PASS | PASS | background rgb(21, 11, 36) |
| H1 | Timing | Pause lands within 1.5 frames of release+offset for EVERY clip in both queues at 50, 100 and 200 ms | PASS | PASS | 144 runs, median +0.10 frames, worst 1.35 |
| H2 | Timing | Speed: tap Start to question under 3 s (cached clip); app ready under 2 s on localhost | PASS | PASS | ready 0.17 s, start-to-question 1.78 s (includes the clip's own lead-in) |
| I1 | Content | Every queue item: file exists, plays, release inside the clip with at least 0.4 s after it; keys agree with the pitch's own location and type | PASS | PASS | 48 items checked |
| I2 | Content | Assessment keys are absent from every public file and present in the private file for every assessment item | PASS | PASS | queue files carry null keys for assessment items |
| I3 | Content | Footprint: total content and per-clip size reasonable for a phone | PASS | PASS | 48 clips, 5.3 MB total, largest 0.15 MB |
| J1 | Security | Path traversal: ../ and encoded variants cannot read files outside the app and content folders | PASS | PASS | no file outside the served folders was readable |
| J2 | Security | POST hardening: oversize body, bad JSON, wrong shape, missing ids are all rejected without crashing the server | PASS | PASS | {'badjson': 400, 'notlist': 400, 'nokey': 400, 'noid': 200, 'toobig': 413} |
| J3 | Security | Shared token: wrong or missing token gets 401 on POST and on the CSV; correct token works | PASS | PASS | codes [401, 401, 200]; note: config.json hands the token to anyone who opens the app, so it is a team passcode, not a secret |
| J4 | Security | Script injection: hostile player name and hostile pack title never execute | PASS | PASS |  |
| J5 | Security | Static server: only GET/POST used; HEAD, OPTIONS and unknown paths answer without killing the server | PASS | PASS | {'HEAD': 200, 'OPTIONS': 501, 'DELETE': 501, 'PUT': 501} |
| K1 | Hygiene | No uncaught script errors or console errors occurred anywhere in this run | PASS | PASS | 1 console lines, none from the app's own code |

## What this does not cover
- **No real iPhone or Android.** WebKit here is the iOS engine on Linux, with iPhone screen emulation. Real-device differences (home-screen storage, audio and autoplay policy, touch latency, thermal, memory, the iOS version on the player's phone) are untested.
- **The published Artifact link** runs inside claude.ai's frame, which blocks service workers: no install, no offline there. Playing, both questions, the result card and syncing are exercised by the artifact-specific test.
- Tap-to-answer timing accuracy on real hardware.
- Load: one player at a time. Many phones syncing at once is untested.
- Content: only the MLB clips built so far. Visalia low-home clips go through a different build and have not been run through this gate.
- Accessibility beyond contrast, tap size, names and landscape: no screen reader pass, no large-text setting test.
