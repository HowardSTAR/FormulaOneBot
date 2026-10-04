#!/usr/bin/env bash
set -euo pipefail
umask 077
target=${1:?Full target Git commit is required}
incoming=${2:?Path to official classification snapshot is required}
[[ "$target" =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ "$(realpath "$incoming")" == /root/f1hub-section-tour/2026-16.json ]] || exit 2
[[ "$(sha256sum "$incoming" | cut -d' ' -f1)" == 73e78ba725828542c444b3a5a4cc505a58b4919c6380534c87a158c5d0d4baea ]] || exit 2
cd /root/FormulaOneBot
[[ "$(pwd -P)" == /root/FormulaOneBot ]] || exit 2
exec 9>/root/f1hub-git-update.lock
flock -n 9 || exit 2
export GIT_PAGER=cat GIT_TERMINAL_PROMPT=0
git fetch origin
[[ "$(git rev-parse origin/main)" == "$target" ]] || exit 2
git merge-base --is-ancestor HEAD "$target"
git diff --quiet 2aaa708204ae7ad2b40b2774a7bf5186d3c5f8c3 "$target" -- app requirements.txt Dockerfile docker-compose-build.yml
python3 - <<'PY'
import subprocess
dirty = subprocess.check_output(['git','status','--porcelain','-z']).decode().split('\0')
assert all(not item or item[3:] == 'logs/bot.log' for item in dirty), 'Unexpected server worktree changes'
PY
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/root/f1hub-backups/section-tour-$stamp"
mkdir -p "$backup"
export RELEASE_BACKUP="$backup"
git rev-parse HEAD > "$backup/git-head"
git status --porcelain > "$backup/git-status"
cp -p .env "$backup/environment"
cp -p docker-compose-build.yml "$backup/compose.yml"
python3 - <<'PY'
import os, sqlite3, shutil
from pathlib import Path
root = Path('/root/FormulaOneBot')
backup = Path(os.environ['RELEASE_BACKUP'])
source = sqlite3.connect(f'file:{root / "data/bot.db"}?mode=ro', uri=True)
destination = sqlite3.connect(backup / 'bot.db')
source.backup(destination)
destination.close()
source.close()
snapshots = root / 'fastf1_cache/published_race_results'
if snapshots.exists(): shutil.copytree(snapshots, backup / 'published_race_results')
PY
for service in web bot; do
  image=$(docker inspect "formulaonebot-$service-1" --format '{{.Image}}')
  docker image tag "$image" "formulaonebot-app:section-tour-backup-$service-$stamp"
done
printf 'services:\n  web:\n    image: formulaonebot-app:section-tour-backup-web-%s\n  bot:\n    image: formulaonebot-app:section-tour-backup-bot-%s\n' "$stamp" "$stamp" > "$backup/rollback-compose.yml"
git -c pull.rebase=false pull --ff-only origin main
[[ "$(git rev-parse HEAD)" == "$target" ]] || exit 2
export APP_VERSION="$target"
docker compose -f docker-compose-build.yml config --quiet
echo "Building release $target; backup: $backup"
docker compose -f docker-compose-build.yml -f /root/f1hub-section-tour/mobile-build-compose.yml build web > "$backup/build.log" 2>&1 || { tail -n 70 "$backup/build.log"; exit 1; }
mkdir -p fastf1_cache/published_race_results
install -m 644 "$incoming" fastf1_cache/published_race_results/2026-16.json
rollback() {
  trap - ERR
  echo 'Restoring previous application images.'
  docker compose -f docker-compose-build.yml -f "$backup/rollback-compose.yml" up -d --no-deps --force-recreate --no-build web bot
  docker compose -f docker-compose-build.yml restart nginx
}
trap 'rollback; exit 1' ERR
docker compose -f docker-compose-build.yml up -d --no-deps --force-recreate --no-build web bot
healthy=0
for attempt in $(seq 1 75); do
  web_status=$(docker inspect formulaonebot-web-1 --format '{{.State.Health.Status}}' 2>/dev/null || true)
  bot_status=$(docker inspect formulaonebot-bot-1 --format '{{.State.Health.Status}}' 2>/dev/null || true)
  if [[ "$web_status" == healthy && "$bot_status" == healthy ]]; then healthy=1; break; fi
  sleep 2
done
[[ "$healthy" == 1 ]]
docker compose -f docker-compose-build.yml restart nginx
curl --fail --silent --show-error --retry 6 --retry-delay 2 --retry-connrefused --max-time 15 https://www.f1hub.ru/health
for service in web bot; do
  [[ "$(docker inspect "formulaonebot-$service-1" --format '{{index .Config.Labels "version"}}')" == "$target" ]]
done
trap - ERR
printf '\nDeployed Git commit: %s\nBackup: %s\n' "$target" "$backup"
docker compose -f docker-compose-build.yml ps
