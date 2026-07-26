#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите скрипт от root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Не удалось определить Linux-дистрибутив." >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release

case "${ID:-}" in
  ubuntu|debian)
    docker_distribution="${ID}"
    ;;
  *)
    echo "Поддерживаются Ubuntu и Debian; обнаружен: ${ID:-unknown}" >&2
    exit 1
    ;;
esac

codename="${VERSION_CODENAME:-}"
if [[ -z "${codename}" ]]; then
  echo "В /etc/os-release отсутствует VERSION_CODENAME." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl git gnupg nginx certbot python3-certbot-nginx ufw

install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/${docker_distribution}/gpg" \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

architecture="$(dpkg --print-architecture)"
cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=${architecture} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${docker_distribution} ${codename} stable
EOF

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
if ss -ltnp | grep -Eq ':(80|443)[[:space:]]'; then
  echo "80/443 уже заняты; host-Nginx установлен, но не запускается автоматически."
  echo "Выберите edge-топологию из deploy/jenkins/README.md."
else
  systemctl enable --now nginx
fi

# Jenkins home принадлежит стандартному пользователю jenkins из контейнера (UID/GID 1000).
install -d -m 0700 -o 1000 -g 1000 /srv/f1hub-jenkins/home

# 8080 и 50000 намеренно не публикуются. Docker Compose дополнительно привязывает
# 8080 к loopback, а веб-доступ идёт только через Nginx.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8080/tcp
ufw deny 50000/tcp
ufw --force enable

echo
echo "Host подготовлен."
docker --version
docker compose version
ufw status
