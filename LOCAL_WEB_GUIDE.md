# Локальный запуск сайта FormulaOneBot

Эта инструкция запускает только сайт и API с данными Formula 1. Telegram-бот,
`BOT_TOKEN`, Docker и Redis для этого не нужны.

## Что будет запущено

| Адрес | Назначение |
| --- | --- |
| `http://127.0.0.1:5173` | React-сайт с горячим обновлением |
| `http://127.0.0.1:8000` | FastAPI и Swagger: `/docs` |

Vite перенаправляет запросы `/api`, `/assets` и `/static` с `5173` в API на
`8000`, поэтому сайт нужно открывать именно по адресу `5173`.

## Возможности в локальном браузере

Без Telegram доступны главная страница, календарь, следующий этап,
пилоты, команды, результаты, детали гонок и сравнение. Данные загружаются
из FastF1/OpenF1/Jolpica и кэшируются в `fastf1_cache/` и `f1bot_cache/`.
Первый запрос к новому сезону может занимать 10–30 секунд.

Избранное, настройки, голосование и уведомления требуют настоящей подписи
Telegram Mini App, поэтому в обычном браузере они намеренно недоступны.
Если Redis не запущен, API автоматически использует файловый кэш — это
нормально для локальной проверки.

## Windows

1. Установите Python **3.11** и Node.js **20 LTS**. Python 3.11 соответствует
   Docker-окружению проекта.
2. Откройте PowerShell в корне проекта и создайте окружение:

   ```powershell
   py -3.11 -m venv .venv-web
   .\.venv-web\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Установите фронтенд-зависимости:

   ```powershell
   cd front
   npm ci
   cd ..
   ```

4. В первом окне PowerShell запустите API:

   ```powershell
   .\.venv-web\Scripts\Activate.ps1
   python run_web.py
   ```

5. Во втором окне PowerShell запустите сайт:

   ```powershell
   cd front
   npm run dev
   ```

6. Откройте `http://127.0.0.1:5173`.

### Переносимый Node.js в этой рабочей копии

Для текущей Windows-копии уже размещён Node.js в `.tools/`. Если Node.js не
установлен системно, перед `npm ci` и `npm run dev` выполните:

```powershell
$node = "$PWD\.tools\node-v20.19.5-win-x64"
$env:Path = "$node;$env:Path"
```

## macOS

1. Установите Python 3.11 и Node.js 20 LTS (например, через Homebrew):

   ```bash
   brew install python@3.11 node@20
   ```

2. В корне проекта выполните:

   ```bash
   python3.11 -m venv .venv-web
   source .venv-web/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   cd front && npm ci && cd ..
   ```

3. В первом окне Terminal запустите API:

   ```bash
   source .venv-web/bin/activate
   python run_web.py
   ```

4. Во втором окне Terminal запустите фронтенд:

   ```bash
   cd front
   npm run dev
   ```

5. Откройте `http://127.0.0.1:5173`.

## Быстрая проверка

После старта API можно открыть документацию `http://127.0.0.1:8000/docs` или
проверить данные командами:

```bash
# Календарь сезона
curl "http://127.0.0.1:8000/api/season?season=2026"

# Следующий этап
curl "http://127.0.0.1:8000/api/next-race"

# Зачёт пилотов
curl "http://127.0.0.1:8000/api/drivers?season=2026"
```

Перед изменениями полезно выполнить проверки:

```bash
python -m pytest tests/test_api.py -q
cd front && npm run build
```

## Письма Yandex Cloud Postbox

Обычный SMTP-режим использует `postbox.cloud.yandex.net:587` с STARTTLS.
Если провайдер или корпоративная сеть блокирует SMTP, приложение также умеет
отправлять через официальный HTTPS API Postbox на порту 443.

Для HTTPS API создайте **статический ключ доступа** сервисного аккаунта с ролью
`postbox.sender` в том же каталоге Yandex Cloud, где создан почтовый адрес. Это
не тот же ключ, который создаётся специально для SMTP. Добавьте в `.env`:

```env
EMAIL_DELIVERY_MODE=yandex_postbox_api
YANDEX_POSTBOX_ACCESS_KEY_ID=<идентификатор статического ключа>
YANDEX_POSTBOX_SECRET_ACCESS_KEY=<секретная часть статического ключа>
SMTP_FROM_EMAIL=auth@ваш-домен.ru
```

После изменения `.env` полностью перезапустите backend. Если и HTTPS-запрос к
`postbox.cloud.yandex.net:443` зависает, смените сеть, включите VPN или запускайте
отправку на Ubuntu-сервере: это сетевое ограничение Windows/провайдера, а не
ошибка ключа приложения.

## Остановка и типичные проблемы

- Остановить серверы: `Ctrl+C` в каждом окне.
- `Address already in use`: освободите порт `8000` или `5173`, либо завершите
  ранее запущенный `run_web.py`/Vite.
- `node is not recognized`: установите Node.js 20 LTS или воспользуйтесь
  переносимым Node.js из раздела выше.
- Предупреждение `Redis unavailable`: для локального веб-просмотра ничего
  делать не нужно.
- Ошибка данных внешнего провайдера: повторите запрос через несколько секунд;
  API использует несколько источников и файловый кэш как резервный вариант.

## Production-запуск на Ubuntu через Docker Compose

Установите Docker Engine и Compose plugin, затем из каталога проекта выполните:

```bash
cp .env.production.example .env
nano .env
mkdir -p data logs fastf1_cache ssl
chmod 700 data logs fastf1_cache ssl
```

Положите сертификаты домена в `ssl/fullchain.pem` и `ssl/privkey.pem`. Перед
первым запуском обязательно проверьте итоговую конфигурацию:

```bash
docker compose -f docker-compose-build.yml config
docker compose -f docker-compose-build.yml build --pull
docker compose -f docker-compose-build.yml up -d --remove-orphans
docker compose -f docker-compose-build.yml ps
```

Проверка после запуска:

```bash
curl -fsS https://f1hub.ru/health
curl -fsS https://f1hub.ru/api/auth/me -o /dev/null -w '%{http_code}\n'
docker compose -f docker-compose-build.yml logs --tail=100 web bot nginx
```

`/health` должен вернуть `{"status":"ok","database":"ready"}`, а гостевой
`/api/auth/me` — ожидаемый `401`. Для обновления кода повторите `build --pull` и
`up -d --remove-orphans`; SQLite и Redis сохраняются в volumes/bind mounts.

Реальная проверка обоих шаблонов Yandex Postbox из production-контейнера:

```bash
docker compose -f docker-compose-build.yml run --rm web \
  python scripts/test_email.py your-email@example.com --kind both \
  --public-url https://f1hub.ru
```

Команда должна завершиться текстом `accepted`, после чего проверьте входящие,
спам и журнал выполнения Postbox. Если SMTP-порты сервера заблокированы,
переключите `.env` на `EMAIL_DELIVERY_MODE=yandex_postbox_api` и используйте
статический ключ доступа, описанный выше.

Перед обновлением сервера сделайте резервную копию базы:

```bash
docker compose -f docker-compose-build.yml stop bot web
cp data/bot.db "data/bot.db.backup-$(date +%Y%m%d-%H%M%S)"
docker compose -f docker-compose-build.yml start web bot
```
