# Jenkins CI для FormulaOneBot

Этот комплект поднимает Jenkins в Docker на Ubuntu/Debian, запускает Python 3.11
и Node.js-проверки в одноразовых контейнерах, публикует JUnit/HTML-отчёты и
принимает webhook после каждого `git push`.

Рекомендуемый публичный адрес для текущего проекта:

```text
https://jenkins.f1hub.ru/
```

Архитектура:

```text
GitHub push
    │ HTTPS webhook
    ▼
Nginx :443 ─────► Jenkins 127.0.0.1:8080
                       │
                       ├─► Python 3.11 container → pytest
                       ├─► Node 20 container → ESLint/TypeScript/Vite
                       └─► Docker build + /health smoke test
```

> Jenkins имеет доступ к `/var/run/docker.sock`. Это эквивалентно root-доступу
> к Docker-хосту. Не запускайте Jenkinsfile из недоверенных fork/PR и не
> предоставляйте право изменения Pipeline случайным пользователям.

## 0. Перед началом

Требования:

- Ubuntu 22.04/24.04 либо актуальный Debian;
- минимум 2 CPU, 4 ГБ RAM и 30–50 ГБ свободного диска;
- DNS `A`-запись `jenkins.f1hub.ru` → `85.198.68.135`;
- открытый SSH-доступ;
- репозиторий `HowardSTAR/FormulaOneBot`.

Проверьте DNS с локального компьютера:

```bash
nslookup jenkins.f1hub.ru
```

Ответ должен содержать `85.198.68.135`. Let's Encrypt не выпустит обычный
доменный сертификат, пока DNS не указывает на сервер и порт 80 недоступен.

### Срочная защита SSH

Если пароль сервера когда-либо передавался в чате, тикете или сообщении,
сразу смените его:

```bash
ssh root@85.198.68.135
passwd
```

После этого добавьте SSH-ключ и только после проверки входа ключом отключите
парольный вход. Не закрывайте первую SSH-сессию до проверки второй.

```bash
ssh-keygen -t ed25519 -C "f1hub-admin"
ssh-copy-id root@85.198.68.135
ssh root@85.198.68.135
```

Затем на сервере:

```bash
sudoedit /etc/ssh/sshd_config
```

Установите:

```text
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
```

Проверка и перезагрузка:

```bash
sshd -t
systemctl reload ssh
```

## 1. Проверить, кто уже занимает 80/443

FormulaOneBot содержит production-compose, в котором Dockerized Nginx может
уже публиковать `80:80` и `443:443`. Перед установкой выполните:

```bash
ss -ltnp | grep -E ':(80|443|8080)\b' || true
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Выберите одну топологию:

1. **Рекомендуется:** host-Nginx является единственной точкой входа на 80/443,
   а контейнер приложения и Jenkins слушают разные loopback-порты.
2. **Если edge-Nginx уже работает в Docker:** используйте общий Docker network
   и конфиг `nginx-jenkins-docker-vhost.conf`.

Нельзя одновременно публиковать host-Nginx и Docker Nginx на одни `80/443`.

## 2. Подготовить сервер

Клонируйте проект:

```bash
git clone https://github.com/HowardSTAR/FormulaOneBot.git /opt/FormulaOneBot
cd /opt/FormulaOneBot
chmod +x deploy/jenkins/scripts/*.sh
```

Установите Docker, Nginx, Certbot и UFW:

```bash
sudo bash deploy/jenkins/scripts/bootstrap-host.sh
```

Скрипт:

- подключает официальный Docker apt-репозиторий для Ubuntu/Debian;
- устанавливает Docker Engine, Compose plugin, Nginx и Certbot;
- создаёт `/srv/f1hub-jenkins/home` с UID/GID 1000;
- разрешает `22`, `80`, `443`;
- запрещает внешний доступ к `8080` и `50000`.

Ручной эквивалент firewall:

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8080/tcp
ufw deny 50000/tcp
ufw --force enable
ufw status verbose
```

Порт `8080` **не нужно открывать для всех устройств**: внешний доступ уже
работает через `https://jenkins.f1hub.ru/` на 443. Прямой 8080 обходит TLS и
reverse proxy.

Если UFW не используется, минимальный iptables-вариант:

```bash
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j DROP
iptables -A INPUT -p tcp --dport 50000 -j DROP
```

Для постоянного хранения iptables-правил установите `iptables-persistent`.
Не включайте одновременно несогласованные наборы UFW и ручных iptables-правил.

## 3. Запустить Jenkins

```bash
cd /opt/FormulaOneBot/deploy/jenkins
cp .env.example .env
sudo bash scripts/start-jenkins.sh
```

Скрипт автоматически определит GID `/var/run/docker.sock`, соберёт образ,
запустит Jenkins и напечатает одноразовый начальный пароль.

Ручные проверки:

```bash
docker compose ps
docker compose logs --tail=100 jenkins
curl -I http://127.0.0.1:8080/login
ss -ltnp | grep 8080
```

Ожидается привязка только к `127.0.0.1:8080`, не к `0.0.0.0:8080`.

### Почему Jenkins home — bind mount

`JENKINS_HOME_HOST=/srv/f1hub-jenkins/home` выбран намеренно. Docker daemon
работает на хосте, поэтому путь `-v "$WORKSPACE:/workspace"` должен существовать
именно на хосте. Named volume без преобразования пути привёл бы к пустому
workspace в контейнерах тестов. `Jenkinsfile` преобразует:

```text
/var/jenkins_home/workspace/...  →  /srv/f1hub-jenkins/home/workspace/...
```

## 4. Nginx и бесплатный HTTPS

### Вариант A: host-Nginx владеет 80/443

Убедитесь, что другие Docker-контейнеры не публикуют 80/443, затем:

```bash
sudo bash /opt/FormulaOneBot/deploy/jenkins/scripts/install-nginx.sh \
  jenkins.f1hub.ru admin@f1hub.ru
```

Скрипт создаст временный HTTP-vhost, запросит сертификат Let's Encrypt,
установит production-конфиг `nginx-jenkins.conf` и включит таймер обновления.

Проверка:

```bash
nginx -t
systemctl status nginx --no-pager
certbot certificates
certbot renew --dry-run
curl -I https://jenkins.f1hub.ru/login
```

В `Manage Jenkins → System → Jenkins Location` установите:

```text
Jenkins URL: https://jenkins.f1hub.ru/
```

### Вариант B: 80/443 уже принадлежат Dockerized Nginx FormulaOneBot

Создайте общую сеть:

```bash
docker network create f1hub_edge || true
```

Запустите Jenkins с override:

```bash
cd /opt/FormulaOneBot/deploy/jenkins
docker compose \
  -f docker-compose.yml \
  -f docker-compose.edge.yml \
  up -d --build
```

Подключите существующий контейнер Nginx к сети (имя найдите через `docker ps`):

```bash
docker network connect f1hub_edge FORMULAONEBOT_NGINX_CONTAINER
```

Чтобы подключение переживало `docker compose up --force-recreate`, добавьте
external network `f1hub_edge` в production-compose сервиса `nginx`.

Добавьте содержимое `nginx-jenkins-docker-vhost.conf` в Nginx-конфигурацию
FormulaOneBot, замените `__JENKINS_DOMAIN__` на `jenkins.f1hub.ru` и
перезагрузите контейнер:

```bash
docker exec FORMULAONEBOT_NGINX_CONTAINER nginx -t
docker exec FORMULAONEBOT_NGINX_CONTAINER nginx -s reload
```

Сертификат, смонтированный в edge-Nginx, должен включать:

```text
f1hub.ru
www.f1hub.ru
jenkins.f1hub.ru
```

Если Certbot работает на host, сертификат можно расширить:

```bash
certbot --nginx --cert-name f1hub.ru \
  -d f1hub.ru -d www.f1hub.ru -d jenkins.f1hub.ru
```

Сначала убедитесь, что challenge `/.well-known/acme-challenge/` действительно
доходит до host-Nginx. Если 80 обслуживает контейнер, используйте общий
webroot-volume или DNS challenge у DNS-провайдера.

## 5. Первоначальная настройка Jenkins

Откройте `https://jenkins.f1hub.ru/`, введите начальный пароль и создайте
отдельного администратора. Не используйте пароль Linux root.

Плагины уже устанавливаются из `plugins.txt` при сборке образа:

- Git;
- Pipeline и Pipeline Stage View;
- GitHub и GitHub Branch Source;
- GitLab;
- Bitbucket Branch Source;
- Credentials Binding и SSH Credentials;
- JUnit;
- HTML Publisher;
- Allure Jenkins Plugin;
- Matrix Authorization Strategy;
- AnsiColor, Timestamper, Docker Pipeline, Workspace Cleanup.

Проверить: `Manage Jenkins → Plugins → Installed plugins`.

### Закрыть анонимный доступ и регистрацию

`Manage Jenkins → Security`:

1. Security Realm: `Jenkins' own user database`.
2. Снимите `Allow users to sign up`.
3. Authorization: `Matrix-based security`.
4. Администратору выдайте `Overall/Administer`.
5. Группе `authenticated` при необходимости:
   - `Overall/Read`;
   - `View/Read`;
   - `Job/Read`;
   - `Job/Build`.
6. У `anonymous` не должно быть даже `Overall/Read`.
7. Оставьте CSRF Protection включённой.
8. Сохраните и проверьте доступ в отдельном приватном окне.

Сначала назначьте `Overall/Administer` своему администратору, и только затем
убирайте права anonymous, иначе можно заблокировать собственный доступ.

Создание новых пользователей после отключения signup:
`Manage Jenkins → Users → Create User`. Более гибкая альтернатива —
Role-based Authorization Strategy, но для одного проекта Matrix проще.

## 6. Credentials для закрытого репозитория

### Рекомендуется: read-only SSH Deploy Key

Создайте ключ на защищённой машине, не в Git:

```bash
ssh-keygen -t ed25519 -C "jenkins-formulaonebot" -f jenkins_formulaonebot
cat jenkins_formulaonebot.pub
```

GitHub:

```text
Repository → Settings → Deploy keys → Add deploy key
```

Добавьте public key без `Allow write access`.

Jenkins:

```text
Manage Jenkins → Credentials → System → Global credentials → Add Credentials
Kind: SSH Username with private key
Username: git
Private Key: Enter directly
ID: github-formulaonebot-ssh
```

Repository URL:

```text
git@github.com:HowardSTAR/FormulaOneBot.git
```

### Альтернатива: fine-grained GitHub PAT

Ограничьте токен одним репозиторием:

- `Contents: Read`;
- `Metadata: Read`;
- `Pull requests: Read` для Multibranch;
- `Commit statuses: Read and write`, если статус не отправляет GitHub App.

В Jenkins используйте `Username with password`, где password — PAT. Не
добавляйте PAT в `.env`, URL репозитория, Jenkinsfile или console log.

Для GitLab используйте Project Access Token/Deploy Key с `read_repository`.
Для Bitbucket — Repository Access Token/SSH Access Key только на чтение.

## 7. Создать Pipeline

### Рекомендуется: Multibranch Pipeline для GitHub

1. `New Item → Multibranch Pipeline`.
2. Display name: `FormulaOneBot`.
3. Branch Sources → `GitHub`.
4. Credentials: созданный deploy key/PAT.
5. Repository: `HowardSTAR/FormulaOneBot`.
6. Build Configuration: `by Jenkinsfile`.
7. Script Path: `Jenkinsfile`.
8. Discover branches: включить.
9. PR from forks: не запускать с Docker socket без ручного доверия.
10. Save → `Scan Multibranch Pipeline Now`.

Для обычного `Pipeline`:

1. Definition: `Pipeline script from SCM`.
2. SCM: Git.
3. Repository URL и credentials.
4. Branch: `*/main`.
5. Script Path: `Jenkinsfile`.
6. Включите `GitHub hook trigger for GITScm polling`.

`Jenkinsfile` также содержит declarative trigger `githubPush()`.

## 8. Webhook при каждом git push

### GitHub

Откройте:

```text
Repository → Settings → Webhooks → Add webhook
```

Параметры:

```text
Payload URL: https://jenkins.f1hub.ru/github-webhook/
Content type: application/json
Events: Just the push event
Active: yes
SSL verification: enabled
```

Завершающий `/` в `/github-webhook/` обязателен. После сохранения откройте
`Recent Deliveries`: ping должен получить `2xx`. Выполните тестовый push:

```bash
git commit --allow-empty -m "test: Jenkins webhook"
git push origin main
```

В Jenkins должна автоматически появиться новая сборка.

### GitLab

Установленный `GitLab Plugin` использует не GitHub URL. В Job включите:

```text
Build Triggers → Build when a change is pushed to GitLab
```

Jenkins покажет точный webhook URL и Secret Token. Обычно это:

```text
https://jenkins.f1hub.ru/project/FORMULAONEBOT_JOB_NAME
```

В GitLab: `Settings → Webhooks`, включите `Push events`, SSL verification и
вставьте Secret Token из Jenkins.

### Bitbucket

Для Multibranch используйте `Bitbucket Branch Source`. В репозитории:
`Repository settings → Webhooks → Add webhook`, выберите `Repository push`.
Endpoint зависит от выбранного plugin/job; для классического Bitbucket plugin
обычно используется:

```text
https://jenkins.f1hub.ru/bitbucket-hook/
```

Не направляйте GitLab/Bitbucket payload на `/github-webhook/`: это endpoint
только GitHub plugin.

## 9. Что проверяет Jenkinsfile

Стадии:

1. **Checkout** — `checkout scm` текущей ветки/revision.
2. **Environment Setup** — проверка Docker, обязательных файлов и распаковка
   `app-assets.zip`, необходимая asset-тестам; сборка Python 3.11 CI-образа с
   native build-зависимостями.
3. **Install Dependencies** — `npm ci` и Python virtualenv из
   `requirements-ci.txt`.
4. **Quality & Tests** — ESLint, TypeScript и полный `pytest`.
5. **Build** — Vite production build и production Docker image.
6. **Integration Smoke Test** — запуск образа и проверка `/health`.
7. **post** — публикация отчётов, артефактов и финального статуса.

Секреты production `.env` в CI не используются. Тестовая SQLite создаётся в
`.ci/test.db`. Каталоги `.ci`, `reports`, `front/node_modules` исключены из
Docker build context.

## 10. Отчёты

Pytest генерирует два отчёта:

```text
reports/pytest.xml   — JUnit
reports/pytest.html  — автономный HTML
```

В Jenkins:

- `Test Result` показывает JUnit, число тестов и историю падений;
- `Pytest HTML Report` открывает полный HTML-отчёт;
- `Artifacts` хранит отчёты и `front/dist`.

Публикация выполняется даже при падении тестов благодаря stage-level `post`.

Allure plugin установлен, но по умолчанию pipeline использует JUnit + HTML и
не зависит от внешнего Allure CLI. Чтобы включить Allure:

1. `Manage Jenkins → Tools → Allure Commandline → Add Allure`.
2. Добавьте `allure-pytest` в `requirements-ci.txt`.
3. Добавьте pytest-аргумент `--alluredir=reports/allure-results`.
4. Добавьте в `post always`:

```groovy
allure results: [[path: 'reports/allure-results']]
```

## 11. Уведомление о статусе

Блок `post` явно фиксирует `SUCCESS`, `UNSTABLE` и `FAILURE` в Jenkins log.
GitHub Branch Source автоматически публикует check/commit status при наличии
прав у GitHub App/PAT. Поэтому устаревший `Pipeline: GitHub Notify Step` не
используется и отдельный secret ID в Jenkinsfile не требуется.

Для Telegram/Email-уведомлений используйте Jenkins Credentials и соответствующий
плагин; токены нельзя хранить в репозитории.

## 12. Обслуживание

Обновление Jenkins:

```bash
cd /opt/FormulaOneBot
git pull --ff-only
cd deploy/jenkins
docker compose build --pull
docker compose up -d
docker compose logs --tail=100 jenkins
```

Резервная копия с короткой остановкой Jenkins:

```bash
sudo bash deploy/jenkins/scripts/backup-jenkins.sh /srv/backups/jenkins
```

Проверка диска:

```bash
docker system df
du -sh /srv/f1hub-jenkins/home
```

Безопасная очистка старых неиспользуемых image:

```bash
docker image prune
```

Не запускайте `docker system prune --volumes`: можно удалить постоянные данные
и кэши других сервисов.

## 13. Финальная проверка Definition of Done

```bash
# Снаружи
curl -I https://jenkins.f1hub.ru/login

# На сервере
curl -I http://127.0.0.1:8080/login
ss -ltnp | grep 8080
ufw status verbose
docker compose -f /opt/FormulaOneBot/deploy/jenkins/docker-compose.yml ps
certbot renew --dry-run
```

Проверьте вручную:

- anonymous пользователь не видит dashboard;
- signup выключен;
- admin входит по отдельному паролю Jenkins;
- тестовый `git push` запускает Pipeline;
- pytest, ESLint, TypeScript, build и smoke test зелёные;
- `Test Result` и `Pytest HTML Report` доступны в build;
- GitHub `Recent Deliveries` показывает ответ `2xx`;
- прямой `http://85.198.68.135:8080` недоступен извне.

Официальные справочные материалы:

- https://www.jenkins.io/doc/book/installing/docker/
- https://www.jenkins.io/doc/book/system-administration/reverse-proxy-configuration-with-jenkins/reverse-proxy-configuration-nginx/
- https://plugins.jenkins.io/github/
- https://plugins.jenkins.io/htmlpublisher/
- https://plugins.jenkins.io/allure-jenkins-plugin/
- https://plugins.jenkins.io/matrix-auth/
- https://docs.github.com/en/webhooks/about-webhooks
