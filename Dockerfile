FROM node:20-alpine AS front-builder

WORKDIR /front

COPY front/package*.json ./
RUN npm ci

COPY front/ ./
# Для продакшена: same-origin, API на том же домене (f1hub.ru)
ENV VITE_API_URL=https://f1hub.ru
RUN npm run build

FROM python:3.11-slim

ARG APP_VERSION=0.1.1
ENV APP_VERSION=$APP_VERSION
LABEL version=$APP_VERSION

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY run_web.py .

COPY --from=front-builder /front/dist ./front/dist
COPY web/ ./web/

RUN mkdir -p logs fastf1_cache data

ENV PYTHONPATH=/app
