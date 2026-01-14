import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path
from pydantic import BaseModel

# Добавляем Depends
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.handlers.races import build_next_race_payload
from app.f1_data import (
    get_season_schedule_short_async,
    get_weekend_schedule,
    get_driver_standings_async,
    get_constructor_standings_async,
    get_race_results_async,
    _get_latest_quali_async,
)
from app.db import get_favorite_drivers, get_favorite_teams, get_last_reminded_round, remove_favorite_driver, \
    add_favorite_driver, remove_favorite_team, add_favorite_team

# Импортируем нашу проверку авторизации
from app.auth import get_current_user_id


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

WEB_DIR = PROJECT_ROOT / "web" / "app"
STATIC_DIR = WEB_DIR / "static"

# ДЛЯ ОТЛАДКИ (будет видно в консоли при запуске):
print(f"DEBUG: Ищу веб-файлы здесь: {WEB_DIR}")
print(f"DEBUG: Существует ли папка? {WEB_DIR.exists()}")
print(f"DEBUG: Существует ли index.html? {(WEB_DIR / 'index.html').exists()}")

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
    print(f"DEBUG: Статика подключена из {STATIC_DIR}")
else:
    print(f"WARNING: Папка static не найдена: {STATIC_DIR}")


# --- Публичные эндпоинты (авторизация не обязательна) ---

@web_app.get("/api/next-race")
async def api_next_race(season: Optional[int] = None):
    # Эта функция делает всю магию. Если она работает в боте, сработает и тут.
    data = await build_next_race_payload(season)
    return data


@web_app.get("/api/season")
async def api_season(season: Optional[int] = Query(None)):
    if season is None:
        season = datetime.now().year

    # Получаем расписание
    races = await get_season_schedule_short_async(season)

    # Возвращаем JSON
    return {
        "season": season,
        "races": races  # Это список словарей: date, round, event_name, location...
    }


@web_app.get("/api/weekend-schedule")
async def api_weekend_schedule(
        season: Optional[int] = Query(None),
        round_number: int = Query(..., description="Номер этапа"),
):
    if season is None:
        season = datetime.now().year
    sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)
    return {"season": season, "round": round_number, "sessions": sessions}


@web_app.get("/api/quali-results")
async def api_quali_results(season: Optional[int] = Query(None)):
    if season is None:
        season = datetime.now().year

    latest = await _get_latest_quali_async(season)
    latest_round, results = latest

    if latest_round is None or not results:
        return {"season": season, "round": None, "race_info": None, "results": []}

    schedule = await get_season_schedule_short_async(season)
    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == latest_round), None)

    formatted_results = []
    for row in results:
        formatted_results.append({
            "position": row.get("position"),
            "driver": row.get("driver"),
            "name": row.get("name"),
            "best": row.get("best"),
        })

    return {
        "season": season,
        "round": latest_round,
        "race_info": race_info,
        "results": formatted_results,
    }


@web_app.get("/api/drivers")
async def api_drivers(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    # ... (код авторизации и получения user_id оставляем как был) ...
    user_id = None
    if x_telegram_init_data:
        try:
            user_id = await get_current_user_id(x_telegram_init_data)
        except:
            pass

    if season is None:
        season = datetime.now().year

    # Запрашиваем данные
    df = await get_driver_standings_async(season, round_number)

    # --- УДАЛЯЕМ ЭТОТ БЛОК (или закомментируй его) ---
    # if df.empty and season == datetime.now().year:
    #     season = season - 1
    #     df = await get_driver_standings_async(season, round_number)
    # -------------------------------------------------

    if df.empty:
        return {"season": season, "round": round_number, "drivers": []}

        # 1. СНАЧАЛА СОРТИРУЕМ (Pandas умеет сортировать с NaN, ставя их в конец)
    if "position" in df.columns:
        # На всякий случай превращаем колонку в числа, чтобы избежать глюков
        df["position"] = pd.to_numeric(df["position"], errors='coerce')
        df = df.sort_values("position")

        # 2. И ТОЛЬКО ПОТОМ УБИРАЕМ NaN (для JSON)
    df = df.fillna("")

    if "position" in df.columns:
        df = df.sort_values("position")

    # ... (дальше формирование списка results оставляем как есть) ...
    # Код ниже не меняется
    favorite_drivers = set()
    if user_id:
        favorite_drivers = set(await get_favorite_drivers(user_id))

    results = []
    for row in df.itertuples(index=False):
        # ... (код цикла) ...
        pass  # (тут твой код)

    return {"season": season, "round": round_number, "drivers": results}


@web_app.get("/api/constructors")
async def api_constructors(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    # ... (авторизация) ...
    user_id = None
    if x_telegram_init_data:
        try:
            user_id = await get_current_user_id(x_telegram_init_data)
        except:
            pass

    if season is None:
        season = datetime.now().year

    df = await get_constructor_standings_async(season, round_number)

    # --- УДАЛЯЕМ ЭТОТ БЛОК ---
    # if df.empty and season == datetime.now().year:
    #     season = season - 1
    #     df = await get_constructor_standings_async(season, round_number)
    # -------------------------

    if df.empty:
        return {"season": season, "round": round_number, "constructors": []}

        # 1. Сортируем
    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors='coerce')
        df = df.sort_values("position")

        # 2. Чистим
    df = df.fillna("")

    if "position" in df.columns:
        df = df.sort_values("position")

    # ... (дальше код без изменений) ...
    favorite_teams = set()
    if user_id:
        favorite_teams = set(await get_favorite_teams(user_id))

    results = []
    # ... (цикл формирования) ...

    return {"season": season, "round": round_number, "constructors": results}


# А вот для /api/favorites авторизация ОБЯЗАТЕЛЬНА.
# Если заголовка нет — вернется 401 Unauthorized.
@web_app.get("/api/favorites")
async def api_favorites(
        user_id: int = Depends(get_current_user_id)
):
    """Избранные пилоты и команды. Требует валидный initData."""
    drivers = await get_favorite_drivers(user_id)
    teams = await get_favorite_teams(user_id)

    return {
        "drivers": drivers,
        "teams": teams,
    }


@web_app.get("/api/race-results")
async def api_race_results(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    user_id = None
    if x_telegram_init_data:
        try:
            user_id = await get_current_user_id(x_telegram_init_data)
        except:
            pass

    if season is None:
        season = datetime.now().year

    if round_number is None:
        round_number = await get_last_reminded_round(season)
        if round_number is None:
            raise HTTPException(status_code=404, detail="Нет завершённых гонок")

    race_results = await get_race_results_async(season, round_number)
    if race_results is None or race_results.empty:
        raise HTTPException(status_code=404, detail="Результаты гонки недоступны")

    schedule = await get_season_schedule_short_async(season)
    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == round_number), None)

    favorites_drivers = set()
    favorites_teams = set()
    if user_id:
        favorites_drivers = set(await get_favorite_drivers(user_id))
        favorites_teams = set(await get_favorite_teams(user_id))

    results = []
    if "Position" in race_results.columns:
        race_results = race_results.sort_values("Position")

    for row in race_results.itertuples(index=False):
        try:
            position = getattr(row, "Position", None)
            if position is None: continue

            code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
            team = getattr(row, "TeamName", "")

            # Парсинг очков
            pts = getattr(row, "Points", 0)
            try:
                pts_val = float(pts)
                pts_str = f"{pts_val:g}"
            except:
                pts_str = str(pts)

            # Парсинг имени
            given = getattr(row, "FirstName", "") or ""
            family = getattr(row, "LastName", "") or ""
            full_name = f"{given} {family}".strip()

            results.append({
                "position": int(position),
                "code": code,
                "name": full_name,
                "team": team,
                "points": pts_str,
                "is_favorite_driver": code in favorites_drivers,
                "is_favorite_team": team in favorites_teams,
            })
        except:
            continue

    return {
        "season": season,
        "round": round_number,
        "race_info": race_info,
        "results": results,
    }


# --- Модели для получения данных от WebApp ---
class FavoriteItem(BaseModel):
    id: str  # Код пилота (VER) или имя команды (Red Bull)


# --- Эндпоинты для изменения избранного ---

@web_app.post("/api/favorites/driver")
async def toggle_favorite_driver(
        item: FavoriteItem,
        user_id: int = Depends(get_current_user_id)
):
    """Добавить или удалить пилота из избранного."""
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
    """Добавить или удалить команду."""
    current_favs = await get_favorite_teams(user_id)

    if item.id in current_favs:
        await remove_favorite_team(user_id, item.id)
        return {"status": "removed", "id": item.id}
    else:
        await add_favorite_team(user_id, item.id)
        return {"status": "added", "id": item.id}



@web_app.get("/")
async def serve_index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="index.html not found")


@web_app.get("/{filename}")
async def serve_file(filename: str):
    if filename.startswith("api") or filename.startswith("static"):
        raise HTTPException(status_code=404, detail="Not found")

    file_path = WEB_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    raise HTTPException(status_code=404, detail=f"File {filename} not found")