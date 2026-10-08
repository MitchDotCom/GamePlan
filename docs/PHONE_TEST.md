# Testing the phone app on your phone

Your phone cannot reach the session this was built in, so the app runs on your own computer and the phone connects to it over Wi-Fi.

## 1. Get the pieces
- Pull the branch `claude/baseball-hitting-strategy-engine-iwo2dz` (the app is `phone_app/`, the server is `src/gameplan/app_server.py`).
- Unzip `gonogo_content.zip` (sent separately: real MLB clips, about 5 MB, not in the repo) somewhere, for example `~/gonogo/content`. It holds `queue_L.json`, `queue_R.json` and the pack folders.
- Optional, to score the assessment pack on the server: `private_keys.json` goes in `~/gonogo/` (also in the zip).

## 2. Start the server (on your computer)
```
cd GamePlan
PYTHONPATH=src python3 -m gameplan.app_server --content ~/gonogo/content --data ~/gonogo/data --keys ~/gonogo/private_keys.json --port 8080
```
It prints the address for your phone, like `http://192.168.1.20:8080`. Phone and computer must be on the same Wi-Fi (not a guest network, and the computer's firewall must allow port 8080).

## 3. Open it on the phone
Safari on iPhone or Chrome on Android, that address. Plain HTTP is enough for: playing, both questions, the result card, saving answers on the phone, syncing to the server, the Log and CSV download.
Install to home screen and offline use need HTTPS (browsers only run the offline code on a secure origin). To test those, put HTTPS in front of the same server, for example:
- `tailscale serve --https=443 localhost:8080` (private to your own devices), or
- `cloudflared tunnel --url http://localhost:8080` or `ngrok http 8080` (a public link while it runs: anyone with the link could open the clips, so close it when done).
Then on the phone: Share, Add to Home Screen (iPhone) or Install app (Android).

## 4. What to check on the phone (I could not test a real phone)
1. Setup tab: enter a name, batting side; nothing runs off the screen sideways.
2. Queue: "Next starter" pack shows; clips download (watch "x of 6 clips on this phone").
3. Start: the clip plays inline (does not jump to full screen), then freezes just after release.
4. Two questions appear one after another, and the order differs between clips. Buttons are easy to hit with a thumb.
5. Result card: your answers with right or wrong, then pitch type and speed, location, ride, run, spin, extension, flight time, result, and the zone drawing.
6. Turn Wi-Fi off after the clips are downloaded (needs HTTPS for the installed app): it still opens and plays.
7. Rotate to landscape: the buttons are still on screen.
8. Light and dark mode both readable outdoors.
9. Log tab: counts match what you did. Sync now: "Synced n". The server's `data/trials.jsonl` has the rows.
10. Assessment pack (Queue, last card): no feedback after answering.
11. Lock the phone mid-clip and come back; the app recovers.
12. Anything that looks wrong or feels slow: screenshot it with the time.

## Known limits
- iOS may delete a website's stored clips if it is not installed to the home screen and unused for a while; installed apps are exempt.
- Video autoplay on iPhone needs a tap first (the Start button is that tap).
- The server is plain HTTP and for your own network. Real hosting is an org decision.
