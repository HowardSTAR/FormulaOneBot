FROM python:3.11-slim

# Совпадает с native-зависимостями production Dockerfile и позволяет
# устанавливать Python-пакеты даже при отсутствии готового wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       git \
       libglib2.0-0 \
       libsm6 \
       libxext6 \
       libxrender-dev \
       python3-dev \
       unzip \
    && rm -rf /var/lib/apt/lists/*
