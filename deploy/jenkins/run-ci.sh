#!/usr/bin/env bash
set -Eeuo pipefail
cd "$WORKSPACE"
case "${1:?stage required}" in
  build)
    test -f app-assets.zip
    test -f Dockerfile
    docker builder prune --force --filter until=168h --keep-storage 1GB
    available_kb=$(df -Pk "$WORKSPACE" | awk 'NR==2 {print $4}')
    if (( available_kb < 2500000 )); then
      echo 'Less than 2.5 GB free. Build stopped before production is changed.' >&2
      exit 1
    fi
    args=()
    if [[ -f "$CI_SCRIPTS/build.env" ]]; then
      while IFS='=' read -r key value; do
        [[ "$key" == VITE_* ]] && args+=(--build-arg "$key=$value")
      done < "$CI_SCRIPTS/build.env"
    fi
    docker buildx build --builder f1hub-ci --load --progress plain \
      --build-arg "APP_VERSION=$(git rev-parse --short=12 HEAD)" \
      "${args[@]}" --tag "$APP_IMAGE" .
    ;;
  frontend)
    docker run --rm --name "f1hub-ci-front-$BUILD_NUMBER" --memory=768m --cpus=1 \
      --user "$(id -u):$(id -g)" -e HOME=/tmp -e npm_config_cache=/tmp/npm-cache \
      -e NODE_OPTIONS=--max-old-space-size=512 \
      -v "$WORKSPACE:/workspace" -w /workspace node:22-alpine sh -ec '
        cd front
        npm ci --no-audit --no-fund
        npm run lint -- --ignore-pattern "public/race-game/**"
        node --experimental-strip-types --test \
          --test-reporter=spec --test-reporter-destination=stdout \
          --test-reporter=junit --test-reporter-destination=/workspace/reports/frontend.xml \
          tests/*.test.mjs tests/*.test.ts ../tests/navigation.test.mjs
        cd ../race-game
        npm ci --no-audit --no-fund
        node --test --test-reporter=spec --test-reporter-destination=stdout \
          --test-reporter=junit --test-reporter-destination=/workspace/reports/game.xml tests/*.test.mjs
      '
    ;;
  python)
    mkdir -p .ci-logs .ci-fastf1-cache .ci-f1bot-cache
    docker run --rm --name "f1hub-ci-python-$BUILD_NUMBER" --memory=768m --cpus=1 \
      --user "$(id -u):$(id -g)" -e HOME=/tmp -e BOT_TOKEN=123456:TEST \
      -e ADMIN_IDS=100000001 -e ADMIN_TELEGRAM_ID=100000001 -e ADMIN_EMAIL=ci-admin@example.com \
      -e DATABASE_PATH=/app/data/ci.db -e REDIS_URL= -e APP_ENV=test \
      -v "$WORKSPACE/tests:/app/tests:ro" -v "$WORKSPACE/pytest.ini:/app/pytest.ini:ro" \
      -v "$WORKSPACE/app-assets.zip:/app/app-assets.zip:ro" \
      -v "$WORKSPACE/scripts:/app/scripts:ro" \
      -v "$WORKSPACE/reports:/app/reports" -v "$WORKSPACE/.ci-data:/app/data" \
      -v "$WORKSPACE/.ci-logs:/app/logs" \
      -v "$WORKSPACE/.ci-fastf1-cache:/app/fastf1_cache" \
      -v "$WORKSPACE/.ci-f1bot-cache:/app/f1bot_cache" \
      -w /app "$APP_IMAGE" pytest --junitxml=/app/reports/pytest.xml
    ;;
  smoke)
    name="f1hub-ci-smoke-$BUILD_NUMBER"
    trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
    docker run -d --name "$name" --memory=512m --cpus=0.5 \
      -e BOT_TOKEN=123456:TEST -e REDIS_URL= -e DATABASE_PATH=/app/data/ci.db \
      -e APP_ENV=test "$APP_IMAGE" >/dev/null
    for attempt in $(seq 1 45); do
      if docker exec "$name" python -c \
        'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=3)); assert d["status"]=="ok" and d["database"]=="ready"' \
        >/dev/null 2>&1; then exit 0; fi
      sleep 2
    done
    docker logs --tail=100 "$name"
    exit 1
    ;;
  deploy)
    docker run --rm --name "f1hub-ci-deploy-$BUILD_NUMBER" --network host \
      --memory=128m --cpus=0.5 -e APP_IMAGE -e BUILD_NUMBER \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -v /root/FormulaOneBot:/root/FormulaOneBot \
      -v "$CI_SCRIPTS:/ci:ro" -v "$WORKSPACE/reports:/reports" \
      docker:27-cli sh /ci/deploy-verified.sh
    ;;
  notify)
    docker run --rm --memory=128m --cpus=0.25 \
      -e TELEGRAM_BOT_TOKEN -e TELEGRAM_CHAT_ID -e CI_RESULT -e CI_DURATION \
      -e BUILD_NUMBER -e BUILD_URL \
      -v "$CI_SCRIPTS/notify.py:/notify.py:ro" \
      -v "$WORKSPACE/reports:/reports:ro" python:3.11-alpine python /notify.py
    ;;
  cleanup)
    for part in front python smoke deploy; do
      docker rm -f "f1hub-ci-$part-$BUILD_NUMBER" >/dev/null 2>&1 || true
    done
    docker image rm "$APP_IMAGE" >/dev/null 2>&1 || true
    docker buildx prune --builder f1hub-ci --force --keep-storage 1500MB >/dev/null 2>&1 || true
    ;;
  *) echo 'Unknown CI stage' >&2; exit 2 ;;
esac
