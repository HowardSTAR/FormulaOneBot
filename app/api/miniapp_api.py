# app/miniapp_api.py
import asyncio
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.handlers.races import build_next_race_payload
# ИСПРАВЛЕНО: Импортируем асинхронные версии
from app.f1_data import (
    get_season_schedule_short_async,
    get_weekend_schedule,
    get_driver_standings_async,
    get_constructor_standings_async,
    get_race_results_async,
    _get_latest_quali_async,
)
from app.db import get_favorite_drivers, get_favorite_teams, get_last_reminded_round

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


@web_app.get("/api/next-race")
async def api_next_race(season: Optional[int] = None):
    # build_next_race_payload мы сделали асинхронной в races.py
    return await build_next_race_payload(season)


@web_app.get("/api/season")
async def api_season(season: Optional[int] = Query(None)):
    if season is None:
        season = datetime.now().year

    # ИСПРАВЛЕНО: await
    races = await get_season_schedule_short_async(season)
    return {
        "season": season,
        "races": races,
    }


@web_app.get("/api/drivers")
async def api_drivers(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        telegram_id: Optional[int] = Query(None),
):
    if season is None:
        season = datetime.now().year

    # ИСПРАВЛЕНО: await
    df = await get_driver_standings_async(season, round_number)

    if df.empty:
        return {"season": season, "round": round_number, "drivers": []}

    df = df.sort_values("position")

    favorites = set()
    if telegram_id:
        favorites = set(await get_favorite_drivers(telegram_id))

    drivers = []
    for row in df.itertuples(index=False):
        # (код парсинга без изменений)
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
        telegram_id: Optional[int] = Query(None),
):
    if season is None:
        season = datetime.now().year

    # ИСПРАВЛЕНО: await
    df = await get_constructor_standings_async(season, round_number)

    if df.empty:
        return {"season": season, "round": round_number, "constructors": []}

    df = df.sort_values("position")

    favorites = set()
    if telegram_id:
        favorites = set(await get_favorite_teams(telegram_id))

    constructors = []
    for row in df.itertuples(index=False):
        # (код парсинга)
        try:
            position = int(getattr(row, "position", 0))
            points = float(getattr(row, "points", 0))
            name = getattr(row, "constructorName", "Unknown")
            code = ""  # (логика добычи кода)

            constructors.append({
                "position": position,
                "name": name,
                "code": code,
                "points": points,
                "is_favorite": name in favorites,
            })
        except:
            continue

    return {"season": season, "round": round_number, "constructors": constructors}


@web_app.get("/api/race-results")
async def api_race_results(
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None),
        telegram_id: Optional[int] = Query(None),
):
    if season is None:
        season = datetime.now().year

    if round_number is None:
        round_number = await get_last_reminded_round(season)
        if round_number is None:
            raise HTTPException(status_code=404, detail="Нет завершённых гонок")

    # ИСПРАВЛЕНО: await
    race_results = await get_race_results_async(season, round_number)
    if race_results is None or race_results.empty:
        raise HTTPException(status_code=404, detail="Результаты гонки недоступны")

    schedule = await get_season_schedule_short_async(season)
    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == round_number), None)

    favorites_drivers = set()
    favorites_teams = set()
    if telegram_id:
        favorites_drivers = set(await get_favorite_drivers(telegram_id))
        favorites_teams = set(await get_favorite_teams(telegram_id))

    results = []
    if "Position" in race_results.columns:
        race_results = race_results.sort_values("Position")

    for row in race_results.itertuples(index=False):
        # (код парсинга результатов)
        try:
            position = getattr(row, "Position", None)
            if position is None: continue

            code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
            team = getattr(row, "TeamName", "")
            # ...

            results.append({
                "position": int(position),
                "code": code,
                # ...
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


# Остальные эндпоинты (api_quali_results, api_weekend_schedule)
# нужно обновить аналогично: использовать await _get_latest_quali_async
# и убрать блокирующие вызовы.

@web_app.get("/api/weekend-schedule")
async def api_weekend_schedule(
        season: Optional[int] = Query(None),
        round_number: int = Query(..., description="Номер этапа"),
):
    """Расписание уикенда (практики, квала, гонка)"""
    if season is None:
        season = datetime.now().year

    # ИСПРАВЛЕНИЕ: get_weekend_schedule синхронная, поэтому запускаем её в потоке,
    # чтобы сервер не завис, пока fastf1 ищет расписание.
    sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)

    return {
        "season": season,
        "round": round_number,
        "sessions": sessions,
    }


@web_app.get("/api/quali-results")
async def api_quali_results(
        season: Optional[int] = Query(None),
):
    """Результаты последней квалификации"""
    if season is None:
        season = datetime.now().year

    # ИСПРАВЛЕНИЕ: Используем await, так как _get_latest_quali_async теперь асинхронная
    latest = await _get_latest_quali_async(season)

    # latest возвращает кортеж (round_number, results_list) или (None, None)
    latest_round, results = latest

    if latest_round is None or not results:
        # Возвращаем пустой список, если квалификаций еще не было
        return {
            "season": season,
            "round": None,
            "race_info": None,
            "results": []
        }

    # Получаем инфу о трассе для заголовка (асинхронно)
    schedule = await get_season_schedule_short_async(season)
    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == latest_round), None)

    # Формируем красивый список для фронтенда
    formatted_results = []
    for row in results:
        # row это словарь: {'position': 1, 'driver': 'VER', 'name': '...', 'best': '1:23.456'}
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