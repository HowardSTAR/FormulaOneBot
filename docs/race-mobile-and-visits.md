# Mobile racing and visitor metrics

Race results and ghosts represent the complete three-lap race, not an individual lap.
Only telemetry matching the leaderboard's best time is served as a global ghost.
Legacy scores without telemetry remain in the leaderboard; no slower substitute is
shown. A new fastest recording or an authorized reset restores ghost availability.

Movement, telemetry and elapsed time advance through the same simulation substeps.
Frames longer than 250 ms are bounded equally for all three; hidden tabs pause play.
The finish time is interpolated at the actual line crossing.

Touch steering uses a captured pointer with an analog horizontal axis and a small
dead zone. Pedals use independent pointer capture, so steering and acceleration can
be held simultaneously. Gas is above brake. iPhone Safari chrome cannot be hidden
reliably by rotation; launch the installed Home Screen web app. Supported browsers
receive a fullscreen request on the Start button's user gesture.

`npm run build` in `front` now builds `race-game`, copies its generated assets, then
builds the site. Install both projects' npm dependencies first. Docker also builds
the game from source. `npm run build:front` is only for a prebuilt game.

Visitor metrics start when this version is deployed. A first-party random cookie
deduplicates browser visits for up to a year. Paths exclude query strings; repeated
visits to one path within a five-minute bucket are merged. Logged-in activity links
previous guest visits on that browser to the authenticated account. No IP addresses
or fingerprints are saved by this feature. Different browsers and cleared cookies
count separately; this is an estimate of visitors, not proof of unique people.
Existing authenticated DAU/WAU/MAU metrics retain their meaning; the new site-visit
section includes guests and is independent of the bot/site filter.

Verification: race-game `npm test`; pytest `test_race_ghost.py`, `test_site_visits.py`,
`test_admin_api.py`, `test_api.py`. Optional browser smoke test:
`node scripts/check-race-mobile.cjs` with Playwright on NODE_PATH and built frontend
preview at port 4175. APIs are intercepted; no real race scores are sent.
