# VPS 45.88.177.198

Application directory: `/opt/f1hub`. Ubuntu 24.04, Docker Compose,
2 GiB swap. The production image contains both frontend variants. The public
site retains the existing `legacy` variant; `web-new` serves the new interface on `new.f1hub.ru`.

The deployment uses a new server-only `.env`. The database was restored from
`backup_20261029T030040376960Z.db.gz` (2026-10-29 03:00 UTC), containing 87 users
and 81 active Telegram recipients. The owner-provided
Telegram token is configured for web, bot and worker. Admin Telegram ID: `2099386`.
SMTP credentials remain absent, so email verification/reset requires later setup.
Bot polling and the full app.worker scheduler are enabled at the owner's request.
Race/session reminders, prediction opening/closing/results, background calculations,
analytics delivery and automatic backups now run. Recipient sound preferences and
quiet hours remain respected. The earlier constrained runner is retained as an
optional fallback file but is not the active worker command.

Preserve the existing `AUTH_PEPPER` with the database. Stop the old bot and worker
before starting their replacements; do not copy an open SQLite database with
`cp` (use SQLite online backup or stop all writers).

Releases are built from GitHub main by the trusted Jenkins Pipeline. A normal
manual build runs tests only; select DEPLOY to promote a manually started build.
GitHub changes detected by Poll SCM deploy automatically after successful checks.
Do not retag the production image manually while a deployment is running.

Once `f1hub.ru`, `www.f1hub.ru`, `new.f1hub.ru`, `analytics.f1hub.ru` and
`jenkins.f1hub.ru` resolve to the new VPS and TCP 80/443 are reachable, issue
certificates (the bootstrap needs port 80 free on first installation):

```sh
export APP_VERSION=latest
docker compose -f docker-compose-build.yml -f deploy/vps/compose.yml up -d --no-build web web-new
sudo ./deploy/vps/certificates.sh operator@example.com
```

Start the website, Redis, bot and broadcast-only worker (migration runs automatically):

```sh
export APP_VERSION=latest
docker compose -f docker-compose-build.yml -f deploy/vps/compose.yml up -d --no-build
docker compose -f docker-compose-build.yml -f deploy/vps/compose.yml ps
curl --fail https://f1hub.ru/health
sudo certbot renew --dry-run --run-deploy-hooks --no-random-sleep-on-renew
systemctl list-timers certbot.timer
```

Certbot renews through the system timer. HTTP ACME challenges stay accessible
through nginx. The deploy hook validates and reloads the running proxy after
renewal. `/etc/letsencrypt` is mounted read-only as a complete tree, including the
archive targeted by live symlinks. Keep HTTP 80 reachable for future renewals.
Redis and application containers have no published ports; nginx publishes 80/443.
Data, logs and caches persist outside containers. Automatic restart uses the
Docker daemon and each service's `unless-stopped` policy.

The full scheduler was explicitly enabled by the owner on 2026-11-08.
The new AUTH_PEPPER remains in use. Existing passwords and sessions are
independent of it; previously issued one-time codes may no longer validate. The old server is
not modified by this deployment.

`https://jenkins.f1hub.ru/` now proxies a new secured Jenkins controller.
Its Compose definition and first-start initialization live in `deploy/vps/jenkins`.
There is no imported build history. `F1Hub-main` polls GitHub main every two
minutes and deploys after successful build/tests; manual runs test only unless
DEPLOY is selected. Telegram results go only to administrator 2099386. Registration and anonymous
access are disabled. Admin credentials are in `/root/f1hub-ci/login.txt` (0600),
with a local ignored copy at `secrets/jenkins-login.txt`. The controller has 1 CPU,
a 1 GiB memory limit and a 512 MiB Java heap. At the owner's explicit request, it now has the host Docker socket and matching
Docker group access. Pipeline code is installed root-owned in `/opt/f1hub-ci`
and mounted read-only. Only trusted main is eligible for automatic deployment.
The controller uses the persistent `f1hub_jenkins_home` volume; do not remove it.
If restoring an older home volume, remove the first-start init mount first.

`https://analytics.f1hub.ru/` redirects (302, not cached) to the previously selected
PostHog Cloud EU project `https://eu.posthog.com/project/293486/`.
The owner-provided POSTHOG_PROJECT_KEY is now stored privately in the VPS .env.
Web services enqueue events and the constrained worker flushes every 15 seconds.
A technical f1hub_deployment_check event was accepted by PostHog and the pending
queue was empty after verification. See deploy/posthog/README.md.

Verified on 2026-11-08: all five DNS names resolve to 45.88.177.198; the live
certificate covers all five names and expires 2027-02-06. Certbot's dry-run with
deploy hooks succeeded. External HTTPS requests verified main/preview HTML,
referenced JS/CSS and database health. Jenkins now serves its secured login
and analytics redirects to the PostHog Cloud project.

Broadcast workflow in the private bot chat (admin only):

```text
/broadcast Your message text
/button ❤️ Поддержать на Boosty | https://boosty.to/turbotears
```

The admin receives a preview and confirms the audience with the send button.
Delivery targets all active users registered in the current database, including
users with notifications disabled (those recipients receive silent messages).
Quiet hours and Telegram client mute settings still apply. No broadcast was
created as part of deployment. The previous database is now imported. Password hashes and sessions do not
depend on AUTH_PEPPER; one-time email/link codes may need to be requested again.

Validation: 92 targeted tests passed, including an isolation check that a
broadcast-only drain leaves non-broadcast notifications pending.

Nginx health probes use HTTP /health with the explicit Host f1hub.ru. HTTPS
connections with unknown SNI (including 127.0.0.1) are intentionally rejected;
external TLS is verified separately using the public domain names.

Database restore on 2026-11-08: the supplied compressed archive matched manifest
SHA-256 `532b183c8de0bd6c769b6a2f9ae375f4eaa911914c67f059df874dc60cbcb066`.
Local and server SQLite integrity/foreign-key checks passed, and isolated
migrations succeeded. No pending/retry/sending outbound deliveries were present;
previous sent/failed/blocked/unknown statuses remain unchanged. All writers were
stopped before replacing the database. The pre-import database is retained at
`/opt/f1hub/restore-20261029/before-import.db`; the original archive and the
restore-result.json report are in the same root-only directory. The source
backup reflects October 29; later changes from the old server are not included.

Service endpoint verification on 2026-11-08: Jenkins authenticated whoAmI returned
f1hub-admin, security was enabled and the job list was empty. Docker host access was subsequently authorized for autodeployment. Nginx configuration passed validation before reload. The analytics
host returns the intended redirect to the existing cloud project.

CI runtime on the new VPS: `APP_VERSION=latest` is a stable runtime tag initially
seeded from the currently running image. Before promotion, candidate production
settings are validated through the effective base+VPS Compose configuration.
Each deploy creates and integrity-checks data/ci-backups/before-last-deploy.db,
retains the previous image and restores that image if rollout/health fails.
User data is never automatically rolled back. The VPS Compose overlay is used
for preflight, deploy and rollback, preserving SSL routing and worker policy.
The CI builder is limited to one CPU, 1 GiB RAM and 512 MiB additional swap;
only one build step runs at a time and its cache is bounded. Automated tests use
an isolated database and fake bot credentials; external live API tests are opt-in.
The new Jenkinsfile has no daily timers and no outbound reports to regular users.
GitHub is polled every 2 minutes; no webhook secret is needed for this setup.
Root-only login.txt can be used with Jenkins Script Console for CI maintenance.

The Jenkins administrator password was changed to the owner-provided value;
root and ignored local login.txt files were updated without interrupting builds.

Final CI verification on 2026-11-08: F1Hub-main build #1 completed SUCCESS.
Application image build, frontend/game checks, backend tests, deployment-contract
checks and isolated candidate startup succeeded. The manual control run did not
promote an image. Telegram confirmed delivery of the result to admin 2099386.
The candidate also passed a separate production-environment preflight using the
actual VPS Compose overlay without starting or replacing the application.

Race-day exception: `PREDICTION_RACE_DAY_EXCEPTION=2026:20:2026-11-08` and
`PREDICTION_RACE_DAY_EXCEPTION_UNTIL=2026-11-08T17:00:00Z`. Only Sao Paulo round 20
can accept forecasts until race start (20:00 Moscow). Other stages retain normal
FP1-to-qualifying rules. The API rechecks the cutoff under its DB write lock.
The deadline expires automatically; no cron or manual closing action is needed.
CI preflight refuses to promote a candidate that removes this active exception
until the configured cutoff has passed. Both UI variants show the explanation and
an accessible, server-clock-adjusted countdown. Existing preserved UI layout is
retained; only its deadline copy and static module names are patched at build.
Original legacy/public-frontend.tar.gz remains untouched.

Release race-day-20261108 was promoted with a verified database backup and image
rollback protection. Prediction/race-day/closing/result tests passed (72 checks),
then 46 focused exception/standard-window/deploy checks passed; TypeScript and
changed-page ESLint passed. Browser checks verified both variants, two viewport
sizes, driver choice and decreasing countdown without runtime errors.
The one-time invitation key is prediction:race-day-open:2026:20:2026-11-08;
its audience is frozen at 81 and pending deliveries expire at race start.

Announcement verification: 63 deliveries confirmed; 16 recipients blocked the bot,
one recipient is a bot account with bot-to-bot messaging disabled, and one chat
was not found. There are no pending/retry deliveries for this invitation.
The full worker command is python -m app.worker, with 20 registered jobs.
Light/dark browser renders were inspected; both public and preview driver pickers
remained editable before the cutoff and the timer decreased without page errors.
