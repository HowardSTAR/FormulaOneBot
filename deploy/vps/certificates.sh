#!/bin/sh
# Run on the VPS after all configured domain names resolve to it; pass contact email.
set -eu
cd /opt/f1hub
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 contact-email" >&2
    exit 2
fi
install -d -m 755 ssl/acme
# Reuse the temporary HTTP entry point if it already serves the website.
if [ "$(docker inspect -f '{{.State.Running}}' formulaonebot-nginx-1 2>/dev/null || true)" != true ] && \
   ! docker container inspect f1hub-acme-bootstrap >/dev/null 2>&1; then
    docker run -d --name f1hub-acme-bootstrap --restart unless-stopped \
        --network formulaonebot_default -p 80:80 \
        -v /opt/f1hub/deploy/vps/nginx-acme.conf:/etc/nginx/conf.d/default.conf:ro \
        -v /opt/f1hub/ssl/acme:/var/www/acme:ro nginx:1.28-alpine
fi
certbot certonly --non-interactive --agree-tos --email "$1" \
    --webroot -w /opt/f1hub/ssl/acme --cert-name f1hub.ru \
    -d f1hub.ru -d www.f1hub.ru -d new.f1hub.ru \
    -d analytics.f1hub.ru -d jenkins.f1hub.ru --expand --keep-until-expiring
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/f1hub-nginx.sh <<'HOOK'
#!/bin/sh
set -eu
[ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/f1hub.ru ] || exit 0
# nginx is started after initial issuance. The complete certificate tree is mounted
# so renewed archive files and live symlinks are visible without copying secrets.
if [ "$(docker inspect -f '{{.State.Running}}' formulaonebot-nginx-1 2>/dev/null)" = true ]; then
    docker exec formulaonebot-nginx-1 nginx -t
    docker exec formulaonebot-nginx-1 nginx -s reload
fi
HOOK
chmod 700 /etc/letsencrypt/renewal-hooks/deploy/f1hub-nginx.sh
systemctl enable --now certbot.timer
if docker container inspect f1hub-acme-bootstrap >/dev/null 2>&1; then
    docker run --rm --network formulaonebot_default \
        -v /opt/f1hub/deploy/vps/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
        -v /opt/f1hub/ssl:/etc/nginx/ssl:ro \
        -v /etc/letsencrypt:/etc/letsencrypt:ro nginx:1.28-alpine nginx -t
    docker rm -f f1hub-acme-bootstrap
fi
docker compose -f docker-compose-build.yml -f deploy/vps/compose.yml up -d --no-build nginx
docker exec formulaonebot-nginx-1 nginx -t
docker exec formulaonebot-nginx-1 nginx -s reload
