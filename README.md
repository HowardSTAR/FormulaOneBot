# 🏎️ FormulaOneBot: Your Ultimate F1 Companion

**[FormulaOneBot](t.me/@turbotearsbot)** — это продвинутая экосистема для фанатов Формулы-1, объединяющая мощь Telegram-бота и интерактивность современного Mini App. Проект позволяет отслеживать результаты гонок, сравнивать пилотов и получать актуальную информацию о сезоне в реальном времени.
<img width="2653" height="3040" alt="image" src="https://github.com/user-attachments/assets/36160bf7-b30b-4221-a586-c2e8d4b3ce7f" />


---

## ✨ Основные возможности

* **📅 Расписание и результаты:** Полный календарь Гран-при с обратным отсчетом до следующей гонки.
* **📊 Сравнение пилотов:** Уникальный функционал сопоставления статистики гонщиков для анализа их формы.
* **🏆 Таблицы чемпионата:** Актуальные данные личного зачета и Кубка конструкторов.
* **📍 Интерактивные трассы:** Встроенные карты автодромов для каждого этапа.
* **📱 Telegram Mini App:** Полноценный веб-интерфейс прямо внутри мессенджера для максимально удобного UX.
* **⭐ Избранное:** Возможность подписываться на любимых пилотов и команды.

---

## 🛠 Технологический стек

Проект построен на базе современной микросервисной архитектуры:

### **Backend**

* **Python 3.10+**: Основной язык разработки.
* **Aiogram 3.x**: Асинхронный фреймворк для Telegram-бота.
* **FastAPI**: Высокопроизводительный API для связи Mini App с данными.
* **SQLAlchemy**: ORM для работы с базой данных (PostgreSQL/SQLite).

### **Frontend (Mini App)**

* **React + TypeScript**: Надежная и типизированная фронтенд-логика.
* **Vite**: Быстрая сборка и горячая перезагрузка.
* **CSS-in-JS / Tailwind**: Современная стилизация интерфейса.

### **Infrastructure**

* **Docker & Docker Compose**: Контейнеризация для быстрого развертывания.
* **Nginx**: Обратный прокси для обслуживания веб-части.

---

## 📸 Интерфейс приложения
<img width="454" height="1000" alt="image" src="https://github.com/user-attachments/assets/64de71cc-4114-4c85-a0b8-e25938e81b97" />

<img width="463" height="823" alt="image" src="https://github.com/user-attachments/assets/f75dd5bd-cafe-4832-9995-c09cc3630ce8" />

<img width="460" height="601" alt="image" src="https://github.com/user-attachments/assets/e14cd7eb-eb76-4729-b612-fb98e0622a11" />

<img width="450" height="821" alt="image" src="https://github.com/user-attachments/assets/27fcdf98-7e86-4178-9161-5be148b828b8" />

---

## 📂 Структура проекта

```text
FormulaOneBot/
├── app/                # Backend логика (Python)
│   ├── api/            # FastAPI эндпоинты для Mini App
│   ├── handlers/       # Обработчики команд Telegram бота
│   ├── utils/          # Вспомогательные инструменты (рендеринг, время)
│   └── bot.py          # Точка входа в бота
├── front/              # Исходный код Mini App (React)
│   └── src/            # Страницы (compare, drivers, next-race)
├── web/                # Статические файлы и шаблоны (возможно уже ушел от этог)
├── assets/             # Изображения пилотов, команд и трасс (2025/2026)
└── docker-compose.yml  # Оркестрация контейнеров

```

---

## 🚀 Быстрый старт

### 1. Подготовка окружения

Клонируйте репозиторий и создайте файл `.env` в корне проекта:

```bash
BOT_TOKEN=your_telegram_bot_token
ADMIN_TELEGRAM_ID=123456789
DATABASE_URL=sqlite+aiosqlite:///./bot.db
WEB_APP_URL=https://your-domain.com

```

### 2. Запуск через Docker

Самый простой способ запустить весь стек (бот + API + фронтенд):

```bash
docker-compose up -d --build

```

### 3. Ручная установка (Dev)

**Backend:**

```bash
pip install -r requirements.txt
python run_web.py

```

**Frontend:**

```bash
cd front
npm install
npm run dev

```

---

## 🔧 Настройка

Данные о пилотах и командах на сезон 2026 уже интегрированы в проект. Вы можете обновить ассеты в папке `app/assets/2026/`, если составы команд изменятся.
