#!/bin/sh
# Копируем свежую сборку фронтенда в volume (который монтируется поверх /app/front/dist)
# Иначе volume сохраняет старые файлы между деплоями
if [ -d /app/front_dist_built ] && [ -d /app/front/dist ]; then
  cp -r /app/front_dist_built/. /app/front/dist/
fi
exec "$@"
