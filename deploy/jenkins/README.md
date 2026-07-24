# Jenkins для FormulaOneBot

Комплект запускает Jenkins 24/7 в Docker, хранит состояние в named volume и
предоставляет Docker CLI для сборок через сокет Docker хоста.

> **Важно:** доступ к `/var/run/docker.sock` фактически даёт Jenkins права root
> на Ubuntu-хосте. Разрешайте запуск Pipeline только доверенным веткам и не
> выполняйте Jenkinsfile из непроверенных pull request от форков.

## 1. Подготовка чистого Ubuntu Server

Команды рассчитаны на Ubuntu 22.04/24.04 и выполняются пользователем с `sudo`.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Перезайдите по SSH, затем проверьте:

```bash
docker version
docker compose version
```

Клонируйте репозиторий и подготовьте конфигурацию:

```bash
git clone git@github.com:YOUR_ORG/FormulaOneBot.git
cd FormulaOneBot/deploy/jenkins
cp .env.example .env
docker_gid="$(getent group docker | cut -d: -f3)"
sed -i "s/^DOCKER_GID=.*/DOCKER_GID=${docker_gid}/" .env
docker compose config
docker compose up -d --build
docker compose ps
```

Первичный пароль:

```bash
docker compose exec jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

Откройте Jenkins, создайте администратора и установите recommended plugins.
В `Manage Jenkins → System → Jenkins Location` задайте публичный HTTPS URL.

Резервная копия всех настроек:

```bash
docker run --rm \
  -v f1hub_jenkins_home:/source:ro \
  -v "$PWD:/backup" \
  alpine tar czf /backup/jenkins-home-$(date +%F).tar.gz -C /source .
```

## 2А. Публичный домен, Nginx и Let's Encrypt

1. Создайте DNS `A`/`AAAA` запись `jenkins.example.com` на сервер.
2. Разрешите только SSH/HTTP/HTTPS. Порт 8080 остаётся закрытым:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

3. Установите Nginx и Certbot:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

4. Для первого сертификата создайте временный HTTP-конфиг:

```bash
sudo tee /etc/nginx/sites-available/jenkins >/dev/null <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name jenkins.example.com;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
sudo ln -s /etc/nginx/sites-available/jenkins /etc/nginx/sites-enabled/jenkins
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d jenkins.example.com
```

5. Замените временный файл содержимым
[`nginx-jenkins.conf`](./nginx-jenkins.conf), подставьте домен и проверьте:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Для дополнительной защиты рекомендуется Cloudflare Access, VPN либо allowlist
адресов в Nginx. Обязательно отключите анонимный доступ в
`Manage Jenkins → Security`.

## 2Б. Доступ без белого IP

### Cloudflare Tunnel

После добавления домена в Cloudflare:

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
cloudflared tunnel login
cloudflared tunnel create jenkins
cloudflared tunnel route dns jenkins jenkins.example.com
```

`/etc/cloudflared/config.yml`:

```yaml
tunnel: TUNNEL_UUID
credentials-file: /root/.cloudflared/TUNNEL_UUID.json
ingress:
  - hostname: jenkins.example.com
    service: http://127.0.0.1:8080
  - service: http_status:404
```

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

В Cloudflare Zero Trust добавьте Access Policy (email/SSO + MFA). Порты 80,
443 и 8080 при таком варианте открывать не требуется.

### Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg http://127.0.0.1:8080
tailscale serve status
```

Jenkins будет доступен только участникам tailnet по HTTPS-адресу, который
покажет `tailscale serve status`.

## 3. GitHub credentials и плагины

### Предпочтительно: SSH deploy key

```bash
ssh-keygen -t ed25519 -C jenkins-formulaonebot -f jenkins_github
cat jenkins_github.pub
```

Добавьте public key в GitHub:
`Repository → Settings → Deploy keys → Add deploy key`. Write access для
checkout не нужен. В Jenkins:
`Manage Jenkins → Credentials → System → Global → SSH Username with private key`;
ID, например, `github-repo-ssh`, username `git`, private key — содержимое
`jenkins_github`.

### Альтернатива: fine-grained PAT

В GitHub откройте `Settings → Developer settings → Personal access tokens →
Fine-grained tokens`, ограничьте токен одним репозиторием и выдайте:

- `Contents: Read`;
- `Metadata: Read`;
- `Commit statuses: Read and write`;
- `Pull requests: Read` для Multibranch Pipeline.

Сохраните его в Jenkins как `Username with password` или `Secret text`.
Рекомендуемый ID для статусов из приложенного Jenkinsfile:
`github-status-token`. Не помещайте PAT в `.env` или репозиторий.

Установите через `Manage Jenkins → Plugins`:

- Pipeline;
- Git и GitHub;
- GitHub Branch Source (для PR/Multibranch);
- Credentials Binding;
- JUnit;
- AnsiColor;
- Pipeline: GitHub Notify Step (шаг `githubNotify`).

Перезапустите Jenkins после установки обновлений плагинов.

## 4. Job и GitHub Webhook

Рекомендуется создать `New Item → Multibranch Pipeline`:

1. Branch source — GitHub, repository HTTPS/SSH URL и созданные credentials.
2. Build configuration — `by Jenkinsfile`, Script Path: `Jenkinsfile`.
3. Включите discovery веток и PR согласно политике доверия.
4. Для PR из форков не передавайте секреты и не разрешайте Docker socket
   непроверенному Jenkinsfile.

В GitHub откройте `Repository → Settings → Webhooks → Add webhook`:

- Payload URL: `https://jenkins.example.com/github-webhook/`
  (завершающий `/` обязателен);
- Content type: `application/json`;
- Secret: сгенерированная случайная строка, если выбранный Jenkins/GitHub
  trigger поддерживает проверку webhook secret;
- Events: `Pushes` и `Pull requests`;
- Active: включено.

После сохранения проверьте `Recent Deliveries`: ответ должен быть `2xx`.
В обычном Pipeline включите `GitHub hook trigger for GITScm polling`; в
Multibranch Pipeline события обрабатывает GitHub Branch Source.

## 5. Что делает Jenkinsfile

- checkout текущей ветки или merge revision PR через `checkout scm`;
- проверка Docker/Compose и обязательных файлов;
- установка npm/pip-зависимостей с named-volume кэшами;
- параллельный ESLint и pytest с JUnit XML;
- параллельная Vite-сборка и сборка production Docker image;
- smoke test `/health` в одноразовом контейнере;
- публикация JUnit и артефактов `front/dist`;
- статус commit через `githubNotify`;
- опциональный Telegram alert через Jenkins Credentials.

Первый прогон скачивает образы и зависимости, следующие используют Docker/npm/
pip кэши. Периодически очищайте только неиспользуемые данные:

```bash
docker system df
docker image prune
```

Не запускайте `docker system prune --volumes`: он может удалить кэши и
постоянные данные других Docker-сервисов.
