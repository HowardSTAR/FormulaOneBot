#!/usr/bin/env bash
set -Eeuo pipefail
cd "$WORKSPACE"
# Optional, root-managed DNS overrides for routes unavailable from this host.
# Keep hostnames intact so HTTPS certificate validation still applies.
network_args=()
if [[ -f "$CI_SCRIPTS/network.env" ]]; then
  while IFS='=' read -r host address; do
    case "$host" in deb.debian.org|api.telegram.org) ;; *) continue ;; esac
    if [[ ! "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
      echo 'Invalid CI network override address.' >&2
      exit 1
    fi
    network_args+=(--add-host "$host=$address")
  done < "$CI_SCRIPTS/network.env"
fi
case "${1:?stage required}" in
  build)
    test -f app-assets.zip
    test -f Dockerfile
    docker buildx prune --builder default --all --force --max-used-space 512MB --reserved-space 0B
    docker buildx prune --builder f1hub-ci --all --force --max-used-space 1500MB --reserved-space 256MB
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
      "${network_args[@]}" \
      --build-arg "APP_VERSION=$(git rev-parse --short=12 HEAD)" \
      --label ru.f1hub.ci.app=true \
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
        cd ../front
        npm run test:mutations
      '
    ;;
  python)
    mkdir -p .ci-logs .ci-fastf1-cache .ci-f1bot-cache
    docker run --rm --name "f1hub-ci-python-$BUILD_NUMBER" --memory=768m --cpus=1 \
      --user "$(id -u):$(id -g)" -e HOME=/tmp -e BOT_TOKEN=123456:TEST \
      -e ADMIN_IDS=100000001 -e ADMIN_TELEGRAM_ID=100000001 -e ADMIN_EMAIL=ci-admin@example.com \
      -e DATABASE_PATH=/app/data/ci.db -e REDIS_URL= -e APP_ENV=test \
      -e COVERAGE_FILE=/app/reports/.coverage \
      -v "$WORKSPACE/tests:/app/tests:ro" -v "$WORKSPACE/pytest.ini:/app/pytest.ini:ro" \
      -v "$WORKSPACE/.coveragerc:/app/.coveragerc:ro" \
      -v "$WORKSPACE/app-assets.zip:/app/app-assets.zip:ro" \
      -v "$WORKSPACE/scripts:/app/scripts:ro" \
      -v "$WORKSPACE/reports:/app/reports" -v "$WORKSPACE/.ci-data:/app/data" \
      -v "$WORKSPACE/.ci-logs:/app/logs" \
      -v "$WORKSPACE/.ci-fastf1-cache:/app/fastf1_cache" \
      -v "$WORKSPACE/.ci-f1bot-cache:/app/f1bot_cache" \
      -w /app "$APP_IMAGE" pytest --live --test-order-seed=20261005 --cov=app --cov-branch \
        --cov-report=xml:/app/reports/coverage.xml --junitxml=/app/reports/pytest.xml
    # Jenkins has Docker CLI only; use the application's Python for CI tests.
    # No Docker socket is mounted: deployment and cleanup use fake CLI fixtures.
    docker run --rm --name "f1hub-ci-contracts-$BUILD_NUMBER" --memory=128m --cpus=0.5 \
      --user "$(id -u):$(id -g)" -e HOME=/tmp \
      -v "$WORKSPACE/deploy/jenkins:/ci:ro" -w /ci "$APP_IMAGE" sh -ec '
        python test_deploy.py
        python test_cleanup.py
        python test_notify.py
      '
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
      "${network_args[@]}" \
      -e TELEGRAM_BOT_TOKEN -e TELEGRAM_CHAT_ID -e CI_RESULT -e CI_DURATION \
      -e BUILD_NUMBER -e BUILD_URL \
      -v "$CI_SCRIPTS/notify.py:/notify.py:ro" \
      -v "$WORKSPACE/reports:/reports:ro" python:3.11-alpine python /notify.py
    ;;
  cleanup)
    for part in front python contracts smoke deploy; do
      docker rm -f "f1hub-ci-$part-$BUILD_NUMBER" >/dev/null 2>&1 || true
    done
    docker image rm "$APP_IMAGE" >/dev/null 2>&1 || true
    bash "$CI_SCRIPTS/cleanup-images.sh"
    docker buildx prune --builder f1hub-ci --all --force --max-used-space 1500MB --reserved-space 256MB >/dev/null 2>&1 || true
    ;;
  *) echo 'Unknown CI stage' >&2; exit 2 ;;
esac
