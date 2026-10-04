#!/bin/sh
set -eu
cd /root/FormulaOneBot
compose() { docker compose -f docker-compose-build.yml "$@"; }
previous=$(docker inspect formulaonebot-web-1 --format '{{.Image}}')
previous_bot=$(docker inspect formulaonebot-bot-1 --format '{{.Image}}')
test "$previous" = "$previous_bot"
candidate=$(docker image inspect "$APP_IMAGE" --format '{{.Id}}')
if [ "$candidate" = "$previous" ]; then
  printf '{"status":"unchanged"}\n' > /reports/deployment.json
  exit 0
fi
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
    docker tag "$previous" formulaonebot-app:latest
    if compose up -d --no-build --no-deps --wait --wait-timeout 120 bot web && \
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
compose up -d --no-build --no-deps --wait --wait-timeout 120 bot web
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
echo 'Verified image deployed. Previous image remains available for rollback.'
