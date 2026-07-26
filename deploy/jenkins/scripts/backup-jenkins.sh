#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jenkins_dir="$(cd -- "${script_dir}/.." && pwd)"
cd "${jenkins_dir}"

if [[ ! -f .env ]]; then
  echo "Нет deploy/jenkins/.env. Сначала запустите start-jenkins.sh." >&2
  exit 1
fi

jenkins_home_host="$(sed -n 's/^JENKINS_HOME_HOST=//p' .env | tail -n 1)"
backup_dir="${1:-${jenkins_dir}/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "${backup_dir}"
archive="${backup_dir}/jenkins-home-${timestamp}.tar.gz"

docker compose stop jenkins
trap 'docker compose start jenkins >/dev/null' EXIT
tar -C "${jenkins_home_host}" -czf "${archive}" .
docker compose start jenkins
trap - EXIT

echo "Резервная копия создана: ${archive}"
