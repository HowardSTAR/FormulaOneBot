#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

for command_name in docker getent; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Ошибка: команда '$command_name' не найдена." >&2
        exit 1
    fi
done

if ! docker compose version >/dev/null 2>&1; then
    echo "Ошибка: установите Docker Compose plugin." >&2
    exit 1
fi

if [[ ! -S /var/run/docker.sock ]]; then
    echo "Ошибка: /var/run/docker.sock отсутствует. Запустите Docker daemon." >&2
    exit 1
fi

docker_gid="$(getent group docker | awk -F: '{print $3}')"
if [[ -z "$docker_gid" ]]; then
    echo "Ошибка: не удалось определить GID группы docker." >&2
    exit 1
fi

if [[ ! -f .env ]]; then
    cp .env.example .env
fi

if grep -q '^DOCKER_GID=' .env; then
    sed -i "s/^DOCKER_GID=.*/DOCKER_GID=${docker_gid}/" .env
else
    printf '\nDOCKER_GID=%s\n' "$docker_gid" >> .env
fi

docker compose config --quiet
docker compose build --pull
docker compose up --detach
docker compose ps

echo
echo "Jenkins запущен только на http://127.0.0.1:8080."
echo "Настройте Nginx и HTTPS по инструкции README.md."
echo "Первичный пароль:"
docker compose exec --no-TTY jenkins \
    cat /var/jenkins_home/secrets/initialAdminPassword
