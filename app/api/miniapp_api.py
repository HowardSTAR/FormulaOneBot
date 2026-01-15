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
    """Информация о ближайшей гонке + таймер."""
    data = await build_next_race_payload(season)

    if data.get("status") != "ok":
        return data

    try:
        current_season = data["season"]
        round_num = data["round"]

        # Загружаем расписание для таймера
        sessions = await asyncio.to_thread(get_weekend_schedule, current_season, round_num)

        if not sessions:
            return data

        now_utc = datetime.now(timezone.utc)
        sorted_sessions = []

        for s in sessions:
            dt = None
            # Пытаемся найти дату сессии для таймера
            if s.get("utc_iso"):
                try:
                    dt = datetime.fromisoformat(s["utc_iso"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except:
                    pass

            # Фолбэк на старые методы парсинга (если utc_iso нет)
            if dt is None and isinstance(s.get("date"), datetime):
                dt = s["date"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

            if dt:
                sorted_sessions.append({
                    "name": s.get("name", "Session"),
                    "dt": dt
                })

        # Сортируем и ищем ближайшую будущую сессию
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

    except Exception as e:
        print(f"ERROR calculating timer: {e}")

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
    """
    Детальное расписание уикенда.
    Исправлено: теперь возвращает поля 'local' и 'utc', которые ждет HTML.
    """
    if season is None:
        season = datetime.now().year

    # Получаем данные из f1_data.py
    # Структура словаря там: {'name': ..., 'local': '06.03.2026 04:30', 'utc': ...}
    raw_sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)

    # Маппинг имен на русский
    name_map = {
        "Practice 1": "Практика 1",
        "Practice 2": "Практика 2",
        "Practice 3": "Практика 3",
        "Qualifying": "Квалификация",
        "Sprint": "Спринт",
        "Sprint Qualifying": "Спринт-квалификация",
        "Race": "Гонка",
    }

    # Просто обновляем имена, но оставляем структуру данных (local/utc)
    for s in raw_sessions:
        raw_name = s.get("name", "Session")
        s["name"] = name_map.get(raw_name, raw_name)

    return {"season": season, "round": round_number, "sessions": raw_sessions}


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

    df = await get_driver_standings_async(season, round_number)

    if df.empty:
        return {"season": season, "round": round_number, "drivers": []}

    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors='coerce')
        df = df.sort_values("position")

    df = df.fillna("")

    favorite_drivers = set()
    if user_id:
        favorite_drivers = set(await get_favorite_drivers(user_id))

    results = []
    for row in df.itertuples(index=False):
        driver_code = getattr(row, "driverCode", "")
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

    df = await get_constructor_standings_async(season, round_number)

    if df.empty:
        return {"season": season, "round": round_number, "constructors": []}

    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors='coerce')
        df = df.sort_values("position")

    df = df.fillna("")

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


@web_app.get("/api/race-results")
async def api_race_results(user_id: Optional[int] = Depends(get_current_user_id)):
    """Возвращает результаты последней прошедшей гонки."""
    season = datetime.now().year

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
        return {"results": [], "race_info": None}

    last_race = past_races[-1]
    round_num = last_race["round"]

    df = await get_race_results_async(season, round_num)

    if df is None or df.empty:
        return {"results": [], "race_info": None}

    fav_drivers = set()
    fav_teams = set()
    if user_id:
        fav_drivers = set(await get_favorite_drivers(user_id))
        fav_teams = set(await get_favorite_teams(user_id))

    results = []
    if "Position" in df.columns:
        df = df.sort_values("Position")

    for row in df.itertuples(index=False):
        try:
            pos = int(getattr(row, "Position", 0))
            code = getattr(row, "Abbreviation", "") or getattr(row, "DriverNumber", "")
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

    data = await _get_latest_quali_async(season)
    if not data:
        return {"results": [], "race_info": None}

    round_num, q_results = data

    schedule = await get_season_schedule_short_async(season)
    race_info = next((r for r in schedule if r["round"] == round_num), None)

    results = []
    for r in q_results:
        results.append({
            "position": r["position"],
            "driver": r["driver"],
            "name": r.get("name", ""),
            "best": r.get("best", "-")
        })

    return {
        "season": season,
        "round": round_num,
        "race_info": race_info,
        "results": results
    }


@web_app.get("/")
async def serve_index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="index.html not found")


@web_app.get("/{filename}")
async def serve_file(filename: str):
    if filename.startswith("api") or filename.endswith(".py"):
        raise HTTPException(status_code=404, detail="Not found")

    file_path = WEB_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    raise HTTPException(status_code=404, detail=f"File {filename} not found")