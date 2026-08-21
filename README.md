# TurboTears

Open-source motorsport statistics and race companion.

[TurboTears](https://t.me/turbotearsbot) — независимый неофициальный некоммерческий проект с Telegram-ботом и Web/Mini App. Он показывает расписания, результаты, сравнения и аналитику автоспорта.

Проект не является официальным продуктом и не связан с Formula One Group, FIA, командами, гонщиками или организаторами этапов.

## Возможности

- календарь этапов и расписание сессий;
- результаты практик, квалификаций, спринтов и гонок;
- зачёты пилотов и команд;
- сравнение статистики;
- избранное, уведомления, голосования и прогнозы;
- независимые игры «Тест реакции» и Reflex Grid;
- единый профиль сайта и Telegram.

## Статус проекта

TurboTears распространяется как бесплатный некоммерческий фан-проект. До получения отдельных разрешений в проекте не должны появляться подписки, реклама, платные уровни, спонсорская интеграция или продажа доступа к данным.

Гоночные данные агрегируются через независимые сторонние интеграции, включая OpenF1, FastF1 и Jolpica-совместимые API. MIT-лицензия FastF1 относится к коду библиотеки и сама по себе не лицензирует результаты, статистику или timing data.

## Правовая информация

В Web/Mini App доступны публичные маршруты:

- `/privacy` — политика конфиденциальности;
- `/terms` — условия использования;
- `/legal/ip` — уведомление об интеллектуальной собственности и takedown-процедура;
- `/about/data` — источники и ограничения данных;
- `/account/delete` — порядок удаления аккаунта и персональных данных.

Перед production-сборкой заполните фактические реквизиты оператора из `front/.env.example`, проверьте `LEGAL_COMPLIANCE.md` и зарегистрируйте URL собственной Privacy Policy через BotFather.

### Trademark notice

F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V. This project is independent and is not affiliated with or endorsed by Formula One Group.

Текстовые названия чемпионата, этапов, команд и гонщиков используются только в информационном контексте. Лицензия репозитория не распространяется на сторонние товарные знаки, данные или материалы: см. `LICENSE`, `THIRD_PARTY_NOTICES.md` и `ASSET_LICENSES.md`.

## Технологии

- Python 3.11, FastAPI, Aiogram 3, aiosqlite;
- React 19, TypeScript, Vite;
- Redis, Docker Compose, Nginx;
- FastF1, OpenF1 и Jolpica-интеграции.

## Структура

```text
TurboTears/
├── app/                  # bot, API, auth, database and services
├── front/                # React Web / Telegram Mini App
├── tests/                # backend integration and unit tests
├── deploy/jenkins/       # CI deployment configuration
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── ASSET_LICENSES.md
└── LEGAL_COMPLIANCE.md
```

## Локальный запуск

Backend:

```bash
python -m venv .venv
pip install -r requirements.txt
python run_web.py
```

Frontend:

```bash
cd front
npm ci
npm run dev
```

Подробности находятся в `LOCAL_WEB_GUIDE.md`.

## Docker

```bash
docker compose -f docker-compose-build.yml up -d --build
```

Production-сборка получает публичные юридические реквизиты через build args:

```dotenv
LEGAL_OPERATOR_NAME=
LEGAL_OPERATOR_ADDRESS=
LEGAL_CONTACT_EMAIL=
DATA_STORAGE_LOCATION=
```

## Интерфейс приложения

Существующие демонстрационные изображения сохранены без изменения в рамках текущей задачи. Их публикацию и содержимое необходимо проверить вместе с остальными визуальными материалами в отдельном asset-аудите.

<img width="2653" height="3040" alt="TurboTears interface" src="https://github.com/user-attachments/assets/36160bf7-b30b-4221-a586-c2e8d4b3ce7f" />

<img width="454" height="1000" alt="TurboTears interface" src="https://github.com/user-attachments/assets/64de71cc-4114-4c85-a0b8-e25938e81b97" />

## Assets

`app-assets.zip`, фотографии, логотипы и схемы трасс не изменялись в рамках текущего юридического обновления. До завершения отдельной проверки происхождения и лицензий они не считаются очищенными для публичного распространения или production-использования.

## Лицензия

Собственный исходный код лицензирован по MIT. Сторонние имена, товарные знаки, данные, фотографии, шрифты, графика и другие материалы не входят в эту лицензию, если это прямо не указано отдельно.
