import io
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.auth import get_current_user_id
from app.db import (
    get_favorite_drivers, get_favorite_teams,
    remove_favorite_driver, add_favorite_driver,
    remove_favorite_team, add_favorite_team,
    get_user_settings, update_user_setting
)
from app.f1_data import (
    get_season_schedule_short_async,
    get_weekend_schedule,
    get_driver_standings_async,
    get_constructor_standings_async,
    sort_standings_zero_last,
    _get_latest_quali_async,
    get_race_results_async,
    get_event_details_async,
)
from app.handlers.races import build_next_race_payload
from app.utils.image_render import _get_team_logo

# --- Настройка путей ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
WEB_DIR_LEGACY = PROJECT_ROOT / "web" / "app"
FRONT_DIR = PROJECT_ROOT / "front" / "dist"
# Используем React SPA (front) если собран, иначе web/app
WEB_DIR = FRONT_DIR if FRONT_DIR.exists() else WEB_DIR_LEGACY
STATIC_DIR = WEB_DIR / "static"

# --- Инициализация приложения ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.f1_data import init_redis_cache
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    await init_redis_cache(redis_url)
    yield


web_app = FastAPI(title="FormulaOneBot Mini App API", lifespan=lifespan)

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    web_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- МОДЕЛИ ДАННЫХ ---

class NextRaceResponse(BaseModel):
    status: str
    season: int
    round: Optional[int] = None
    event_name: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    date: Optional[str] = None
    utc: Optional[str] = None
    local: Optional[str] = None
    fmt_date: Optional[str] = None
    next_session_name: Optional[str] = None
    next_session_iso: Optional[str] = None


class SessionItem(BaseModel):
    name: str
    utc_iso: Optional[str] = None
    utc: Optional[str] = None
    local: Optional[str] = None


class ScheduleResponse(BaseModel):
    sessions: List[SessionItem]


class FavoriteItem(BaseModel):
    id: str


class SettingsRequest(BaseModel):
    timezone: str
    notify_before: int
    notifications_enabled: bool = False


# --- ЭНДПОИНТЫ ---

@web_app.get("/api/settings")
async def api_get_settings(user_id: int = Depends(get_current_user_id)):
    """Получить текущие настройки пользователя."""
    return await get_user_settings(user_id)


@web_app.post("/api/settings")
async def api_save_settings(
        settings: SettingsRequest,
        user_id: int = Depends(get_current_user_id)
):
    """Сохранить настройки."""
    await update_user_setting(user_id, "timezone", settings.timezone)
    await update_user_setting(user_id, "notify_before", settings.notify_before)

    # ДОБАВИТЬ СОХРАНЕНИЕ НОВОГО ПОЛЯ В БД:
    await update_user_setting(user_id, "notifications_enabled", int(settings.notifications_enabled))
    return {"status": "ok"}


@web_app.get("/api/next-race", response_model=NextRaceResponse)
async def api_next_race(
        season: Optional[int] = None,
        user_id: Optional[int] = Depends(get_current_user_id)
):
    """Информация о ближайшей гонке + таймер."""
    # Передаем user_id, чтобы дата гонки в шапке форматировалась как раньше
    data = await build_next_race_payload(season, user_id=user_id)

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
            if s.get("utc_iso"):
                try:
                    dt = datetime.fromisoformat(s["utc_iso"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except:
                    pass

            if dt is None and isinstance(s.get("date"), datetime):
                dt = s["date"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

            if dt:
                sorted_sessions.append({
                    "name": s.get("name", "Session"),
                    "dt": dt
                })

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
    if season is None:
        season = datetime.now().year
    races = await get_season_schedule_short_async(season)
    return {"season": season, "races": races}


@web_app.get("/api/weekend-schedule", response_model=ScheduleResponse)
async def api_weekend_schedule(
        season: Optional[int] = Query(None),
        round_number: int = Query(..., description="Номер этапа"),
):
    # Убрали user_id. Возвращаем как было.
    if season is None:
        season = datetime.now().year

    raw_sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)

    name_map = {
        "Practice 1": "Практика 1",
        "Practice 2": "Практика 2",
        "Practice 3": "Практика 3",
        "Qualifying": "Квалификация",
        "Sprint": "Спринт",
        "Sprint Qualifying": "Спринт-квалификация",
        "Race": "Гонка",
    }

    for s in raw_sessions:
        raw_name = s.get("name", "Session")
        s["name"] = name_map.get(raw_name, raw_name)

    return {"sessions": raw_sessions}


@web_app.get("/api/drivers")
async def api_drivers(
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

    df = await get_driver_standings_async(season, round_number)

    if df.empty:
        return {"season": season, "round": round_number, "drivers": []}

    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors="coerce")
        df = sort_standings_zero_last(df)

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
            "is_favorite": driver_code in favorite_drivers,
            "number": getattr(row, "permanentNumber", "") or "",
            "constructorId": getattr(row, "constructorId", "") or "",
            "constructorName": getattr(row, "constructorName", "") or "",
        })

    return {"season": season, "round": round_number, "drivers": results}


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

    if "position" in df.columns:
        df["position"] = pd.to_numeric(df["position"], errors="coerce")
        df = sort_standings_zero_last(df)

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
            "constructorId": getattr(row, "constructorId", "") or "",
            "is_favorite": team_name in favorite_teams
        })

    return {"season": season, "round": round_number, "constructors": results}


@web_app.get("/api/team-logo")
async def api_team_logo(
        team: str = Query(..., description="constructorId или название команды"),
        name: Optional[str] = Query(None, description="Полное название команды"),
        season: int = Query(None, description="Год сезона")
):
    """Возвращает логотип команды в формате PNG."""
    if season is None:
        season = datetime.now().year
    img = await asyncio.to_thread(_get_team_logo, team, name or team, season)
    if img is None:
        raise HTTPException(status_code=404, detail="Логотип не найден")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


@web_app.get("/api/favorites")
async def api_favorites(user_id: int = Depends(get_current_user_id)):
    drivers = await get_favorite_drivers(user_id)
    teams = await get_favorite_teams(user_id)
    return {"drivers": drivers, "teams": teams}


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


@web_app.get("/api/race-details")
async def api_race_details(
        season: int = Query(..., description="Год сезона"),
        # CHANGE HERE: Added alias="round"
        round_number: int = Query(..., description="Номер этапа", alias="round")
):
    """Возвращает полную инфу о трассе и расписание уикенда"""
    data = await get_event_details_async(season, round_number)

    if not data:
        raise HTTPException(status_code=404, detail="Race not found")

    # Русификация сессий для API
    name_map = {
        "Practice 1": "Практика 1",
        "Practice 2": "Практика 2",
        "Practice 3": "Практика 3",
        "Qualifying": "Квалификация",
        "Sprint": "Спринт",
        "Sprint Qualifying": "Спринт-квалификация",
        "Race": "Гонка",
    }

    if "sessions" in data:
        for s in data["sessions"]:
            raw = s.get("name", "")
            s["name"] = name_map.get(raw, raw)

    return data


import asyncio  # Убедись, что это импортировано вверху файла


@web_app.get("/api/compare")
async def api_compare(d1: str, d2: str, season: int = 2026):  # <-- СТРОГО season!
    """Сравнение пилотов для Web App"""

    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"error": f"Нет расписания на {season} год"}

    today = datetime.now().date()
    passed_races = []

    for r in schedule:
        try:
            r_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if r_date < today:
                passed_races.append(r)
        except Exception:
            continue

    if not passed_races:
        return {"error": f"В {season} году еще не было прошедших гонок для сравнения."}

    labels = []
    tasks = []

    for race in passed_races:
        round_num = race["round"]
        labels.append(race.get("event_name", f"Этап {round_num}").replace(" Grand Prix", "").replace("Gp", ""))
        # Передаем season
        tasks.append(get_race_results_async(season, round_num))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    d1_history, d2_history = [], []
    q_score1, q_score2 = 0, 0  # Счет квалификаций

    for df in results:
        pts1, pts2 = 0, 0
        grid1, grid2 = 999, 999

        if df is not None and not isinstance(df, Exception) and not df.empty:
            df['Abbreviation'] = df['Abbreviation'].fillna("").astype(str).str.upper()

            # Обработка первого пилота
            row1 = df[df['Abbreviation'] == d1.upper()]
            if not row1.empty:
                val1 = row1.iloc[0].get('Points', 0)
                pts1 = 0 if pd.isna(val1) else float(val1)

                # Достаем стартовую позицию (Grid) для сравнения квал
                g1 = row1.iloc[0].get('GridPosition', row1.iloc[0].get('Grid', 999))
                grid1 = 999 if pd.isna(g1) else float(g1)

            # Обработка второго пилота
            row2 = df[df['Abbreviation'] == d2.upper()]
            if not row2.empty:
                val2 = row2.iloc[0].get('Points', 0)
                pts2 = 0 if pd.isna(val2) else float(val2)

                g2 = row2.iloc[0].get('GridPosition', row2.iloc[0].get('Grid', 999))
                grid2 = 999 if pd.isna(g2) else float(g2)

            # Сравниваем, кто стартовал выше (у кого позиция меньше)
            if grid1 != 999 and grid2 != 999:
                if grid1 < grid2:
                    q_score1 += 1
                elif grid2 < grid1:
                    q_score2 += 1

        d1_history.append(pts1)
        d2_history.append(pts2)

    return {
        "labels": labels,
        "q_score": [q_score1, q_score2],  # Передаем счет на фронтенд
        "data1": {"code": d1.upper(), "history": d1_history, "color": "#ff8700"},
        "data2": {"code": d2.upper(), "history": d2_history, "color": "#00d2be"}
    }


# Маппинг названий команд: Ergast/API -> возможные FastF1 TeamName
TEAM_NAME_ALIASES: dict[str, list[str]] = {
    "Red Bull": ["Red Bull Racing", "Oracle Red Bull Racing", "Red Bull Racing Honda RBPT"],
    "RB F1 Team": ["Racing Bulls", "Visa Cash App RB", "Racing Bulls Honda RBPT", "RB", "Visa Cash App Racing Bulls"],
    "Alpine F1 Team": ["Alpine"],
    "Sauber": ["Stake F1 Team Kick Sauber", "Kick Sauber", "Alfa Romeo Sauber", "Sauber", "Stake F1 Team"],
}


def _team_matches(selected: str, row_value: str) -> bool:
    """Проверяет, соответствует ли выбранная команда значению из результатов гонки."""
    if not selected or (row_value is None or (isinstance(row_value, float) and pd.isna(row_value))):
        return False
    sel = str(selected).strip().lower()
    row = str(row_value).strip().lower()
    if sel == row:
        return True
    if sel in row or row in sel:
        return True
    aliases = TEAM_NAME_ALIASES.get(selected.strip(), [])
    for alias in aliases:
        if alias.strip().lower() == row:
            return True
        if alias.strip().lower() in row or row in alias.strip().lower():
            return True
    return False


@web_app.get("/api/compare/teams")
async def api_compare_teams(c1: str, c2: str, season: int = Query(...)):
    """Сравнение команд по очкам за каждую гонку сезона."""
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"error": f"Нет расписания на {season} год"}

    today = datetime.now().date()
    passed_races = []
    for r in schedule:
        try:
            r_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if r_date < today:
                passed_races.append(r)
        except Exception:
            continue

    if not passed_races:
        return {"error": f"В {season} году ещё не было прошедших гонок для сравнения."}

    labels = []
    tasks = []
    for race in passed_races:
        round_num = race["round"]
        labels.append(race.get("event_name", f"Этап {round_num}").replace(" Grand Prix", "").replace("Gp", ""))
        tasks.append(get_race_results_async(season, round_num))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    c1_history, c2_history = [], []

    def _team_points(df: pd.DataFrame, team_name: str) -> float:
        if df is None or isinstance(df, Exception) or df.empty:
            return 0.0
        col = "TeamName" if "TeamName" in df.columns else "Constructor"
        if col not in df.columns:
            return 0.0
        pts_col = "Points" if "Points" in df.columns else ("points" if "points" in df.columns else None)
        if pts_col is None:
            return 0.0
        mask = df[col].apply(lambda x: _team_matches(team_name, x))
        team_rows = df[mask]
        if team_rows.empty:
            return 0.0
        pts = team_rows[pts_col].fillna(0).astype(float).sum()
        return float(pts)

    for df in results:
        pts1 = _team_points(df, c1) if isinstance(df, pd.DataFrame) else 0.0
        pts2 = _team_points(df, c2) if isinstance(df, pd.DataFrame) else 0.0
        c1_history.append(pts1)
        c2_history.append(pts2)

    return {
        "labels": labels,
        "q_score": [0, 0],
        "data1": {"code": c1, "history": c1_history, "color": "#ff8700"},
        "data2": {"code": c2, "history": c2_history, "color": "#00d2be"},
    }


@web_app.get("/{full_path:path}")
async def serve_mpa_or_static(full_path: str):
    # 1. Если это запрос к API - выдаем 404 (чтобы не отдавать HTML вместо данных)
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    # 2. Если путь пустой (корень) - отдаем главную
    if not full_path or full_path == "/":
        file_path = WEB_DIR / "index.html"
    else:
        file_path = WEB_DIR / full_path

    # 3. Отдаем точный файл, если он существует (например, картинку или стили)
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    # 4. Если запросили просто /season, ищем файл season.html
    html_file = WEB_DIR / f"{full_path}.html"
    if html_file.exists() and html_file.is_file():
        return FileResponse(str(html_file))

    # 5. SPA fallback: для React Router (drivers, compare, и т.д.) отдаем index.html
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))

    raise HTTPException(status_code=404, detail="Page not found")


# Модель для принятия данных с фронтенда
class NotificationToggle(BaseModel):
    is_enabled: bool


@web_app.get("/api/settings/notifications")
async def get_notifications(user_id: int = Depends(get_current_user_id)):
    settings = await get_user_settings(user_id)
    return {"is_enabled": settings.get("notifications_enabled", False)}


@web_app.post("/api/settings/notifications")
async def update_notifications(data: NotificationToggle, user_id: int = Depends(get_current_user_id)):
    await update_user_setting(user_id, "notifications_enabled", int(data.is_enabled))
    return {"status": "ok", "is_enabled": data.is_enabled}