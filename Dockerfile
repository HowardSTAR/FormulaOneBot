FROM python:3.11-slim AS asset-builder
WORKDIR /source
COPY app-assets.zip ./
COPY scripts/pack_assets.py ./scripts/pack_assets.py
RUN python scripts/pack_assets.py --extract --destination /unpacked

FROM node:20-alpine AS race-builder
ENV NODE_OPTIONS=--max-old-space-size=512
WORKDIR /race-game
COPY race-game/package*.json ./
RUN npm ci --no-audit --no-fund
COPY race-game/index.html race-game/tsconfig.json race-game/vite.config.ts ./
COPY race-game/src ./src
COPY --from=asset-builder /unpacked/race-game/public ./public
COPY app/race_tracks.json /app/race_tracks.json
RUN npm run build

FROM node:20-alpine AS front-builder
ENV NODE_OPTIONS=--max-old-space-size=512

WORKDIR /front

COPY front/package*.json ./
RUN npm ci --no-audit --no-fund

# Копируем исходники явно (без node_modules/dist из .dockerignore)
COPY front/index.html front/vite.config.ts front/tsconfig*.json ./
COPY front/public ./public
COPY --from=race-builder /race-game/dist ./public/race-game
COPY front/src ./src
COPY --from=asset-builder /unpacked/front/ ./
# Legal pages import these root-level registers via ../../../../*.md?raw.
# Keep them beside /front, matching the repository layout during Vite build.
COPY THIRD_PARTY_NOTICES.md ASSET_LICENSES.md /

ARG VITE_API_URL=""
ARG VITE_LEGAL_OPERATOR_NAME=""
ARG VITE_LEGAL_OPERATOR_ADDRESS=""
ARG VITE_LEGAL_CONTACT_EMAIL=""
ARG VITE_DATA_STORAGE_LOCATION=""
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_LEGAL_OPERATOR_NAME=${VITE_LEGAL_OPERATOR_NAME} \
    VITE_LEGAL_OPERATOR_ADDRESS=${VITE_LEGAL_OPERATOR_ADDRESS} \
    VITE_LEGAL_CONTACT_EMAIL=${VITE_LEGAL_CONTACT_EMAIL} \
    VITE_DATA_STORAGE_LOCATION=${VITE_DATA_STORAGE_LOCATION}

RUN npm run build:front

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Use HTTPS: CI hosts may be unable to reach Debian mirrors over port 80.
# Retry transient downloads and fail on an incomplete package index.
# Install runtime libraries only. Native Python dependencies have Linux wheels;
# Debian python3-dev would pull a second Python and a large compiler toolchain.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 \
        -o APT::Update::Error-Mode=any update \
    && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 \
        install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --prefer-binary --no-compile -r requirements.txt

COPY --from=asset-builder /unpacked/app/ ./app/
COPY app/ ./app/
COPY run_web.py .

COPY --from=front-builder /front/dist ./front/dist

RUN mkdir -p logs fastf1_cache data

# Release metadata must not invalidate the expensive dependency layers.
ARG APP_VERSION=1.0.0
ENV APP_VERSION=$APP_VERSION
LABEL version=$APP_VERSION

CMD ["uvicorn", "app.api.miniapp_api:web_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
