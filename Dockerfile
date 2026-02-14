# Используем официальный легкий образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости, которые могут понадобиться для matplotlib и fastf1
RUN apt-get update && apt-get install -y \
    build-essential \
    libfreetype6-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта в контейнер
COPY . .

# Создаем папку для кэша fastf1 (если ее нет)
RUN mkdir -p fastf1_cache

# Указываем команду для запуска бота (замените app/main.py на ваш стартовый файл, если нужно)
# Поскольку PYTHONPATH внутри контейнера может сбоить при запуске из папки,
# мы запускаем как модуль: python -m app.main
CMD ["python", "-m", "app.main"]