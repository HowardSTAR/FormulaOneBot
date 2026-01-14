import asyncio
from datetime import datetime
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
    get_constructor_standings_async,
    get_race_results_async,
    _get_latest_quali_async,
)
from app.db import (
    get_favorite_drivers, get_favorite_teams, get_last_reminded_round,
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
    """Информация о ближайшей гонке."""
    data = await build_next_race_payload(season)
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
    """Детальное расписание уикенда."""
    if season is None:
        season = datetime.now().year
    sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)
    return {"season": season, "round": round_number, "sessions": sessions}


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