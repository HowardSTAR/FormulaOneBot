import os
import sqlite3
import datetime
import logging
from pathlib import Path
from app.db import DB_PATH  # Путь к вашей базе данных

logger = logging.getLogger(__name__)

# Папка для бэкапов (на уровень выше app)
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "backups"


def create_backup():
    """
    Создает SQL-дамп и удаляет старые копии, оставляя только 2 последние.
    """
    try:
        BACKUP_DIR.mkdir(exist_ok=True)

        # 1. Создаем новый бэкап
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        new_backup_filename = f"backup_{timestamp}.sql"
        new_backup_path = BACKUP_DIR / new_backup_filename

        con = sqlite3.connect(DB_PATH)
        with open(new_backup_path, 'w', encoding='utf-8') as f:
            for line in con.iterdump():
                f.write('%s\n' % line)
        con.close()

        logger.info(f"Бэкап создан: {new_backup_filename}")

        # 2. Удаляем старые, оставляем только 2 (свежий + предыдущий)
        clean_old_backups(keep=2)

    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа: {e}")


def clean_old_backups(keep: int):
    """
    Удаляет старые файлы из папки, оставляя 'keep' самых новых.
    """
    try:
        # Получаем список всех .sql файлов в папке
        files = list(BACKUP_DIR.glob("backup_*.sql"))

        # Если файлов меньше или равно лимиту, ничего не делаем
        if len(files) <= keep:
            return

        # Сортируем файлы по времени изменения (от старых к новым)
        # os.path.getmtime возвращает время последней модификации
        files.sort(key=lambda f: os.path.getmtime(f))

        # Вычисляем, сколько файлов нужно удалить
        # Например: 5 файлов, keep=2 -> удаляем 3 первых (самых старых)
        files_to_delete = files[:-keep]

        for file_path in files_to_delete:
            file_path.unlink()  # Удаляем файл
            logger.info(f"Удален старый бэкап: {file_path.name}")

    except Exception as e:
        logger.error(f"Ошибка при очистке старых бэкапов: {e}")