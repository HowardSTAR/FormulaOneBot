#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
    docker compose config --quiet
else
    docker compose --env-file .env.example config --quiet
fi

if grep -R --line-number --extended-regexp \
    '(password|token|secret)[[:space:]]*[:=][[:space:]]*[^$<{[:space:]]+' \
    docker-compose.yml Dockerfile .env.example plugins.txt; then
    echo "Проверьте найденные строки: секреты нельзя хранить в Git." >&2
    exit 1
fi

grep -q '127.0.0.1:${JENKINS_HTTP_PORT:-8080}:8080' docker-compose.yml
grep -q 'server_name jenkins.f1hub.ru;' nginx-jenkins.conf
grep -q 'proxy_pass http://f1hub_jenkins;' nginx-jenkins.conf

echo "Compose, loopback binding и Nginx-конфигурация выглядят корректно."
