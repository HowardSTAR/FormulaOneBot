FROM node:20-alpine AS front-builder

WORKDIR /front

COPY front/package*.json ./
RUN npm ci --no-audit --no-fund

# Копируем исходники явно (без node_modules/dist из .dockerignore)
COPY front/index.html front/vite.config.ts front/tsconfig*.json ./
COPY front/public ./public
COPY front/src ./src

ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

FROM python:3.11-slim

ARG APP_VERSION=0.1.1
ENV APP_VERSION=$APP_VERSION \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
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
COPY scripts/ ./scripts/
COPY run_web.py .

COPY --from=front-builder /front/dist ./front/dist

RUN mkdir -p logs fastf1_cache data

CMD ["uvicorn", "app.api.miniapp_api:web_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
