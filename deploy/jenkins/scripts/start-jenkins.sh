#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jenkins_dir="$(cd -- "${script_dir}/.." && pwd)"
cd "${jenkins_dir}"

if [[ ! -S /var/run/docker.sock ]]; then
  echo "Не найден /var/run/docker.sock. Сначала запустите Docker." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
fi
chmod 600 .env

docker_gid="$(stat -c '%g' /var/run/docker.sock)"
sed -i -E "s/^DOCKER_GID=.*/DOCKER_GID=${docker_gid}/" .env

jenkins_home_host="$(sed -n 's/^JENKINS_HOME_HOST=//p' .env | tail -n 1)"
if [[ -z "${jenkins_home_host}" || "${jenkins_home_host}" != /* ]]; then
  echo "JENKINS_HOME_HOST в .env должен быть абсолютным Linux-путём." >&2
  exit 1
fi

if [[ ${EUID} -eq 0 ]]; then
  install -d -m 0700 -o 1000 -g 1000 "${jenkins_home_host}"
else
  mkdir -p "${jenkins_home_host}"
fi

docker compose config >/dev/null
docker compose build --pull
docker compose up -d
docker compose ps

echo
echo "Jenkins слушает только http://127.0.0.1:8080."
echo "Публичный доступ настройте через Nginx и HTTPS."
echo
echo "Начальный пароль (появится после полной загрузки Jenkins):"
for _ in {1..60}; do
  if docker compose exec -T jenkins \
    test -s /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null; then
    docker compose exec -T jenkins \
      cat /var/jenkins_home/secrets/initialAdminPassword
    exit 0
  fi
  sleep 2
done

echo "Пароль пока не создан. Проверьте: docker compose logs -f jenkins" >&2
