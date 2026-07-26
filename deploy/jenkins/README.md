# Jenkins CI для FormulaOneBot

Готовая схема:

```text
GitHub push
    |
    v
https://jenkins.f1hub.ru/github-webhook/
    |
    v
Nginx :80/:443  --->  Jenkins 127.0.0.1:8080
                              |
                              v
                    /var/run/docker.sock
                              |
                              v
          Node 20 + Python 3.11 + production image
```

Jenkins постоянно хранит настройки в named volume `f1hub_jenkins_home`.
Порт 8080 привязан только к loopback, поэтому снаружи доступен лишь защищённый
HTTPS-вход через Nginx.

## Важные замечания до начала

1. Пароль `root`, переданный через переписку, следует считать раскрытым. Смените
   его командой `passwd`, добавьте SSH-ключ и после проверки входа по ключу
   отключите парольный вход и прямой вход root.
2. `/var/run/docker.sock` даёт Pipeline фактически root-доступ к серверу.
   Запускайте только доверенный `Jenkinsfile`; не разрешайте автоматические сборки
   Jenkinsfile из fork pull request. В идеале Jenkins должен жить на отдельной CI-VM.
3. Нельзя одновременно запускать host Nginx и контейнер FormulaOneBot Nginx на
   одних `80/443`. На production-сервере сначала выполните:

   ```bash
   sudo ss -ltnp | grep -E ':(80|443)\s'
   docker ps --format 'table {{.Names}}\t{{.Ports}}'
   ```

   Если порты уже занимает production-контейнер F1Hub, не запускайте второй Nginx:
   перенесите его server block в существующий reverse proxy либо используйте
   отдельную CI-VM. Остановка production proxy вслепую приведёт к недоступности
   `f1hub.ru`.
4. По явному требованию конфигурация использует
   `jenkins/jenkins:lts-jdk17`. На июль 2026 это последняя замороженная
   Java-17-совместимая LTS-линия; новые Jenkins LTS требуют Java 21. После
   первичного запуска запланируйте переход на `jenkins/jenkins:lts-jdk21`.

## Состав файлов

- `docker-compose.yml` — Jenkins, loopback-порт и постоянный volume;
- `Dockerfile` — официальный Jenkins + Docker CLI/Compose;
- `plugins.txt` — Pipeline, Git, GitHub, отчёты и Matrix Authorization;
- `nginx-jenkins-bootstrap.conf` — временный HTTP-конфиг для Certbot;
- `nginx-jenkins.conf` — production HTTPS reverse proxy;
- `install-jenkins.sh` — проверка окружения, сборка и запуск;
- `verify-config.sh` — базовая статическая проверка;
- `backup-jenkins.sh` — архив и SHA-256 для `JENKINS_HOME`;
- корневой `Jenkinsfile` — CI проекта.

## 1. DNS

Создайте у DNS-провайдера запись:

```text
Type: A
Name: jenkins
Value: 85.198.68.135
TTL: 300
```

Дождитесь, пока адрес начнёт возвращаться публичным DNS:

```bash
dig +short jenkins.f1hub.ru A
```

Ожидается IP вашего сервера. Сертификат не выпускайте до обновления DNS.

## 2. Безопасный SSH-доступ

На Windows создайте отдельный ключ:

```powershell
ssh-keygen -t ed25519 -a 100 -f "$env:USERPROFILE\.ssh\f1hub-ci"
Get-Content "$env:USERPROFILE\.ssh\f1hub-ci.pub"
```

На сервере создайте не-root пользователя и вставьте public key:

```bash
adduser deploy
usermod -aG sudo deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
nano /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

Проверьте вход в новой консоли:

```powershell
ssh -i "$env:USERPROFILE\.ssh\f1hub-ci" deploy@85.198.68.135
```

Только после успешной проверки создайте `/etc/ssh/sshd_config.d/99-hardening.conf`:

```text
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
```

Проверьте и перечитайте конфигурацию, не закрывая текущую сессию:

```bash
sudo sshd -t
sudo systemctl reload ssh
```

## 3. Docker Engine на Ubuntu 22.04/24.04

Если Docker уже обслуживает F1Hub, не переустанавливайте его — проверьте
`docker version` и `docker compose version`. Для чистого сервера:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker deploy
```

Перезайдите по SSH и проверьте:

```bash
docker version
docker compose version
```

## 4. Получение проекта и запуск Jenkins

Для публичного репозитория:

```bash
sudo mkdir -p /opt/formulaonebot
sudo chown deploy:deploy /opt/formulaonebot
git clone https://github.com/HowardSTAR/FormulaOneBot.git /opt/formulaonebot
cd /opt/formulaonebot/deploy/jenkins
chmod +x install-jenkins.sh verify-config.sh backup-jenkins.sh
./install-jenkins.sh
```

Скрипт сам создаст локальный `.env`, запишет GID группы Docker, проверит
Compose, соберёт образ и выведет первичный пароль. Повторный запуск безопасен.

Полезные команды:

```bash
docker compose ps
docker compose logs --tail=200 jenkins
curl -I http://127.0.0.1:8080/login
docker compose exec --no-TTY jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

Пока Nginx не настроен, Jenkins с другого устройства недоступен — это ожидаемо.

## 5. UFW

Открываются только SSH, HTTP и HTTPS:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8080/tcp
sudo ufw enable
sudo ufw status verbose
```

Порт `8080` не нужно открывать всему интернету: Nginx обращается к нему через
`127.0.0.1`. Публичный доступ с любых устройств осуществляется по 443.
Docker-порты, опубликованные на `0.0.0.0`, могут обходить обычные правила UFW,
поэтому Compose намеренно использует loopback binding.

Если используется облачный firewall, в нём также разрешите TCP 22, 80 и 443.

## 6. Nginx и Let's Encrypt

Эти шаги выполняются, только если host Nginx является единственным владельцем
портов 80/443.

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
cd /opt/formulaonebot/deploy/jenkins
sudo cp nginx-jenkins-bootstrap.conf /etc/nginx/sites-available/jenkins
sudo ln -sfn /etc/nginx/sites-available/jenkins \
  /etc/nginx/sites-enabled/jenkins
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Проверьте HTTP:

```bash
curl -I http://jenkins.f1hub.ru/login
```

Выпустите сертификат:

```bash
sudo certbot --nginx \
  --domain jenkins.f1hub.ru \
  --redirect \
  --agree-tos \
  --no-eff-email \
  --email YOUR_EMAIL
```

После успешного выпуска установите финальный конфиг:

```bash
sudo cp nginx-jenkins.conf /etc/nginx/sites-available/jenkins
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Теперь Jenkins должен открываться по:

```text
https://jenkins.f1hub.ru/
```

В `Manage Jenkins -> System -> Jenkins Location` задайте тот же URL с
завершающим `/`.

## 7. Первый запуск и плагины

1. Откройте `https://jenkins.f1hub.ru/`.
2. Введите первичный пароль, показанный `install-jenkins.sh`.
3. Создайте отдельного администратора с длинным уникальным паролем.
4. Плагины из `plugins.txt` уже включены в образ:

   - Git;
   - Pipeline и Stage View;
   - GitHub и GitHub Branch Source;
   - Credentials Binding и SSH Credentials;
   - JUnit;
   - HTML Publisher;
   - Allure Jenkins Plugin;
   - Matrix Authorization Strategy;
   - AnsiColor, Timestamper и Workspace Cleanup;
   - Pipeline GitHub Notify Step.

5. После первого входа откройте `Manage Jenkins -> Plugins` и установите
   доступные совместимые security updates. Перед крупным обновлением Jenkins
   создайте backup.

## 8. Защита панели

Откройте `Manage Jenkins -> Security`:

1. Security Realm: `Jenkins' own user database`.
2. Снимите `Allow users to sign up`.
3. Authorization: `Matrix-based security`.
4. Добавьте точное имя администратора и дайте ему `Overall/Administer`.
5. У `anonymous` снимите все права.
6. Не выдавайте группе `authenticated` `Overall/Administer`. Для разработчиков
   достаточно `Overall/Read`, `Job/Read`, `Job/Build`, `Job/Cancel` и
   `View/Read`, если это действительно нужно.
7. Сохраните настройки только после того, как строка администратора получила
   `Overall/Administer`, иначе можно заблокировать себе доступ.

Оставьте включёнными CSRF protection и agent-to-controller security. TCP-порт
inbound agents не опубликован и для этого Pipeline не нужен.

## 9. Credentials для GitHub

Репозиторий FormulaOneBot публичный, поэтому checkout может работать без
секрета. Для приватного репозитория предпочтителен read-only deploy key.

### Вариант A: SSH deploy key

На защищённом компьютере:

```bash
ssh-keygen -t ed25519 -C jenkins-formulaonebot -f jenkins_formulaonebot
```

1. Public key добавьте в GitHub:
   `Repository -> Settings -> Deploy keys -> Add deploy key`.
2. Не включайте `Allow write access`.
3. Private key добавьте в Jenkins:
   `Manage Jenkins -> Credentials -> System -> Global`.
4. Kind: `SSH Username with private key`; username `git`;
   ID `github-repo-ssh`.
5. Repository URL в Job:
   `git@github.com:HowardSTAR/FormulaOneBot.git`.

### Вариант B: fine-grained PAT

В GitHub создайте fine-grained token только для FormulaOneBot:

- `Contents: Read`;
- `Metadata: Read`;
- `Commit statuses: Read and write` для статусов `githubNotify`.

В Jenkins добавьте `Username with password`:

- username — GitHub login;
- password — PAT;
- ID — `github-status-token`.

Не кладите PAT, SSH private key, Telegram token или SMTP-пароль в `.env`,
`Jenkinsfile`, Job parameters либо Git. Используйте только Jenkins Credentials.

## 10. Создание Pipeline Job

1. `New Item -> Pipeline`, имя `FormulaOneBot-main`.
2. Включите `GitHub project` и укажите:
   `https://github.com/HowardSTAR/FormulaOneBot/`.
3. В `Build Triggers` включите
   `GitHub hook trigger for GITScm polling`.
4. В `Pipeline` выберите `Pipeline script from SCM`.
5. SCM: Git.
6. Repository URL:
   `https://github.com/HowardSTAR/FormulaOneBot.git`.
7. Credentials — пусто для public checkout либо созданные credentials.
8. Branch Specifier: `*/main`.
9. Script Path: `Jenkinsfile`.
10. Сохраните и один раз нажмите `Build Now`, чтобы Jenkins загрузил
    Jenkinsfile и зарегистрировал `githubPush()` trigger.

Для большого числа веток можно вместо обычного Job создать `Multibranch
Pipeline`. В нём webhook обрабатывает GitHub Branch Source; не разрешайте
автоматический запуск недоверенных fork PR на executor с Docker socket.

## 11. GitHub Webhook

GitHub: `Repository -> Settings -> Webhooks -> Add webhook`:

- Payload URL: `https://jenkins.f1hub.ru/github-webhook/`;
- Content type: `application/json`;
- SSL verification: Enable;
- Events: `Just the push event`;
- Active: включено.

Завершающий `/` в webhook URL обязателен. После сохранения откройте
`Recent Deliveries`: тестовая доставка должна получить ответ `2xx`.

Проверка:

```bash
git commit --allow-empty -m "test: verify Jenkins webhook"
git push origin main
```

Новый build должен появиться автоматически. Если нет:

1. проверьте `Recent Deliveries`;
2. проверьте URL в `Manage Jenkins -> System -> Jenkins Location`;
3. проверьте, что Job использует тот же repository URL;
4. проверьте Nginx:
   `sudo tail -n 200 /var/log/nginx/access.log`;
5. проверьте Jenkins:
   `docker compose logs --tail=300 jenkins`.

## 12. Что делает Jenkinsfile

Pipeline запускается после каждого push и выполняет:

1. `Checkout` — чистый checkout commit/ветки из webhook.
2. `Environment Setup` — проверка Docker, Compose, lock-файлов,
   `app-assets.zip` и создание `reports/`.
3. `Frontend Dependencies` — `npm ci` в `node:20-alpine`.
4. `Frontend Quality` параллельно:
   - ESLint;
   - production Vite build.
5. `Build Application Image` — production Dockerfile, включая распаковку
   `app-assets.zip`.
6. `Python Tests` — все pytest-тесты внутри собранного production image.
7. `Integration Smoke Test` — запуск контейнера и проверка `/health`.
8. `post`:
   - публикация JUnit;
   - архив `reports/**/*` и `front/dist/**/*`;
   - статус Success/Failure в GitHub;
   - удаление временного CI image и очистка workspace.

Frontend пока не содержит отдельного `npm test`, поэтому реальными frontend
quality gates являются ESLint и production build.

## 13. Отчёты

Pytest создаёт:

```text
reports/pytest.xml
```

Шаг `junit` импортирует его в Jenkins. После сборки доступны:

- ссылка `Test Result` на странице build;
- история упавших тестов;
- trend по количеству passed/failed;
- stack trace и имя конкретного теста.

Артефакты также доступны через `Build -> Artifacts`. HTML Publisher и Allure
установлены для будущего расширения, но текущий стабильный отчёт проекта —
стандартный JUnit XML, который не требует изменения тестов.

`tests/test_email.py` — ручной SMTP smoke script и намеренно не отправляет
реальные письма на каждом push. Автоматические auth/email-тесты используют mock
mailer и проверяют регистрацию/восстановление пароля без рассылки.

## 14. Backup и обновление

Создание резервной копии:

```bash
cd /opt/formulaonebot/deploy/jenkins
./backup-jenkins.sh /srv/backups/jenkins
```

Скопируйте архив и `.sha256` за пределы сервера. Проверяйте восстановление на
отдельном Jenkins.

Обновление:

```bash
./backup-jenkins.sh /srv/backups/jenkins
git -C /opt/formulaonebot pull --ff-only
cd /opt/formulaonebot/deploy/jenkins
docker compose build --pull
docker compose up -d
docker compose ps
```

Не выполняйте `docker system prune --volumes`: команда может удалить постоянные
данные Jenkins и других сервисов.

## Официальные источники

- Jenkins Docker:
  https://www.jenkins.io/doc/book/installing/docker/
- Jenkins security:
  https://www.jenkins.io/doc/book/security/managing-security/
- Jenkins credentials:
  https://www.jenkins.io/doc/book/using/using-credentials/
- GitHub Jenkins plugin/webhook:
  https://plugins.jenkins.io/github/
- Docker Engine for Ubuntu:
  https://docs.docker.com/engine/install/ubuntu/
- Certbot:
  https://certbot.eff.org/instructions
