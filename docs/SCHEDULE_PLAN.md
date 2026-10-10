# Weekly starter schedule: the logic, end to end

Built for the January pilot. This is what the code does today, the rule behind each behavior, and what is not proven yet.

## The promise
Each night the right hitter gets the right opposing starter. An admin enters the week once (a Monday off day), the system builds each starter's pitches ahead of time and checks they exist, and each hitter's phone shows his own affiliate's next starter, flipping at 9:00 pm Pacific so the next opponent is ready right after the game. A rain delay, an early finish, a scratch or a postponement is a button, not a database edit. Nothing is guessed: if a starter is missing or his pitches are not ready, the hitter is told so and gets practice pitches. A different starter is never shown in his place.

## The unit: one game
A row in `starters` is one game: (affiliate, game date, game number) -> opposing starter name, player id, opponent. Many games can be confirmed at once. Scope is the whole affiliate: every hitter assigned to Visalia sees Visalia's starter. (Per-group or per-hitter targeting is not built; see "Not built".)

## What a hitter sees (`schedule.resolve`, `playlist.compose`)
1. **Slate day.** The affiliate's local date, moved forward one day once the local clock reaches the rollover hour (default 21:00, America/Los_Angeles). So at 8:59:59 pm he sees tonight's starter, at 9:00:00 pm tomorrow's.
2. **Hold.** An admin can pin the slate day for one affiliate (rain delay, rainout, early finish). A hold expires by itself at the time set, at most 72 hours, so a forgotten hold cannot strand a team.
3. **Starter(s).** The confirmed games on the first game date on or after the slate day, within 10 days. A doubleheader shows both, game 1 first. Off days are skipped by this rule with no special case.
4. **Packs.** A pack tied to a game is served only while that game is on the slate. A pack tied to no game (team-wide) is always served. Other affiliates' packs are never served.
5. **Not ready.** If the game is on the slate but has no pitches for the hitter's side, he gets practice pitches and a note naming the starter ("Pitches for X are not ready yet. Showing practice pitches, not your opponent."). If nothing is confirmed in 10 days: "No confirmed starter ... practice pitches".
6. **People move.** Team membership is evaluated on the slate day, so a hitter promoted effective Wednesday sees the new affiliate's Wednesday starter on Tuesday night after 9 pm.
7. **Phone.** The playlist carries the games (starter, opponent, date, comp note) and `valid_until`. The app shows a "Next up" card and, if it is offline with a list older than the last switch, a warning. It refetches every time it opens with signal.

## The week grid (`/staff/schedule`)
One row per affiliate, one column per date. Each box: starter name, player id (MLBAM), opponent. Rules:
- **All or nothing.** Every box is validated first; one bad box saves nothing, lists every problem, and keeps what was typed.
- **Idempotent.** Saving the same week again changes and rebuilds nothing.
- **Blank is not delete.** An emptied box leaves the existing starter alone. Removal is an explicit "clear" tick, which keeps the row (status `rejected`) and stops serving its packs.
- **Replace.** Changing a box supersedes the old row, retires that game's packs (answers already given still score: their keys stay) and queues a rebuild.
- **Window.** Dates from yesterday to 120 days ahead, so a wrong year is caught. Same player id with a different name than before warns.
- **Doubleheader** opens game 2 under the same date.
- **Suggestions.** The MLB-schedule suggestions appear in the grid in dashed boxes; saving the box confirms it.
- Admins edit; a coach sees their own affiliate read-only.

## Content: verify, then fall back
On save, a game with a player id on an affiliate with a pitch source is queued. A background builder takes the soonest queued game, runs the same fail-closed gates as before and records `build_state`:
`queued -> building -> ready | no_video | failed`. A build interrupted by a restart is marked failed after 30 minutes so it shows and can be retried, never silently stuck. The grid shows the state in plain words and the Today page lists anything wrong for the next 7 days.

**No video or tracking found** puts a "find a comp" link on the game. The comp page takes his arsenal (pasted CSV or typed) and ranks 2025 MLB starters:
- same throwing hand required (can be overridden);
- arm block: release height, release side, extension, arm angle, each scaled by how much MLB pitchers differ;
- arsenal block: for each of his pitches (weighted by usage) the gap in velocity, horizontal break and induced vertical break to the comp's same pitch; a pitch the comp lacks costs a fixed penalty, a pitch the comp leans on that he lacks costs its usage.
The page shows every gap so the admin can overrule it. Choosing a comp re-builds the game's packs from the MLB pitcher's real video. Those packs are titled "Comp for <starter>: <pitcher>" and say they are not the starter's own video, and the phone shows it. The choice and the profile used are in the audit log.

Checked: every pitcher in the pool ranks himself first against his own profile (40 of 40), 25 of 25 random half-samples of a pitcher's pitches return the same pitcher first, handedness is respected, and Skubal/Webb/Gallen/Skenes return sensible neighbours (Webb's include Dustin May). Not checked: whether hitters read the comp and the real starter the same way. That is a baseball judgment the admin makes.

## Rain delay and early finish (admin buttons)
- **Keep this starter until [time]**: pins the current slate day for that affiliate until a local time you type. Expires on its own.
- **Show the next game now**: pins the next game; hands back to the clock at the normal switch.
- **Back to the clock**: lifts a hold.
- A postponed game: clear its box (or replace it with the makeup date). The next confirmed game shows at once.
Only one hold is live per affiliate; the newest wins. Holds, scratches and clears are in the audit log.

## Preview and attention
`/staff/schedule/preview` runs the phones' own code for every active hitter, now or just after each affiliate's next switch, and lists who would see starter pitches, practice pitches or nothing. It writes nothing. The Today page lists affiliates with no starter, missing ids, failed builds and anything not ready for the next two days.

## What was tested
- 34 schedule-logic tests: exact flip second, both daylight-saving changes, other time zones and a corrupt zone, off days, doubleheaders, scratches, postponements, holds, advance, promotions the night before, a new hitter added in the evening, a 900-step randomized run checking invariants after every step (one date at a time, confirmed only, own affiliate only, no retired pack served).
- 28 page tests: every button, role limits, CSRF, atomic saves, redirects that load, HTML in names, the build queue (success, no video, crash, restart), comps end to end, a full admin-to-phone path.
- Scale: 84 hitters on 6 affiliates compose in about a second; 36 phones opening in the same flip second all get the right starter.
- 10 browser checks on Chromium and WebKit: typing into the grid, every button, a coach's read-only view, the phone's "Next up" and stale-list warning, the comp finder. The browser run found a real bug (the save redirect built a malformed URL) that the HTTP tests missed; it is fixed with a test.

## Assumptions to confirm
1. Rollover is 9:00 pm **Pacific for every affiliate** (the setting exists per affiliate in the database but has no page yet).
2. A comp is shown from MLB broadcast video, not drawn pitches, even at an affiliate that normally gets drawn pitches. The camera view therefore differs from that affiliate's usual one.
3. Doubleheaders show both starters at once.
4. New hitters imported in the evening count from the Pacific date, so they see their affiliate immediately.

## Not built (deliberately, until you say you want it)
- Groups inside an affiliate, per-hitter overrides, hitters studying another affiliate's opponent.
- A TruMedia or TrackMan **importer**. The comp finder reads a pasted export; the starter's own pitches cannot be built from one yet. This needs a sample file (see questions in the hand-off).
- A page for each affiliate's rollover time zone and hour.
- Automatic hold from game status (rain delays are manual).
- Auto-retry of failed builds (retry is a button).

## Not proven
- Any real build against MLB video from this environment: the tests stub the pitch builder; the gates themselves were proven earlier on real data.
- The pool is 2025 only (479 pitchers; 235 with five or more starts). Names come from the MLB Stats API.
- The pilot's real workflow: whether one Monday sitting is enough time, and what happens when a probable pitcher changes on game day.
