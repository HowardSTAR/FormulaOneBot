#!/bin/sh
set -eu
cd /root/FormulaOneBot
compose() {
  if [ -f docker-compose.network.yml ]; then
    docker compose -f docker-compose-build.yml -f docker-compose.network.yml "$@"
  else
    docker compose -f docker-compose-build.yml "$@"
  fi
}
previous=$(docker inspect formulaonebot-web-1 --format '{{.Image}}')
previous_bot=$(docker inspect formulaonebot-bot-1 --format '{{.Image}}')
previous_worker=$(docker inspect formulaonebot-worker-1 --format '{{.Image}}' 2>/dev/null || true)
test "$previous" = "$previous_bot"
if [ -n "$previous_worker" ]; then test "$previous" = "$previous_worker"; fi
candidate=$(docker image inspect "$APP_IMAGE" --format '{{.Id}}')
retired=$(docker image inspect formulaonebot-rollback:previous --format '{{.Id}}' 2>/dev/null || true)
if [ "$candidate" = "$previous" ]; then
  printf '{"status":"unchanged"}\n' > /reports/deployment.json
  exit 0
fi
# Check the candidate with the effective production Compose environment before
# changing tags or restarting services. CI's APP_ENV=test smoke check cannot
# catch missing secrets, HTTP origins or insecure mail settings on the host.
printf '%s\n' 'services:' '  web:' "    image: $candidate" | \
  compose -f - run --rm --no-deps --pull never -T --entrypoint python web -c \
  'from app.security import validate_production_security; validate_production_security(); print("Production security configuration validated.")'

docker exec formulaonebot-web-1 python -c '
import os,sqlite3,pathlib
p=pathlib.Path("/app/data/ci-backups"); p.mkdir(exist_ok=True)
src=sqlite3.connect(os.environ.get("DATABASE_PATH","/app/data/bot.db"),timeout=30)
dst=sqlite3.connect(p/"before-last-deploy.db")
with dst: src.backup(dst)
dst.close(); src.close()
'
docker tag "$previous" formulaonebot-rollback:previous
printf '{"status":"deploying"}\n' > /reports/deployment.json
changed=0
rollback() {
  status=$?
  trap - EXIT INT TERM
  if [ "$changed" = 1 ]; then
    echo 'Deploy failed. Restoring the previous application image.' >&2
    # The original release owned schedules in the bot. Never leave a new worker
    # running alongside it when rolling back the first worker deployment.
    compose stop worker || true
    docker tag "$previous" formulaonebot-app:latest
    restore_runtime() {
      if [ -n "$previous_worker" ]; then
        compose up -d --no-build --no-deps --wait --wait-timeout 120 bot web worker
      else
        compose rm -f worker
        # The first pre-worker image cannot import the new heartbeat probe.
        printf '%s\n' 'services:' '  bot:' '    healthcheck:' \
          '      test: ["CMD", "python", "-c", "import os; os.kill(1, 0)"]' | \
          compose -f - up -d --no-build --no-deps --wait --wait-timeout 120 bot web
      fi
    }
    if restore_runtime && \
      docker exec formulaonebot-nginx-1 nginx -s reload; then
      printf '{"status":"rolled_back"}\n' > /reports/deployment.json
    else
      printf '{"status":"rollback_failed"}\n' > /reports/deployment.json
      echo 'ROLLBACK FAILED: administrator intervention required.' >&2
    fi
  fi
  exit "$status"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker tag "$candidate" formulaonebot-app:latest
changed=1
# Stop the old schedule owner before the new one can run. Schema changes in this
# release are additive, allowing the old image to resume if deployment fails.
compose stop bot worker
compose run --rm --no-deps --pull never -T migrate
compose up -d --no-build --no-deps --wait --wait-timeout 120 bot web worker
docker exec formulaonebot-nginx-1 nginx -t
docker exec formulaonebot-nginx-1 nginx -s reload
docker exec formulaonebot-web-1 python -c '
import json,urllib.request
for host in ["f1hub.ru","www.f1hub.ru"]:
 d=json.load(urllib.request.urlopen("https://"+host+"/health",timeout=15))
 assert d["status"]=="ok" and d["database"]=="ready"
'
printf '{"status":"deployed"}\n' > /reports/deployment.json
trap - EXIT INT TERM
if [ -n "$retired" ] && [ "$retired" != "$previous" ] && [ "$retired" != "$candidate" ]; then
  # Remove only the former rollback image, after the new release is healthy.
  docker image rm "$retired" >/dev/null 2>&1 || true
fi
echo 'Verified image deployed. Previous image remains available for rollback.'
