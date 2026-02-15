# ==========================================
# Этап 1: Сборка React/Vite фронтенда
# ==========================================
FROM node:20-alpine AS frontend-builder

WORKDIR /build
# Копируем файлы фронтенда
COPY front/package.json front/package-lock.json* ./
RUN npm install

COPY front/ ./
# Собираем проект. Результат появится в папке /build/dist
RUN npx vite build

# ==========================================
# Этап 2: Сборка Python бэкенда
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей (могут понадобиться для matplotlib, Pillow и numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код бэкенда
COPY app/ ./app/
COPY run_web.py .

# Копируем собранный фронтенд из первого этапа туда, где его ждет FastAPI
# В miniapp_api.py указано: WEB_DIR = PROJECT_ROOT / "web" / "app"
RUN mkdir -p web/app
COPY --from=frontend-builder /build/dist/ ./web/app/

# Создаем директории для логов и кэша, чтобы избежать проблем с правами
RUN mkdir -p logs fastf1_cache data

# Устанавливаем часовой пояс по умолчанию (можете изменить)
ENV TZ=UTC

# Запуск по умолчанию (переопределим в docker-compose)
CMD ["python", "-m", "app.main"]