# app/miniapp_api.py

import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path

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
from app.db import get_favorite_drivers, get_favorite_teams, get_last_reminded_round

# Импортируем нашу проверку авторизации
from app.auth import get_current_user_id

WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "app"

web_app = FastAPI(title="FormulaOneBot Mini App API")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.exists():
    web_app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# --- Публичные эндпоинты (авторизация не обязательна) ---

@web_app.get("/api/next-race")
async def api_next_race(season: Optional[int] = None):
    return await build_next_race_payload(season)


@web_app.get("/api/season")
async def api_season(season: Optional[int] = Query(None)):
    if season is None:
        season = datetime.now().year
    races = await get_season_schedule_short_async(season)
    return {"season": season, "races": races}


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


# --- Приватные эндпоинты (Нужна валидация initData) ---
# Обрати внимание: мы убрали telegram_id из аргументов и добавили user_id через Depends

@web_app.get("/api/drivers")
async def api_drivers(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        # Опциональная авторизация: если header есть, мы получим ID, если нет — None
        # Но для favorites галочек нам нужен ID. Сделаем так:
        # Мы попытаемся достать ID. Если не выйдет (юзер в браузере), будет None.
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    user_id = None
    if x_telegram_init_data:
        try:
            # Ручной вызов проверки, чтобы не падать с 401, если юзер просто смотрит таблицу
            user_id = await get_current_user_id(x_telegram_init_data)
        except:
            pass

    if season is None:
        season = datetime.now().year

    df = await get_driver_standings_async(season, round_number)
    if df.empty:
        return {"season": season, "round": round_number, "drivers": []}

    df = df.sort_values("position")

    favorites = set()
    if user_id:
        favorites = set(await get_favorite_drivers(user_id))

    drivers = []
    for row in df.itertuples(index=False):
        try:
            position = int(getattr(row, "position", 0))
            points = float(getattr(row, "points", 0))
            code = getattr(row, "driverCode", "") or ""
            given = getattr(row, "givenName", "") or ""
            family = getattr(row, "familyName", "") or ""
            full_name = f"{given} {family}".strip() or code

            if not code: continue

            drivers.append({
                "position": position,
                "code": code,
                "name": full_name,
                "points": points,
                "is_favorite": code in favorites,
            })
        except:
            continue

    return {"season": season, "round": round_number, "drivers": drivers}


@web_app.get("/api/constructors")
async def api_constructors(
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

    df = await get_constructor_standings_async(season, round_number)

    if df.empty:
        return {"season": season, "round": round_number, "constructors": []}

    df = df.sort_values("position")

    favorites = set()
    if user_id:
        favorites = set(await get_favorite_teams(user_id))

    constructors = []
    for row in df.itertuples(index=False):
        try:
            position = int(getattr(row, "position", 0))
            points = float(getattr(row, "points", 0))
            name = getattr(row, "constructorName", "Unknown")

            constructors.append({
                "position": position,
                "name": name,
                "points": points,
                "is_favorite": name in favorites,
            })
        except:
            continue

    return {"season": season, "round": round_number, "constructors": constructors}


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