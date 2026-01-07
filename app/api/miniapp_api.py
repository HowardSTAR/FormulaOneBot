import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.handlers.races import build_next_race_payload
from app.f1_data import (
    get_season_schedule_short,
    get_weekend_schedule,
    get_driver_standings_df,
    get_constructor_standings_df,
    get_race_results_df,
    _get_latest_quali_async,
)
from app.db import get_favorite_drivers, get_favorite_teams, get_last_reminded_round

# Для запуска веб-сервера используй:
# uvicorn app.api.miniapp_api:web_app --host 0.0.0.0 --port 8000

# Путь к веб-статистике
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "app"

web_app = FastAPI(title="FormulaOneBot Mini App API")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Для разработки - в продакшене укажи конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача статических файлов (должно быть ПЕРЕД общими роутами)
if WEB_DIR.exists():
    # Статические файлы из папки web/app
    web_app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@web_app.get("/api/next-race")
async def api_next_race(season: Optional[int] = None):
    """Ближайшая гонка"""
    return build_next_race_payload(season)


@web_app.get("/api/season")
async def api_season(season: Optional[int] = Query(None, description="Год сезона")):
    """Календарь сезона"""
    if season is None:
        season = datetime.now().year
    
    races = get_season_schedule_short(season)
    return {
        "season": season,
        "races": races,
    }


@web_app.get("/api/drivers")
async def api_drivers(
    season: Optional[int] = Query(None, description="Год сезона"),
    round_number: Optional[int] = Query(None, description="Номер этапа"),
    telegram_id: Optional[int] = Query(None, description="Telegram ID пользователя"),
):
    """Личный зачёт пилотов"""
    if season is None:
        season = datetime.now().year
    
    df = get_driver_standings_df(season, round_number)
    
    if df.empty:
        return {
            "season": season,
            "round": round_number,
            "drivers": [],
        }
    
    df = df.sort_values("position")
    
    # Получаем избранных пилотов, если указан telegram_id
    favorites = set()
    if telegram_id:
        favorites = set(await get_favorite_drivers(telegram_id))
    
    drivers = []
    for row in df.itertuples(index=False):
        try:
            position = int(getattr(row, "position", 0))
            points = float(getattr(row, "points", 0))
            code = getattr(row, "driverCode", "") or ""
            given = getattr(row, "givenName", "") or ""
            family = getattr(row, "familyName", "") or ""
            full_name = f"{given} {family}".strip() or code
            
            if not code:
                continue
            
            drivers.append({
                "position": position,
                "code": code,
                "name": full_name,
                "points": points,
                "is_favorite": code in favorites,
            })
        except (ValueError, TypeError, AttributeError):
            continue
    
    return {
        "season": season,
        "round": round_number,
        "drivers": drivers,
    }


@web_app.get("/api/constructors")
async def api_constructors(
    season: Optional[int] = Query(None, description="Год сезона"),
    round_number: Optional[int] = Query(None, description="Номер этапа"),
    telegram_id: Optional[int] = Query(None, description="Telegram ID пользователя"),
):
    """Кубок конструкторов"""
    if season is None:
        season = datetime.now().year
    
    df = get_constructor_standings_df(season, round_number)
    
    if df.empty:
        return {
            "season": season,
            "round": round_number,
            "constructors": [],
        }
    
    df = df.sort_values("position")
    
    # Получаем избранные команды, если указан telegram_id
    favorites = set()
    if telegram_id:
        favorites = set(await get_favorite_teams(telegram_id))
    
    constructors = []
    for row in df.itertuples(index=False):
        try:
            position = int(getattr(row, "position", 0))
            points = float(getattr(row, "points", 0))
            name = getattr(row, "constructorName", "Unknown")
            code = ""
            for attr_name in ("constructorCode", "constructorRef", "constructorId"):
                val = getattr(row, attr_name, None)
                if isinstance(val, str) and val:
                    code = val
                    break
            
            constructors.append({
                "position": position,
                "name": name,
                "code": code,
                "points": points,
                "is_favorite": name in favorites,
            })
        except (ValueError, TypeError, AttributeError):
            continue
    
    return {
        "season": season,
        "round": round_number,
        "constructors": constructors,
    }


@web_app.get("/api/race-results")
async def api_race_results(
    season: Optional[int] = Query(None, description="Год сезона"),
    round_number: Optional[int] = Query(None, description="Номер этапа"),
    telegram_id: Optional[int] = Query(None, description="Telegram ID пользователя"),
):
    """Результаты гонки"""
    if season is None:
        season = datetime.now().year
    
    # Если round_number не указан, берём последний завершённый этап
    if round_number is None:
        round_number = await get_last_reminded_round(season)
        if round_number is None:
            raise HTTPException(status_code=404, detail="Нет завершённых гонок для этого сезона")
    
    try:
        race_results = get_race_results_df(season, round_number)
        if race_results.empty:
            raise HTTPException(status_code=404, detail="Результаты гонки недоступны")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении результатов: {str(e)}")
    
    schedule = get_season_schedule_short(season)
    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == round_number), None)
    
    # Получаем избранных
    favorites_drivers = set()
    favorites_teams = set()
    if telegram_id:
        favorites_drivers = set(await get_favorite_drivers(telegram_id))
        favorites_teams = set(await get_favorite_teams(telegram_id))
    
    results = []
    if "Position" in race_results.columns:
        race_results = race_results.sort_values("Position")
    
    for row in race_results.itertuples(index=False):
        try:
            position = getattr(row, "Position", None)
            if position is None:
                continue
            position = int(position)
            
            code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
            team = getattr(row, "TeamName", "")
            points = getattr(row, "Points", None)
            if points is not None:
                points = float(points)
            else:
                points = 0.0
            
            given = getattr(row, "FirstName", "") or ""
            family = getattr(row, "LastName", "") or ""
            full_name = f"{given} {family}".strip() or code
            
            results.append({
                "position": position,
                "code": code,
                "name": full_name,
                "team": team,
                "points": points,
                "is_favorite_driver": code in favorites_drivers,
                "is_favorite_team": team in favorites_teams,
            })
        except (ValueError, TypeError, AttributeError):
            continue
    
    return {
        "season": season,
        "round": round_number,
        "race_info": race_info,
        "results": results,
    }


@web_app.get("/api/quali-results")
async def api_quali_results(
    season: Optional[int] = Query(None, description="Год сезона"),
    round_number: Optional[int] = Query(None, description="Номер этапа"),
):
    """Результаты квалификации"""
    if season is None:
        season = datetime.now().year
    
    if round_number is None:
        latest = await _get_latest_quali_async(season)
        if latest[0] is None:
            raise HTTPException(status_code=404, detail="Нет данных по квалификации")
        round_number, results = latest
    else:
        results = await _get_latest_quali_async(season, round_number)
        if results[0] is None:
            raise HTTPException(status_code=404, detail="Нет данных по квалификации для этого этапа")
        _, results = results
    
    schedule = get_season_schedule_short(season)
    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == round_number), None)
    
    return {
        "season": season,
        "round": round_number,
        "race_info": race_info,
        "results": results,
    }


@web_app.get("/api/weekend-schedule")
async def api_weekend_schedule(
    season: int = Query(..., description="Год сезона"),
    round_number: int = Query(..., description="Номер этапа"),
):
    """Расписание уикенда"""
    sessions = get_weekend_schedule(season, round_number)
    return {
        "season": season,
        "round": round_number,
        "sessions": sessions,
    }


@web_app.get("/api/favorites")
async def api_favorites(telegram_id: int = Query(..., description="Telegram ID пользователя")):
    """Избранные пилоты и команды"""
    drivers = await get_favorite_drivers(telegram_id)
    teams = await get_favorite_teams(telegram_id)
    
    return {
        "drivers": drivers,
        "teams": teams,
    }


# Раздача HTML файлов (должно быть ПОСЛЕ /static, чтобы не перехватывать статические файлы)
@web_app.get("/")
async def serve_index():
    """Главная страница"""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="index.html not found")


@web_app.get("/{filename}")
async def serve_file(filename: str):
    """Раздача HTML файлов"""
    # Игнорируем API эндпоинты и статические файлы
    if filename.startswith("api") or filename.startswith("static"):
        raise HTTPException(status_code=404, detail="Not found")
    
    file_path = WEB_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    
    raise HTTPException(status_code=404, detail=f"File {filename} not found")