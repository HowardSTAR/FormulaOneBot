import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

# Импорты FastAPI
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Импорты из твоего проекта
from app.handlers.races import build_next_race_payload
from app.f1_data import (
    get_season_schedule_short_async,
    get_weekend_schedule,
    get_driver_standings_async,
    get_constructor_standings_async, _get_latest_quali_async, get_race_results_async,
)
from app.db import (
    get_favorite_drivers, get_favorite_teams,
    remove_favorite_driver, add_favorite_driver,
    remove_favorite_team, add_favorite_team
)
from app.auth import get_current_user_id


# --- Настройка путей ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
WEB_DIR = PROJECT_ROOT / "web" / "app"
STATIC_DIR = WEB_DIR / "static"

print(f"DEBUG: WEB_DIR = {WEB_DIR}")

# --- Инициализация приложения ---
web_app = FastAPI(title="FormulaOneBot Mini App API")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    web_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- ЭНДПОИНТЫ ---

@web_app.get("/api/next-race")
async def api_next_race(season: Optional[int] = None):
    """Информация о ближайшей гонке + таймер (исправленная версия)."""
    data = await build_next_race_payload(season)

    if data.get("status") != "ok":
        return data

    try:
        current_season = data["season"]
        round_num = data["round"]

        # Загружаем расписание
        sessions = await asyncio.to_thread(get_weekend_schedule, current_season, round_num)

        if not sessions:
            print(f"DEBUG: Сессии не найдены.")
            return data

        now_utc = datetime.now(timezone.utc)
        sorted_sessions = []

        print(f"DEBUG: Найдено {len(sessions)} сессий. Парсим...")

        for s in sessions:
            dt = None

            # --- ВАРИАНТ 1: Если есть готовый объект datetime ---
            if isinstance(s.get("date"), datetime):
                dt = s["date"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

            # --- ВАРИАНТ 2: Парсим 'utc' (если там полная дата) ---
            elif s.get("utc") and len(str(s["utc"])) > 12:
                try:
                    clean_str = str(s["utc"]).replace(" UTC", "").replace("Z", "").strip()
                    dt = datetime.strptime(clean_str, "%d.%m.%Y %H:%M")
                    dt = dt.replace(tzinfo=timezone.utc)
                except:
                    pass

            # --- ВАРИАНТ 3: Парсим 'local' (Там точно есть дата!) ---
            # Формат: "06.03.2026 04:30 MCK" или просто "06.03.2026 04:30"
            if dt is None and s.get("local"):
                local_str = str(s["local"])
                try:
                    # Берем первые две части: "06.03.2026 04:30"
                    # split(' ') разбивает по пробелам. Берем [0] и [1] и соединяем.
                    parts = local_str.split()
                    if len(parts) >= 2:
                        date_time_str = f"{parts[0]} {parts[1]}"  # "06.03.2026 04:30"

                        # Парсим как Московское время
                        dt_msk = datetime.strptime(date_time_str, "%d.%m.%Y %H:%M")

                        # Руками вычитаем 3 часа, чтобы получить UTC
                        # (так надежнее, чем возиться с pytz)
                        dt = dt_msk - timedelta(hours=3)
                        dt = dt.replace(tzinfo=timezone.utc)
                except Exception as e:
                    print(f"DEBUG: Ошибка парсинга local '{local_str}': {e}")
                    pass

            if dt:
                sorted_sessions.append({
                    "name": s.get("name", "Session"),
                    "dt": dt
                })
            else:
                # Если все варианты не сработали
                print(f"DEBUG: Пропускаем сессию, нет полной даты. Raw: utc='{s.get('utc')}', local='{s.get('local')}'")

        # Сортируем и ищем ближайшую
        sorted_sessions.sort(key=lambda x: x["dt"])

        next_session = None
        for s in sorted_sessions:
            if s["dt"] > now_utc:
                next_session = s
                break

        if next_session:
            name_map = {
                "Practice 1": "Практика 1",
                "Practice 2": "Практика 2",
                "Practice 3": "Практика 3",
                "Qualifying": "Квалификация",
                "Sprint": "Спринт",
                "Sprint Qualifying": "Спринт-квалификация",
                "Race": "Гонка",
            }
            ru_name = name_map.get(next_session["name"], next_session["name"])

            data["next_session_name"] = ru_name
            data["next_session_iso"] = next_session["dt"].strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"DEBUG: Таймер установлен на: {ru_name} -> {data['next_session_iso']}")

    except Exception as e:
        print(f"ERROR: {e}")

    return data


@web_app.get("/api/season")
async def api_season(season: Optional[int] = Query(None)):
    """Календарь гонок."""
    if season is None:
        season = datetime.now().year
    races = await get_season_schedule_short_async(season)
    return {"season": season, "races": races}


@web_app.get("/api/weekend-schedule")
async def api_weekend_schedule(
        season: Optional[int] = Query(None),
        round_number: int = Query(..., description="Номер этапа"),
):
    """Детальное расписание уикенда (берем готовые строки, как в боте)."""
    if season is None:
        season = datetime.now().year

    # Получаем список словарей (точно такой же, как в races.py)
    # Ожидаем структуру: {'name': 'Practice 1', 'local': '06.03.2026 04:30', 'utc': '...'}
    raw_sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)

    clean_sessions = []

    # Маппинг имен
    name_map = {
        "Practice 1": "Практика 1",
        "Practice 2": "Практика 2",
        "Practice 3": "Практика 3",
        "Qualifying": "Квалификация",
        "Sprint": "Спринт",
        "Sprint Qualifying": "Спринт-квалификация",
        "Race": "Гонка",
    }

    if raw_sessions:
        for s in raw_sessions:
            # 1. Берем имя
            raw_name = s.get("name", "Session")
            name_ru = name_map.get(raw_name, raw_name)

            # 2. Берем готовую строку времени (МСК), как в боте
            # Она выглядит примерно так: "06.03.2026 04:30"
            local_str = s.get("local", "")

            date_str = "??"
            time_str = "??"

            # 3. Разрезаем строку на дату и время
            if local_str:
                parts = local_str.split()  # Делим по пробелу
                if len(parts) >= 2:
                    date_str = parts[0]  # "06.03.2026"
                    time_str = parts[1]  # "04:30"
                elif len(parts) == 1:
                    date_str = parts[0]

            clean_sessions.append({
                "name": name_ru,
                "date": date_str,
                "time": time_str
            })

    return {"season": season, "round": round_number, "sessions": clean_sessions}


@web_app.get("/api/drivers")
async def api_drivers(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Личный зачет пилотов."""
    user_id = None
    if x_telegram_init_data:
        try:
            user_id = await get_current_user_id(x_telegram_init_data)
        except:
            pass

    if season is None:
        season = datetime.now().year

    # 1. Загружаем данные
    df = await get_driver_standings_async(season, round_number)

    # 2. Если пусто — возвращаем пустой список (Frontend сам покажет заглушку)
    if df.empty:
        return {"season": season, "round": round_number, "drivers": []}

    # 3. ЧИНИМ СОРТИРОВКУ (Ошибка 500)
    # Превращаем "NC", "DQ" и прочий мусор в NaN (числа), чтобы сортировка не падала
    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors='coerce')
        df = df.sort_values("position")

    # 4. Заменяем NaN на пустые строки для JSON
    df = df.fillna("")

    # 5. Формируем ответ с галочками избранного
    favorite_drivers = set()
    if user_id:
        favorite_drivers = set(await get_favorite_drivers(user_id))

    results = []
    for row in df.itertuples(index=False):
        driver_code = getattr(row, "driverCode", "")
        # Если кода нет, берем 3 буквы фамилии
        if not driver_code and getattr(row, "familyName", ""):
            driver_code = getattr(row, "familyName", "")[:3].upper()

        results.append({
            "position": getattr(row, "position", ""),
            "points": getattr(row, "points", 0),
            "code": driver_code,
            "name": f"{getattr(row, 'givenName', '')} {getattr(row, 'familyName', '')}",
            "is_favorite": driver_code in favorite_drivers
        })

    return {"season": season, "round": round_number, "drivers": results}


@web_app.get("/api/constructors")
async def api_constructors(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Кубок конструкторов."""
    user_id = None
    if x_telegram_init_data:
        try:
            user_id = await get_current_user_id(x_telegram_init_data)
        except:
            pass

    if season is None:
        season = datetime.now().year

    # 1. Загрузка
    df = await get_constructor_standings_async(season, round_number)

    # 2. Если пусто
    if df.empty:
        return {"season": season, "round": round_number, "constructors": []}

    # 3. Сортировка (безопасная)
    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors='coerce')
        df = df.sort_values("position")

    # 4. Чистка NaN
    df = df.fillna("")

    # 5. Формирование ответа
    favorite_teams = set()
    if user_id:
        favorite_teams = set(await get_favorite_teams(user_id))

    results = []
    for row in df.itertuples(index=False):
        team_name = getattr(row, "constructorName", "")
        results.append({
            "position": getattr(row, "position", ""),
            "points": getattr(row, "points", 0),
            "name": team_name,
            "is_favorite": team_name in favorite_teams
        })

    return {"season": season, "round": round_number, "constructors": results}


@web_app.get("/api/favorites")
async def api_favorites(user_id: int = Depends(get_current_user_id)):
    """Получить список избранного (только для WebApp)."""
    drivers = await get_favorite_drivers(user_id)
    teams = await get_favorite_teams(user_id)
    return {"drivers": drivers, "teams": teams}


# --- Изменение избранного (POST) ---

class FavoriteItem(BaseModel):
    id: str


@web_app.post("/api/favorites/driver")
async def toggle_favorite_driver(
        item: FavoriteItem,
        user_id: int = Depends(get_current_user_id)
):
    current_favs = await get_favorite_drivers(user_id)
    if item.id in current_favs:
        await remove_favorite_driver(user_id, item.id)
        return {"status": "removed", "id": item.id}
    else:
        await add_favorite_driver(user_id, item.id)
        return {"status": "added", "id": item.id}


@web_app.post("/api/favorites/team")
async def toggle_favorite_team(
        item: FavoriteItem,
        user_id: int = Depends(get_current_user_id)
):
    current_favs = await get_favorite_teams(user_id)
    if item.id in current_favs:
        await remove_favorite_team(user_id, item.id)
        return {"status": "removed", "id": item.id}
    else:
        await add_favorite_team(user_id, item.id)
        return {"status": "added", "id": item.id}


# --- РЕЗУЛЬТАТЫ ПОСЛЕДНЕГО ГРАН-ПРИ ---

@web_app.get("/api/race-results")
async def api_race_results(user_id: Optional[int] = Depends(get_current_user_id)):
    """Возвращает результаты последней прошедшей гонки."""
    season = datetime.now().year

    # 1. Ищем последний прошедший этап
    schedule = await get_season_schedule_short_async(season)
    today = datetime.now().date()

    past_races = []
    for r in schedule:
        try:
            r_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if r_date < today:
                past_races.append(r)
        except:
            continue

    if not past_races:
        # Если в этом сезоне гонок еще не было, можно попробовать вернуть прошлый год
        # Но пока просто вернем пустой статус
        return {"results": [], "race_info": None}

    last_race = past_races[-1]  # Последняя гонка
    round_num = last_race["round"]

    # 2. Получаем результаты
    df = await get_race_results_async(season, round_num)

    if df is None or df.empty:
        return {"results": [], "race_info": None}

    # 3. Избранное пользователя
    fav_drivers = set()
    fav_teams = set()
    if user_id:
        fav_drivers = set(await get_favorite_drivers(user_id))
        fav_teams = set(await get_favorite_teams(user_id))

    # 4. Формируем ответ
    results = []
    if "Position" in df.columns:
        df = df.sort_values("Position")

    for row in df.itertuples(index=False):
        try:
            pos = int(getattr(row, "Position", 0))
            code = getattr(row, "Abbreviation", "") or getattr(row, "DriverNumber", "")
            # Имя
            given = getattr(row, "FirstName", "")
            family = getattr(row, "LastName", "")
            full_name = f"{given} {family}"
            team = getattr(row, "TeamName", "")
            points = float(getattr(row, "Points", 0))

            results.append({
                "position": pos,
                "code": code,
                "name": full_name,
                "team": team,
                "points": points,
                "is_favorite_driver": code in fav_drivers,
                "is_favorite_team": team in fav_teams
            })
        except:
            continue

    return {
        "season": season,
        "round": round_num,
        "race_info": last_race,
        "results": results
    }


@web_app.get("/api/quali-results")
async def api_quali_results():
    """Возвращает результаты последней квалификации."""
    season = datetime.now().year

    # Функция _get_latest_quali_async сама ищем последний этап с данными
    data = await _get_latest_quali_async(season)
    if not data:
        return {"results": [], "race_info": None}

    round_num, q_results = data

    # Получим инфо о трассе для красоты
    schedule = await get_season_schedule_short_async(season)
    race_info = next((r for r in schedule if r["round"] == round_num), None)

    results = []
    for r in q_results:
        results.append({
            "position": r["position"],
            "driver": r["driver"],  # Code (VER)
            "name": r.get("name", ""),
            "best": r.get("best", "-")
        })

    return {
        "season": season,
        "round": round_num,
        "race_info": race_info,
        "results": results
    }


# --- Обслуживание HTML (Static) ---

@web_app.get("/")
async def serve_index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="index.html not found")


@web_app.get("/{filename}")
async def serve_file(filename: str):
    # Защита от попытки скачать сам код API
    if filename.startswith("api") or filename.endswith(".py"):
        raise HTTPException(status_code=404, detail="Not found")

    file_path = WEB_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    raise HTTPException(status_code=404, detail=f"File {filename} not found")