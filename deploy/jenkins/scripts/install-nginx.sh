#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите от root: sudo bash $0 <domain> <email>" >&2
  exit 1
fi

domain="${1:-}"
email="${2:-}"
if [[ -z "${domain}" || -z "${email}" ]]; then
  echo "Использование: sudo bash $0 jenkins.f1hub.ru admin@f1hub.ru" >&2
  exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jenkins_dir="$(cd -- "${script_dir}/.." && pwd)"
template="${jenkins_dir}/nginx-jenkins.conf"
target="/etc/nginx/sites-available/jenkins"

if ss -ltnp | grep -Eq ':(80|443)[[:space:]]' \
  && ! systemctl is-active --quiet nginx; then
  echo "Порты 80/443 уже заняты не host-Nginx (возможно Docker-контейнером)." >&2
  echo "Не продолжайте: используйте раздел про существующий edge-Nginx в README.md." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx

# Временный HTTP-vhost нужен для ACME challenge и первого сертификата.
cat > "${target}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${domain};

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sfn "${target}" /etc/nginx/sites-enabled/jenkins
nginx -t
systemctl reload nginx

certbot --nginx --non-interactive --agree-tos \
  --email "${email}" --redirect -d "${domain}"

sed "s/__JENKINS_DOMAIN__/${domain}/g" "${template}" > "${target}"
nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer

echo "Jenkins доступен: https://${domain}/"
echo "Проверка продления: certbot renew --dry-run"
