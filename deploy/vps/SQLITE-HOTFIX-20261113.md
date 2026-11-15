# Prediction scheduler SQLite hotfix

Applied with owner approval on 2026-11-13 (Moscow).

Four saved predictions for 2026 round 20 had no points. The prediction job had
12,238 consecutive failures, with `database is locked` at
`prediction_service.mark_notification_state`. The shared worker connection also
prevented PostHog writes. Independent job connections remained operational.

Prediction state writes and scoring now use isolated `BEGIN IMMEDIATE`
transactions with rollback on failure. PostHog draining uses an independent
connection. Worker startup suppresses historical prediction-result broadcasts
while still calculating their points. Future scheduled notification jobs remain
active. The existing race-day exception and prior workspace changes were kept.

Validation: 123 focused tests passed, including pinned WAL snapshot regressions
for state writes and scoring, and scoring without either notification channel.
After deployment all four round-20 predictions were scored (10–14 points,
37 available), prediction and PostHog jobs succeeded, and no new delivery batches
or sent messages appeared during verification.

Server artifacts:
- Image: `formulaonebot-app:sqlite-fix-20261112`, promoted to `latest`.
- Previous image: `formulaonebot-app:before-sqlite-fix-20261112`.
- SQLite online backup, integrity-checked:
  `/opt/f1hub/data/hotfix-backups/before-sqlite-fix-20261112.db`.
- Original deployed source archive:
  `/opt/f1hub/hotfix-sqlite-20261112/original-source.tar.gz`.

All four app services were recreated from the same image to retain the CI
release consistency invariant. Server source files were updated as well.
The matching fix is committed in the local main branch. Push these commits
before the next CI release so its image retains the hotfix.

## Account activity regression

The 2026-11-15 release exposed the same stale shared-WAL-connection failure in
`record_user_activity`, causing authenticated account/settings requests to return
HTTP 500 while `/health` still passed. Activity writes now use isolated immediate
transactions with rollback; optional site metrics wait at most one second for a
SQLite writer and busy/locked errors cannot abort session authorization. Other
activity errors remain visible. Telegram profile activity uses the same isolated
writer. Session validation/refresh uses its own connection so a shared snapshot
cannot prevent renewal or hide externally revoked sessions.

Regression coverage: `tests/test_activity_sqlite.py` pins a real WAL snapshot,
advances it with another connection, exercises authenticated account/settings/
favorites reads, checks deduplication and bot profile updates, verifies external
session revocation, and tests a real held writer plus CSRF rejection. No new
schema migration is needed.
