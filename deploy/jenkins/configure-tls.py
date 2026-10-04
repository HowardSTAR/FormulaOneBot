"""Add Jenkins to the already running container proxy; never start a second nginx."""
from pathlib import Path
import shutil
import subprocess

production = Path('/root/FormulaOneBot')
config = production / 'nginx.conf'
original = config.read_text()
webroot = production / 'ssl/acme'
webroot.mkdir(parents=True, exist_ok=True)
route = '    location ^~ /.well-known/acme-challenge/ {\n        root /etc/nginx/ssl/acme;\n    }\n\n'
http = '''
server {
    listen 80;
    server_name jenkins.f1hub.ru;
    location ^~ /.well-known/acme-challenge/ {
        root /etc/nginx/ssl/acme;
    }
    location / { return 301 https://$host$request_uri; }
}
'''


def install(text):
    # A single-file Docker bind mount follows the original inode: write in place.
    config.write_text(text)
    try:
        subprocess.run(['docker', 'exec', 'formulaonebot-nginx-1', 'nginx', '-t'], check=True)
        subprocess.run(['docker', 'exec', 'formulaonebot-nginx-1', 'nginx', '-s', 'reload'], check=True)
    except Exception:
        config.write_text(original)
        raise


if 'server_name jenkins.f1hub.ru;' in original:
    raise SystemExit('Jenkins proxy already exists; inspect it before changing it.')
updated = original.replace('    location / {', route + '    location / {', 1)
install(updated + http)
subprocess.run(['certbot', 'certonly', '--webroot', '-w', str(webroot),
                '-d', 'jenkins.f1hub.ru', '--cert-name', 'jenkins.f1hub.ru',
                '--non-interactive', '--keep-until-expiring'], check=True)
cert_dir = production / 'ssl/jenkins'
cert_dir.mkdir(exist_ok=True)
for name in ['fullchain.pem', 'privkey.pem']:
    shutil.copy2(Path('/etc/letsencrypt/live/jenkins.f1hub.ru') / name, cert_dir / name)
(cert_dir / 'privkey.pem').chmod(0o600)
https = '''
server {
    listen 443 ssl;
    http2 on;
    server_name jenkins.f1hub.ru;
    ssl_certificate /etc/nginx/ssl/jenkins/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/jenkins/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    client_max_body_size 50m;
    resolver 127.0.0.11 valid=10s ipv6=off;
    location / {
        set $jenkins_upstream http://f1hub-jenkins:8080;
        proxy_pass $jenkins_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_redirect off;
    }
}
'''
install(updated + http + https)
hook = Path('/etc/letsencrypt/renewal-hooks/deploy/f1hub-container.sh')
hook.write_text('''#!/bin/sh
set -eu
case "$RENEWED_LINEAGE" in
 /etc/letsencrypt/live/jenkins.f1hub.ru) target=/root/FormulaOneBot/ssl/jenkins ;;
 /etc/letsencrypt/live/f1hub.ru) target=/root/FormulaOneBot/ssl ;;
 *) exit 0 ;;
esac
cp "$RENEWED_LINEAGE/fullchain.pem" "$target/fullchain.pem"
cp "$RENEWED_LINEAGE/privkey.pem" "$target/privkey.pem"
chmod 600 "$target/privkey.pem"
docker exec formulaonebot-nginx-1 nginx -t
docker exec formulaonebot-nginx-1 nginx -s reload
''')
hook.chmod(0o700)
# The old standalone authenticator conflicts with the running proxy's port 80.
renewal = Path('/etc/letsencrypt/renewal/f1hub.ru.conf')
old = renewal.read_text()
shutil.copy2(renewal, '/root/f1hub-ci/f1hub-renewal-before.conf')
new = old.replace('authenticator = standalone', 'authenticator = webroot')
if '[[webroot_map]]' not in new:
    new += '\nwebroot_path = ' + str(webroot) + ',\n[[webroot_map]]\nf1hub.ru = ' + str(webroot) + '\nwww.f1hub.ru = ' + str(webroot) + '\n'
renewal.write_text(new)
subprocess.run(['systemctl', 'enable', '--now', 'certbot.timer'], check=True)
print('Jenkins HTTPS configured. Certificate renewal uses the existing proxy.')
