# Идеально чистый и быстрый образ на Python
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
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
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код бэкенда
COPY app/ ./app/
COPY run_web.py .

# ВАЖНО: Просто копируем готовую папку web с вашего компьютера
COPY web/ ./web/

# Создаем директории для логов и кэша
RUN mkdir -p logs fastf1_cache data

ENV PYTHONPATH=/app
