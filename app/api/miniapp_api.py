import asyncio
import io
import os
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

# run_web.py imports this module directly, so load local configuration before
# app.db and authentication services read environment variables.
load_dotenv()

from app.db import (
    db,
    get_favorite_drivers, get_favorite_teams,
    remove_favorite_driver, add_favorite_driver,
    remove_favorite_team, add_favorite_team,
    get_user_settings, update_user_setting,
    save_race_vote, save_driver_vote, get_user_votes, get_race_vote_stats, get_driver_vote_stats,
    get_driver_vote_round_winners,
    get_reaction_profile, upsert_reaction_profile,
    save_reaction_score, get_reaction_leaderboard,
    save_reflex_grid_score, get_reflex_grid_leaderboard,
)
from app.api.auth_api import (
    get_optional_hybrid_telegram_id as get_optional_user_id,
    require_hybrid_telegram_id as get_current_user_id,
    router as auth_router,
)
from app.f1_data import (
    points_for_race_position,
    get_season_schedule_short_async,
    get_weekend_schedule,
    get_driver_standings_async,
    get_constructor_standings_async,
    get_driver_details_async,
    get_constructor_details_async,
    sort_standings_zero_last,
    _get_latest_quali_async,
    get_quali_for_round_async,
    get_race_results_async,
    get_sprint_results_async,
    get_sprint_quali_results_async,
    get_event_details_async,
    get_cached_quali_results,
    set_cached_quali_results,
    get_season_schedule_short,
)
from app.handlers.races import build_next_race_payload
from app.services.admin_feedback_service import send_admin_feedback
from app.services.prediction_service import (
    PREDICTION_FIELDS,
    PREDICTION_SCORING_RULES,
    get_prediction_context,
    get_prediction_drivers,
    get_prediction_leaderboard,
    get_prediction_profile,
    get_user_prediction,
    save_prediction_profile,
    save_user_prediction,
)
from app.utils.default import DRIVER_CODE_TO_FILE
from app.utils.image_render import _get_team_logo, get_car_image_path

# --- Настройка путей ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
WEB_DIR_LEGACY = PROJECT_ROOT / "web" / "app"
FRONT_DIR = PROJECT_ROOT / "front" / "dist"
# Используем React SPA (front) если собран, иначе web/app
WEB_DIR = FRONT_DIR if FRONT_DIR.exists() else WEB_DIR_LEGACY
STATIC_DIR = WEB_DIR / "static"
ASSETS_DIR = PROJECT_ROOT / "app" / "assets"

# --- Инициализация приложения ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.f1_data import init_redis_cache
    await db.connect()
    await db.init_tables()
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        await init_redis_cache(redis_url)
    try:
        yield
    finally:
        await db.close()


web_app = FastAPI(title="FormulaOneBot Mini App API", lifespan=lifespan)

web_origins = [
    origin.strip()
    for origin in os.getenv(
        "WEB_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=web_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_app.include_router(auth_router)


@web_app.get("/health", include_in_schema=False)
async def healthcheck():
    """Container/load-balancer readiness probe with a real SQLite check."""
    if db.conn is None:
        raise HTTPException(status_code=503, detail="database_not_ready")
    try:
        async with db.conn.execute("SELECT 1") as cursor:
            await cursor.fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database_unavailable") from exc
    return {"status": "ok", "database": "ready"}

if STATIC_DIR.exists():
    web_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if ASSETS_DIR.exists():
    web_app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# --- МОДЕЛИ ДАННЫХ ---

class NextRaceResponse(BaseModel):
    status: str
    season: int
    round: Optional[int] = None
    event_name: Optional[str] = None
    is_cancelled: Optional[bool] = False
    country: Optional[str] = None
    location: Optional[str] = None
    date: Optional[str] = None
    utc: Optional[str] = None
    local: Optional[str] = None
    fmt_date: Optional[str] = None
    race_start_utc: Optional[str] = None
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


class PredictionProfileRequest(BaseModel):
    display_name: str


class PredictionRequest(BaseModel):
    sprint_pole_driver: Optional[str] = None
    sprint_winner_driver: Optional[str] = None
    pole_driver: str
    winner_driver: str
    second_driver: str
    third_driver: str
    fourth_driver: str
    fifth_driver: str
    fastest_lap_driver: str
    first_retirement_driver: str
    safety_car: bool


class AdminFeedbackRequest(BaseModel):
    sender_name: str
    sender_contact: str
    message: str


# --- ЭНДПОИНТЫ ---

@web_app.get("/api/settings")
async def api_get_settings(user_id: Optional[int] = Depends(get_optional_user_id)):
    """Получить текущие настройки пользователя. Для гостя возвращает дефолт."""
    if user_id is None:
        return {"timezone": "UTC", "notify_before": 60, "notifications_enabled": False}
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


def _serialize_prediction(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        field: bool(row[field]) if field == "safety_car" else row[field]
        for field in PREDICTION_FIELDS
    } | {
        "points": row.get("points"),
        "max_points": row.get("max_points"),
        "updated_at": row.get("updated_at"),
    }


@web_app.get("/api/predictions/current")
async def api_prediction_current(user_id: int = Depends(get_current_user_id)):
    context = await get_prediction_context()
    profile = await get_prediction_profile(user_id)
    drivers = await get_prediction_drivers(int(context.get("season") or datetime.now(timezone.utc).year))
    prediction = None
    if context.get("round") is not None:
        prediction = await get_user_prediction(user_id, context["season"], context["round"])
    return {
        **context,
        "profile": profile,
        "drivers": drivers,
        "prediction": _serialize_prediction(prediction),
        "scoring_rules": PREDICTION_SCORING_RULES,
    }


@web_app.post("/api/predictions/profile")
async def api_prediction_profile(
    data: PredictionProfileRequest,
    user_id: int = Depends(get_current_user_id),
):
    try:
        return await save_prediction_profile(user_id, data.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@web_app.post("/api/predictions/current")
async def api_prediction_save(
    data: PredictionRequest,
    user_id: int = Depends(get_current_user_id),
):
    # Дедлайн повторно вычисляется на сервере в момент записи, поэтому обход блокировки UI невозможен.
    context = await get_prediction_context()
    if context.get("status") != "ok":
        raise HTTPException(status_code=503, detail="Расписание этапа временно недоступно")
    if not context.get("is_open"):
        raise HTTPException(status_code=409, detail="Приём прогнозов закрыт: квалификация уже началась")
    drivers = await get_prediction_drivers(context["season"])
    allowed_codes = {item["code"] for item in drivers}
    try:
        prediction = await save_user_prediction(
            user_id,
            context["season"],
            context["round"],
            data.model_dump(),
            allowed_driver_codes=allowed_codes or None,
            require_sprint=bool(context.get("has_sprint")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok", "prediction": _serialize_prediction(prediction)}


@web_app.get("/api/predictions/leaderboard")
async def api_prediction_leaderboard(_: int = Depends(get_current_user_id)):
    return await get_prediction_leaderboard()


@web_app.post("/api/contact-admin")
async def api_contact_admin(
    data: AdminFeedbackRequest,
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    try:
        feedback_id = await send_admin_feedback(
            sender_name=data.sender_name,
            sender_contact=data.sender_contact,
            message=data.message,
            telegram_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent", "id": feedback_id}


@web_app.get("/api/next-race", response_model=NextRaceResponse)
async def api_next_race(
        season: Optional[int] = None,
        user_id: Optional[int] = Depends(get_optional_user_id)
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
async def api_season(
        season: Optional[int] = Query(None),
        completed_only: bool = Query(False),
        session_type: str = Query("race"),
):
    if season is None:
        season = datetime.now().year
    races = await get_season_schedule_short_async(season)
    # Защита от "застывшего" async-кеша расписания (иногда обрезается до первых этапов).
    # Для текущего/будущего сезона при слишком коротком списке пробуем свежий sync-source.
    now_year = datetime.now().year
    if season >= now_year and races and len(races) < 8:
        try:
            fresh_races = await asyncio.to_thread(get_season_schedule_short, season)
            if fresh_races and len(fresh_races) > len(races):
                races = fresh_races
        except Exception:
            pass

    if completed_only and races:
        now_utc = datetime.now(timezone.utc)

        def _parse_session_dt(raw: Optional[str]) -> Optional[datetime]:
            if not raw:
                return None
            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None

        def _is_passed(r: dict) -> bool:
            st = (session_type or "race").lower()
            dt: Optional[datetime] = None
            if st == "quali":
                dt = _parse_session_dt(r.get("quali_start_utc"))
            elif st == "sprint":
                dt = _parse_session_dt(r.get("sprint_start_utc"))
            elif st in ("sprint_quali", "sprint-quali", "sprintquali"):
                dt = _parse_session_dt(r.get("sprint_quali_start_utc")) or _parse_session_dt(r.get("quali_start_utc"))
            else:
                dt = _parse_session_dt(r.get("race_start_utc"))

            if dt is not None:
                return dt <= now_utc

            # Fallback для старых/неполных расписаний
            date_str = r.get("date")
            if date_str:
                try:
                    return datetime.fromisoformat(date_str).date() <= now_utc.date()
                except Exception:
                    return False
            return False

        races = [r for r in races if _is_passed(r)]
    return {"season": season, "races": races}


# --- Голосования ---

class RaceVoteRequest(BaseModel):
    season: int
    round: int
    rating: int


class DriverVoteRequest(BaseModel):
    season: int
    round: int
    driver_code: str


class LeaderboardProfileRequest(BaseModel):
    display_name: Optional[str] = None
    participate: Optional[bool] = None
    prompt_seen: Optional[bool] = None


class ReactionScoreRequest(BaseModel):
    time_ms: int


class ReflexGridScoreRequest(BaseModel):
    mode: str
    difficulty: str
    score: int
    time_ms: int


@web_app.get("/api/votes/me")
async def api_votes_me(
    season: int = Query(...),
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    """Голоса пользователя за сезон для Telegram и связанной веб-сессии."""
    if user_id is None:
        return {"race_votes": {}, "driver_votes": {}}
    race_votes, driver_votes = await get_user_votes(user_id, season)
    return {"race_votes": race_votes, "driver_votes": driver_votes}


# --- Общий профиль и лидерборды мини-игр ---

@web_app.get("/api/reaction-leaderboard/profile")
async def api_game_leaderboard_profile(
    user_id: int = Depends(get_current_user_id),
):
    """Общее имя и настройка участия для обеих мини-игр."""
    return await get_reaction_profile(user_id)


@web_app.post("/api/reaction-leaderboard/profile")
async def api_game_leaderboard_profile_save(
    body: LeaderboardProfileRequest,
    user_id: int = Depends(get_current_user_id),
):
    profile = await upsert_reaction_profile(
        user_id,
        display_name=body.display_name,
        participate=body.participate,
        prompt_seen=body.prompt_seen,
    )
    return {"profile": profile}


@web_app.get("/api/reaction-leaderboard")
async def api_reaction_leaderboard(
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    return await get_reaction_leaderboard(user_id)


@web_app.post("/api/reaction-leaderboard/score")
async def api_reaction_leaderboard_score(
    body: ReactionScoreRequest,
    user_id: int = Depends(get_current_user_id),
):
    saved = await save_reaction_score(user_id, body.time_ms)
    return {"status": "ok", "saved": saved}


@web_app.get("/api/reflex-grid-leaderboard")
async def api_reflex_grid_leaderboard(
    mode: str = Query(...),
    difficulty: str = Query(...),
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    try:
        return await get_reflex_grid_leaderboard(mode, difficulty, user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@web_app.post("/api/reflex-grid-leaderboard/score")
async def api_reflex_grid_leaderboard_score(
    body: ReflexGridScoreRequest,
    user_id: int = Depends(get_current_user_id),
):
    try:
        saved = await save_reflex_grid_score(
            user_id,
            body.mode,
            body.difficulty,
            body.score,
            body.time_ms,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", "saved": saved}


@web_app.post("/api/votes/race")
async def api_votes_race(
    body: RaceVoteRequest,
    user_id: int = Depends(get_current_user_id),
):
    """Сохранить оценку гонки (1–5)."""
    if not 1 <= body.rating <= 5:
        raise HTTPException(400, "rating must be 1–5")
    await save_race_vote(user_id, body.season, body.round, body.rating)
    return {"status": "ok"}


@web_app.post("/api/votes/driver")
async def api_votes_driver(
    body: DriverVoteRequest,
    user_id: int = Depends(get_current_user_id),
):
    """Сохранить голос за пилота дня. Голосование закрывается через 3 дня после гонки."""
    schedule = await get_season_schedule_short_async(body.season)
    event = next((r for r in (schedule or []) if r.get("round") == body.round), None)
    if event and event.get("date"):
        try:
            race_date = datetime.fromisoformat(event["date"]).date()
            if datetime.now(timezone.utc).date() > race_date + timedelta(days=3):
                raise HTTPException(400, "Голосование за пилота дня закрыто (3 дня после гонки)")
        except HTTPException:
            raise
        except Exception:
            pass
    await save_driver_vote(user_id, body.season, body.round, body.driver_code)
    return {"status": "ok"}


@web_app.get("/api/votes/stats")
async def api_votes_stats(season: int = Query(...)):
    """Средние оценки гонок для графика [(round, avg, count), ...]."""
    stats = await get_race_vote_stats(season)
    return {"stats": [{"round": r, "avg": a, "count": c} for r, a, c in stats]}


@web_app.get("/api/votes/driver-stats")
async def api_votes_driver_stats(season: int = Query(...)):
    """Сезонная статистика и победитель «Пилота дня» каждого этапа."""
    stats = await get_driver_vote_stats(season)
    round_winners = await get_driver_vote_round_winners(season)
    return {
        "stats": [{"driver_code": d, "count": c} for d, c in stats],
        "round_winners": [
            {"round": round_num, "driver_code": driver_code, "count": count}
            for round_num, driver_code, count in round_winners
        ],
    }


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

        driver_id = getattr(row, "driverId", "") or (driver_code.lower() if driver_code else "")
        results.append({
            "position": getattr(row, "position", ""),
            "points": getattr(row, "points", 0),
            "code": driver_code,
            "name": f"{getattr(row, 'givenName', '')} {getattr(row, 'familyName', '')}",
            "is_favorite": driver_code in favorite_drivers,
            "number": getattr(row, "permanentNumber", "") or "",
            "constructorId": getattr(row, "constructorId", "") or "",
            "constructorName": getattr(row, "constructorName", "") or "",
            "driverId": driver_id,
        })

    return {"season": season, "round": round_number, "drivers": results}


@web_app.get("/api/driver-details")
async def api_driver_details(
    code: Optional[str] = Query(None, description="Driver code (e.g. ALO)"),
    driver_id: Optional[str] = Query(None, alias="driverId", description="Ergast driverId (e.g. alonso)"),
    season: Optional[int] = Query(None),
):
    """Карточка пилота: профиль, статистика сезона и карьеры, биография."""
    if season is None:
        season = datetime.now().year
    did = (driver_id or "").strip().lower()
    code_str = (code or "").strip().upper()
    if not did and not code_str:
        raise HTTPException(status_code=400, detail="Укажите code или driverId")

    # driverId из OpenF1 бывает числом (23, 44) — не Ergast driverId, нужен resolve через code
    if did.isdigit() and code_str:
        did = code_str.lower()

    # Если driverId выглядит как валидный Ergast ID (>3 символов, не число) — используем его напрямую
    # Если driverId короткий (3 символа = code) — resolve через get_driver_details_async
    details = await get_driver_details_async(did or code_str.lower(), season, code_str or None)

    # Фоллбэк: если не нашлось по driverId — пробуем по code
    if not details and code_str and did != code_str.lower():
        details = await get_driver_details_async(code_str.lower(), season, code_str)
    # Фоллбэк: если не нашлось по code — пробуем по оригинальному driverId (если отличается)
    if not details and driver_id and did != (driver_id or "").strip().lower():
        details = await get_driver_details_async((driver_id or "").strip().lower(), season, code_str or None)
    if not details:
        raise HTTPException(status_code=404, detail="Пилот не найден")
    return details


@web_app.get("/api/constructor-details")
async def api_constructor_details(
    constructorId: Optional[str] = Query(None, description="constructorId (e.g. ferrari)"),
    season: Optional[int] = Query(None),
):
    """Карточка команды: профиль, статистика сезона и карьеры, биография."""
    if season is None:
        season = datetime.now().year
    cid = (constructorId or "").strip().lower().replace(" ", "_")
    if not cid:
        raise HTTPException(status_code=400, detail="Укажите constructorId")
    details = await get_constructor_details_async(cid, season)
    if not details:
        raise HTTPException(status_code=404, detail="Команда не найдена")
    return details


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


@web_app.get("/api/car-image")
async def api_car_image(
    team: str = Query(..., description="Название команды (Alpine, Ferrari и т.д.)"),
    season: Optional[int] = Query(None),
):
    """Возвращает изображение машины команды. Ищет в assets/{year}/cars/, fallback — assets/car/."""
    if season is None:
        season = datetime.now().year
    path = await asyncio.to_thread(get_car_image_path, team, season)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Изображение машины не найдено")
    suffix = path.suffix.lower()
    media_type = "image/avif" if suffix == ".avif" else "image/png" if suffix == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type)


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


PILOT_FALLBACK_PATH = PROJECT_ROOT / "app" / "assets" / "pilot" / "pilot.png"
PILOT_HEAD_CROP_RATIO = 0.35


def _normalize_key(text: str) -> str:
    s = (text or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in s if ch.isalnum())


def _find_local_pilot_portrait_path(season: int, code: str | None, name: str | None) -> Path | None:
    pilots_dir = PROJECT_ROOT / "app" / "assets" / str(season) / "pilots"
    if not pilots_dir.exists():
        return None

    candidates = []
    if name:
        candidates.append(name)
    if code:
        mapped = DRIVER_CODE_TO_FILE.get(code.upper(), "")
        if mapped:
            candidates.append(Path(mapped).stem)
        candidates.append(code)

    norm_candidates = {_normalize_key(c) for c in candidates if c}
    if not norm_candidates:
        return None

    for file_path in pilots_dir.iterdir():
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
            continue
        file_norm = _normalize_key(file_path.stem.strip())
        if any(c and (c in file_norm or file_norm in c) for c in norm_candidates):
            return file_path
    return None


def _render_head_crop_png_bytes(path: Path) -> bytes:
    with Image.open(path) as img:
        base = img.convert("RGBA")
        w, h = base.size
        alpha_extrema = base.getchannel("A").getextrema()
        is_transparent_square_portrait = h <= int(w * 1.25) and alpha_extrema[0] < 255
        if is_transparent_square_portrait:
            # Готовые квадратные headshot-ассеты уже скомпонованы вокруг лица.
            # Повторный кроп срезал подбородок и форму у портретов 2025 года.
            head = base
        else:
            # Высокие ростовые портреты 2026: берём верхнюю часть без
            # обратного растягивания, чтобы лицо оставалось пропорциональным.
            crop_h = max(1, int(h * PILOT_HEAD_CROP_RATIO))
            head = base.crop((0, 0, w, crop_h))
        buf = io.BytesIO()
        head.save(buf, format="PNG")
        return buf.getvalue()


@web_app.get("/api/pilot-portrait")
async def api_pilot_portrait(
    season: Optional[int] = Query(None),
    code: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
):
    """Портрет пилота: local assets/{season}/pilots с кропом головы, fallback на дефолтный."""
    if season is None:
        season = datetime.now().year

    local_path = _find_local_pilot_portrait_path(season, code, name)
    if local_path and local_path.exists():
        try:
            png_bytes = await asyncio.to_thread(_render_head_crop_png_bytes, local_path)
            return Response(content=png_bytes, media_type="image/png")
        except Exception:
            pass

    if PILOT_FALLBACK_PATH.exists():
        return FileResponse(str(PILOT_FALLBACK_PATH), media_type="image/png")
    raise HTTPException(status_code=404, detail="Default portrait not found")


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


def _get_last_completed_race(schedule: list, now: datetime) -> dict | None:
    """Последний этап, гонка которого уже завершилась (race_start + 1ч для обычных, +9ч для тестов)."""
    finished_event = None
    for r in schedule:
        if not r.get("race_start_utc"):
            continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None:
                race_dt = race_dt.replace(tzinfo=timezone.utc)
            finish_offset = 9 if r.get("is_testing") else 1
            if now > race_dt + timedelta(hours=finish_offset):
                finished_event = r
            else:
                break
        except Exception:
            continue
    return finished_event


def _parse_utc_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _get_latest_started_weekend_round(schedule: list, now: datetime) -> Optional[int]:
    """
    Возвращает round самого позднего этапа, у которого уже стартовала первая сессия уикенда.
    Используем для скрытия прошлых результатов после старта нового уикенда.
    """
    latest_started_round = None
    for r in schedule:
        candidates = []
        for key in (
            "first_session_start_utc",
            "sprint_quali_start_utc",
            "quali_start_utc",
            "sprint_start_utc",
            "race_start_utc",
        ):
            dt = _parse_utc_iso(r.get(key))
            if dt is not None:
                candidates.append(dt)

        if not candidates:
            continue

        weekend_start = min(candidates)
        if weekend_start <= now:
            latest_started_round = r.get("round")
        else:
            break

    return latest_started_round


def _should_reset_previous_results(schedule: list, now: datetime, results_round: Optional[int]) -> bool:
    if results_round is None:
        return False
    started_round = _get_latest_started_weekend_round(schedule, now)
    if started_round is None:
        return False
    try:
        return int(results_round) < int(started_round)
    except Exception:
        return False


def _empty_results_payload_during_active_weekend(schedule: list, now: datetime, season: int) -> dict:
    started_round = _get_latest_started_weekend_round(schedule, now)
    race_info = next((r for r in schedule if r.get("round") == started_round), None) if started_round else None
    return {"results": [], "race_info": race_info, "season": season, "round": started_round}


def _build_race_results(df: pd.DataFrame, fav_drivers: set, fav_teams: set) -> tuple[list[dict], bool]:
    """
    Преобразует DataFrame результатов гонки в API-список.
    Возвращает (results, data_incomplete).
    """
    results: list[dict] = []
    data_incomplete = False

    if "Position" in df.columns:
        df = df.sort_values("Position")

    for row in df.itertuples(index=False):
        try:
            pos = int(getattr(row, "Position", 0))
            code = getattr(row, "Abbreviation", "") or getattr(row, "DriverNumber", "")
            given = getattr(row, "FirstName", "")
            family = getattr(row, "LastName", "")
            full_name = f"{given} {family}".strip() or code
            team = getattr(row, "TeamName", "")
            points = float(getattr(row, "Points", 0))
            if points == 0:
                points = points_for_race_position(pos)

            if code == "?" or (full_name and "?" in str(full_name)):
                data_incomplete = True
            if full_name and full_name.strip() == "":
                data_incomplete = True

            results.append({
                "position": pos,
                "code": code,
                "name": full_name,
                "team": team,
                "points": points,
                "is_favorite_driver": code in fav_drivers,
                "is_favorite_team": team in fav_teams
            })
        except Exception:
            continue

    return results, data_incomplete


@web_app.get("/api/race-results")
async def api_race_results(
        user_id: Optional[int] = Depends(get_optional_user_id),
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None, alias="round"),
):
    if season is None:
        season = datetime.now().year

    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"results": [], "race_info": None, "season": season, "round": round_number}
    try:
        schedule = sorted(schedule, key=lambda r: int(r.get("round") or 10 ** 9))
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    completed_rounds: list[int] = []
    if round_number is not None:
        round_num = round_number
        race_info = next((r for r in schedule if r.get("round") == round_num), None)
        df = await get_race_results_async(season, round_num)
    else:
        for r in schedule:
            if not r.get("race_start_utc"):
                continue
            try:
                race_dt = datetime.fromisoformat(r["race_start_utc"])
                if race_dt.tzinfo is None:
                    race_dt = race_dt.replace(tzinfo=timezone.utc)
                finish_offset = 9 if r.get("is_testing") else 1
                if now > race_dt + timedelta(hours=finish_offset):
                    completed_rounds.append(int(r["round"]))
                else:
                    break
            except Exception:
                continue

        if not completed_rounds:
            return {"results": [], "race_info": None, "season": season, "round": None}

        latest_completed_round = completed_rounds[-1]
        if _should_reset_previous_results(schedule, now, latest_completed_round):
            started_round = _get_latest_started_weekend_round(schedule, now)
            if started_round is not None:
                started_df = await get_race_results_async(season, started_round)
                if started_df is not None and not started_df.empty:
                    round_num = started_round
                    race_info = next((r for r in schedule if r.get("round") == round_num), None)
                    df = started_df
                else:
                    return _empty_results_payload_during_active_weekend(schedule, now, season)
            else:
                return _empty_results_payload_during_active_weekend(schedule, now, season)
        else:
            round_num = latest_completed_round
            race_info = next((r for r in schedule if r.get("round") == round_num), None)
            df = await get_race_results_async(season, round_num)

        if df is None or df.empty:
            # UX fallback: если у последнего завершенного этапа пусто, ищем ближайший предыдущий с данными.
            for rn in reversed(completed_rounds[:-1]):
                candidate_df = await get_race_results_async(season, rn)
                if candidate_df is not None and not candidate_df.empty:
                    round_num = rn
                    race_info = next((r for r in schedule if r.get("round") == rn), None)
                    df = candidate_df
                    break

    if df is None or df.empty:
        return {"results": [], "race_info": race_info, "season": season, "round": round_num}

    fav_drivers = set()
    fav_teams = set()
    if user_id:
        fav_drivers = set(await get_favorite_drivers(user_id))
        fav_teams = set(await get_favorite_teams(user_id))

    results, data_incomplete = _build_race_results(df, fav_drivers, fav_teams)

    if data_incomplete:
        # Для latest-режима пробуем предыдущие завершенные этапы, если текущий пришел "грязным".
        if round_number is None and completed_rounds:
            try:
                current_round = int(round_num)
            except Exception:
                current_round = None
            prev_rounds = [rn for rn in completed_rounds if current_round is None or rn < current_round]
            for rn in reversed(prev_rounds):
                candidate_df = await get_race_results_async(season, rn)
                if candidate_df is None or candidate_df.empty:
                    continue
                candidate_results, candidate_incomplete = _build_race_results(candidate_df, fav_drivers, fav_teams)
                if candidate_results and not candidate_incomplete:
                    return {
                        "season": season,
                        "round": rn,
                        "race_info": next((r for r in schedule if r.get("round") == rn), None),
                        "results": candidate_results,
                        "data_incomplete": False,
                    }
        return {
            "results": [],
            "race_info": race_info,
            "season": season,
            "round": round_num,
            "data_incomplete": True,
        }

    return {
        "season": season,
        "round": round_num,
        "race_info": race_info,
        "results": results,
        "data_incomplete": False,
    }


@web_app.get("/api/sprint-results")
async def api_sprint_results(
        user_id: Optional[int] = Depends(get_optional_user_id),
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None, alias="round"),
):
    if season is None:
        season = datetime.now().year
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"results": [], "race_info": None, "season": season, "round": None}

    now_utc = datetime.now(timezone.utc)
    if round_number is not None:
        round_num = round_number
        race_info = next((r for r in schedule if r.get("round") == round_num), None)
        df = await get_sprint_results_async(season, round_num)
        if df is None or df.empty:
            return {"results": [], "race_info": race_info, "season": season, "round": round_num}
    else:
        passed_rounds = []
        for r in schedule:
            try:
                if r.get("sprint_start_utc"):
                    sprint_dt = datetime.fromisoformat(r["sprint_start_utc"])
                    if sprint_dt.tzinfo is None:
                        sprint_dt = sprint_dt.replace(tzinfo=timezone.utc)
                    if sprint_dt <= now_utc:
                        passed_rounds.append(r["round"])
                    continue
                # Фоллбэк для старых расписаний без sprint_start_utc
                if r.get("date") and datetime.fromisoformat(r["date"]).date() <= now_utc.date():
                    passed_rounds.append(r["round"])
            except Exception:
                continue

        if not passed_rounds:
            return {"results": [], "race_info": None, "season": season, "round": None}

        round_num = None
        df = pd.DataFrame()
        for rn in reversed(passed_rounds):
            sprint_df = await get_sprint_results_async(season, rn)
            if sprint_df is not None and not sprint_df.empty:
                round_num = rn
                df = sprint_df
                break

        if round_num is None or df.empty:
            return {"results": [], "race_info": None, "season": season, "round": None}

        if _should_reset_previous_results(schedule, now_utc, round_num):
            return _empty_results_payload_during_active_weekend(schedule, now_utc, season)

        race_info = next((r for r in schedule if r.get("round") == round_num), None)

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
            full_name = f"{given} {family}".strip() or code
            team = getattr(row, "TeamName", "")
            points = float(getattr(row, "Points", 0))
            if points == 0:
                points = points_for_race_position(pos)
            results.append({
                "position": pos,
                "code": code,
                "name": full_name,
                "team": team,
                "points": points,
                "is_favorite_driver": code in fav_drivers,
                "is_favorite_team": team in fav_teams
            })
        except Exception:
            continue

    return {
        "season": season,
        "round": round_num,
        "race_info": race_info,
        "results": results,
    }


def _segment_by_position(pos: int) -> str:
    if pos <= 10:
        return "Q3"
    if pos <= 16:
        return "Q2"
    return "Q1"


@web_app.get("/api/quali-results")
async def api_quali_results(
        user_id: Optional[int] = Depends(get_optional_user_id),
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None, alias="round"),
):
    def _has_meaningful_quali_data(rows: list[dict]) -> bool:
        if not rows:
            return False
        good_rows = 0
        for row in rows:
            name = str(row.get("name") or "").strip()
            driver = str(row.get("driver") or "").strip()
            best = str(row.get("best") or "").strip()
            has_identity = name not in {"", "?"} or driver not in {"", "?"}
            has_time = best not in {"", "-", "—"}
            if has_identity and has_time:
                good_rows += 1
        min_good = min(5, len(rows))
        return good_rows >= max(2, min_good)

    if season is None:
        season = datetime.now().year
    now_utc = datetime.now(timezone.utc)
    schedule = await get_season_schedule_short_async(season)
    if round_number is not None:
        round_num = round_number
        try:
            round_num, q_results = await get_quali_for_round_async(season, round_number, limit=100)
        except Exception:
            q_results = []
        race_info = next((r for r in (schedule or []) if r.get("round") == round_num), None)
        results = []
        for r in q_results:
            pos = r.get("position", 0)
            results.append({
                "position": pos,
                "driver": r["driver"],
                "name": r.get("name", ""),
                "best": r.get("best", "-"),
                "segment": _segment_by_position(pos),
            })
        base_payload = {
            "season": season,
            "round": round_num,
            "race_info": race_info,
            "results": results,
        }
    else:
        cached = await get_cached_quali_results(season)
        base_payload = cached if cached else None

        if base_payload is None:
            data = await _get_latest_quali_async(season, limit=100)
            if not data:
                if cached:
                    base_payload = cached
                else:
                    base_payload = {"results": [], "race_info": None, "season": season, "round": None}
            else:
                round_num, q_results = data
                race_info = next((r for r in (schedule or []) if r["round"] == round_num), None)

                results = []
                for r in q_results:
                    pos = r.get("position", 0)
                    results.append({
                        "position": pos,
                        "driver": r["driver"],
                        "name": r.get("name", ""),
                        "best": r.get("best", "-"),
                        "segment": _segment_by_position(pos),
                    })

                base_payload = {
                    "season": season,
                    "round": round_num,
                    "race_info": race_info,
                    "results": results,
                }
                # OpenF1 иногда отдает "пустые" строки (имена '?', время '-').
                # В таком случае лучше оставить последний валидный кэш для фронта.
                if cached and not _has_meaningful_quali_data(results) and _has_meaningful_quali_data(cached.get("results", [])):
                    base_payload = cached
                else:
                    await set_cached_quali_results(season, base_payload)

        if _should_reset_previous_results(schedule or [], now_utc, base_payload.get("round")):
            started_round = _get_latest_started_weekend_round(schedule or [], now_utc)
            if started_round is None:
                return _empty_results_payload_during_active_weekend(schedule or [], now_utc, season)
            try:
                started_round_num, started_q_results = await get_quali_for_round_async(season, started_round, limit=100)
            except Exception:
                started_round_num, started_q_results = started_round, []
            if not started_q_results:
                return _empty_results_payload_during_active_weekend(schedule or [], now_utc, season)

            race_info = next((r for r in (schedule or []) if r.get("round") == started_round_num), None)
            started_results = []
            for r in started_q_results:
                pos = r.get("position", 0)
                started_results.append({
                    "position": pos,
                    "driver": r["driver"],
                    "name": r.get("name", ""),
                    "best": r.get("best", "-"),
                    "segment": _segment_by_position(pos),
                })
            base_payload = {
                "season": season,
                "round": started_round_num,
                "race_info": race_info,
                "results": started_results,
            }
            await set_cached_quali_results(season, base_payload)

    # Персональная отметка избранных пилотов: только в ответе, не в кэше.
    if not user_id:
        return base_payload

    fav_drivers = {str(code).upper() for code in (await get_favorite_drivers(user_id))}
    if not fav_drivers:
        return base_payload

    results_with_favs = []
    for row in base_payload.get("results", []):
        driver_code = str(row.get("driver", "")).upper()
        results_with_favs.append({
            **row,
            "is_favorite_driver": driver_code in fav_drivers,
        })

    return {
        **base_payload,
        "results": results_with_favs,
    }


@web_app.get("/api/sprint-quali-results")
async def api_sprint_quali_results(
        user_id: Optional[int] = Depends(get_optional_user_id),
        season: Optional[int] = Query(None),
        round_number: Optional[int] = Query(None, alias="round"),
):
    if season is None:
        season = datetime.now().year
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"results": [], "race_info": None, "season": season, "round": None}

    now_utc = datetime.now(timezone.utc)
    if round_number is not None:
        round_num = round_number
        sq_results = await get_sprint_quali_results_async(season, round_num, limit=100)
        race_info = next((r for r in schedule if r.get("round") == round_num), None)
        if not sq_results:
            return {"results": [], "race_info": race_info, "season": season, "round": round_num}
    else:
        passed_rounds = []
        for r in schedule:
            try:
                sq_dt = None
                if r.get("sprint_quali_start_utc"):
                    sq_dt = datetime.fromisoformat(r["sprint_quali_start_utc"])
                elif r.get("quali_start_utc"):
                    sq_dt = datetime.fromisoformat(r["quali_start_utc"])
                if sq_dt is not None:
                    if sq_dt.tzinfo is None:
                        sq_dt = sq_dt.replace(tzinfo=timezone.utc)
                    if sq_dt <= now_utc:
                        passed_rounds.append(r["round"])
                    continue
                # Фоллбэк для старых расписаний без sprint_quali_start_utc
                if r.get("date") and datetime.fromisoformat(r["date"]).date() <= now_utc.date():
                    passed_rounds.append(r["round"])
            except Exception:
                continue

        if not passed_rounds:
            return {"results": [], "race_info": None, "season": season, "round": None}

        round_num = None
        sq_results = []
        for rn in reversed(passed_rounds):
            data = await get_sprint_quali_results_async(season, rn, limit=100)
            if data:
                round_num = rn
                sq_results = data
                break

        if round_num is None or not sq_results:
            return {"results": [], "race_info": None, "season": season, "round": None}

        if _should_reset_previous_results(schedule, now_utc, round_num):
            return _empty_results_payload_during_active_weekend(schedule, now_utc, season)

        race_info = next((r for r in schedule if r.get("round") == round_num), None)
    fav_drivers = set()
    if user_id:
        fav_drivers = {str(code).upper() for code in (await get_favorite_drivers(user_id))}
    results = []
    for r in sq_results:
        pos = r.get("position", 0)
        driver_code = r.get("driver", "")
        results.append({
            "position": pos,
            "driver": driver_code,
            "name": r.get("name", ""),
            "best": r.get("best", "-"),
            "segment": _segment_by_position(pos),
            "is_favorite_driver": str(driver_code).upper() in fav_drivers,
        })

    return {
        "season": season,
        "round": round_num,
        "race_info": race_info,
        "results": results,
    }


@web_app.get("/api/race-details")
async def api_race_details(
        season: int = Query(..., description="Год сезона"),
        round_number: int = Query(..., description="Номер этапа", alias="round")
):
    """Возвращает полную инфу о трассе и расписание уикенда"""
    data = await get_event_details_async(season, round_number)

    if not data:
        # Fallback: если FastF1 не отдал event details, пробуем собрать минимум из сезонного расписания.
        schedule = await get_season_schedule_short_async(season)
        race = next((r for r in (schedule or []) if int(r.get("round", 0)) == int(round_number)), None)
        if not race:
            raise HTTPException(status_code=404, detail="Race not found")
        data = {
            "round": round_number,
            "event_name": race.get("event_name") or f"Round {round_number}",
            "official_name": race.get("event_name") or "",
            "country": race.get("country") or "",
            "location": race.get("location") or "",
            "event_format": "",
            "sessions": get_weekend_schedule(season, round_number) or [],
        }

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


def _get_last_completed_race_round_for_standings(schedule: list) -> int | None:
    """Номер последнего завершённого этапа (для standings)."""
    ev = _get_last_completed_race(schedule, datetime.now(timezone.utc))
    return ev["round"] if ev else None


def _get_passed_races(schedule: list, now: datetime) -> list:
    """Этапы, гонки которых уже завершились (логика как в _get_last_completed_race)."""
    passed = []
    for r in schedule:
        if not r.get("race_start_utc"):
            # Fallback для расписаний без race_start_utc (например, в тестовых моках):
            # считаем этап прошедшим, если его дата <= текущей UTC-даты.
            try:
                date_str = r.get("date")
                if date_str and datetime.fromisoformat(date_str).date() <= now.date():
                    passed.append(r)
                else:
                    break
            except Exception:
                continue
            continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None:
                race_dt = race_dt.replace(tzinfo=timezone.utc)
            finish_offset = 9 if r.get("is_testing") else 1
            if now > race_dt + timedelta(hours=finish_offset):
                passed.append(r)
            else:
                break
        except Exception:
            continue
    return passed


async def _build_driver_comparison(driver_codes: list[str], season: int):
    """Load one season once and build comparable series for any number of drivers."""
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"error": f"Нет расписания на {season} год"}

    now = datetime.now(timezone.utc)
    passed_races = _get_passed_races(schedule, now)
    preloaded_race_results: dict[int, pd.DataFrame] = {}

    # Если гонка уже стартовала, но еще не прошёл буфер +1ч, и результаты уже доступны,
    # включаем этап в сравнение сразу.
    latest_started_race = None
    for r in schedule:
        race_start_utc = r.get("race_start_utc")
        if not race_start_utc:
            continue
        try:
            race_dt = datetime.fromisoformat(race_start_utc)
            if race_dt.tzinfo is None:
                race_dt = race_dt.replace(tzinfo=timezone.utc)
            if race_dt <= now:
                latest_started_race = r
            else:
                break
        except Exception:
            continue

    if latest_started_race is not None:
        passed_rounds = {int(r.get("round", 0)) for r in passed_races}
        latest_round = int(latest_started_race.get("round") or 0)
        if latest_round > 0 and latest_round not in passed_rounds:
            latest_df = await get_race_results_async(season, latest_round)
            if latest_df is not None and not latest_df.empty:
                passed_races.append(latest_started_race)
                preloaded_race_results[latest_round] = latest_df

    if not passed_races:
        return {"error": f"В {season} году еще не было прошедших гонок для сравнения."}

    labels: list[str] = []
    quali_tasks = []
    rounds: list[int] = []
    missing_race_rounds: list[int] = []
    race_tasks = []

    for race in passed_races:
        round_num = race["round"]
        rounds.append(round_num)
        labels.append(race.get("event_name", f"Этап {round_num}").replace(" Grand Prix", "").replace("Gp", ""))
        if round_num not in preloaded_race_results:
            missing_race_rounds.append(round_num)
            race_tasks.append(get_race_results_async(season, round_num))
        quali_tasks.append(get_quali_for_round_async(season, round_num, limit=100))

    loaded_race_results = await asyncio.gather(*race_tasks, return_exceptions=True)
    race_by_round: dict[int, pd.DataFrame | Exception] = dict(preloaded_race_results)
    for rn, loaded in zip(missing_race_rounds, loaded_race_results):
        race_by_round[rn] = loaded
    race_results = [race_by_round.get(rn, pd.DataFrame()) for rn in rounds]
    quali_results = await asyncio.gather(*quali_tasks, return_exceptions=True)

    histories: dict[str, list[float]] = {code: [] for code in driver_codes}
    race_wins: dict[str, int] = {code: 0 for code in driver_codes}
    quali_wins: dict[str, int] = {code: 0 for code in driver_codes}

    for df, quali_payload in zip(race_results, quali_results):
        round_points: dict[str, float] = {code: 0.0 for code in driver_codes}
        grid_positions: dict[str, int] = {}

        if df is not None and not isinstance(df, Exception) and not df.empty:
            if "Abbreviation" in df.columns:
                df = df.copy()
                df["Abbreviation"] = df["Abbreviation"].fillna("").astype(str).str.upper()
            else:
                df = df.copy()
                df["Abbreviation"] = ""

            for code in driver_codes:
                row = df[df["Abbreviation"] == code]
                if row.empty:
                    continue
                race_row = row.iloc[0]
                points_value = race_row.get("Points", 0)
                points = 0.0 if pd.isna(points_value) else float(points_value)
                if points == 0:
                    position = race_row.get("Position")
                    if position is not None and not pd.isna(position):
                        points = float(points_for_race_position(int(position)))
                round_points[code] = points

                grid = race_row.get(
                    "GridPosition",
                    race_row.get("Grid", None),
                )
                if grid is not None and not pd.isna(grid):
                    try:
                        grid_positions[code] = int(float(grid))
                    except (TypeError, ValueError):
                        pass

        for code in driver_codes:
            histories[code].append(round_points[code])

        best_points = max(round_points.values(), default=0)
        if best_points > 0:
            for code, points in round_points.items():
                if points == best_points:
                    race_wins[code] += 1

        # Direct qualifying results take precedence over the race grid.
        qualifying_positions: dict[str, int] = {}
        if not isinstance(quali_payload, Exception):
            q_rows = []
            if isinstance(quali_payload, tuple) and len(quali_payload) >= 2:
                q_rows = quali_payload[1] or []
            elif isinstance(quali_payload, list):
                q_rows = quali_payload
            for q_row in q_rows:
                code = str(q_row.get("driver", "")).upper()
                if code not in histories:
                    continue
                try:
                    qualifying_positions[code] = int(q_row.get("position"))
                except (TypeError, ValueError):
                    continue

        positions_for_comparison = qualifying_positions or grid_positions
        if positions_for_comparison:
            best_position = min(positions_for_comparison.values())
            for code, position in positions_for_comparison.items():
                if position == best_position:
                    quali_wins[code] += 1

    return {
        "labels": labels,
        "series": [
            {
                "code": code,
                "history": histories[code],
                "race_wins": race_wins[code],
                "quali_wins": quali_wins[code],
                "total_points": round(sum(histories[code]), 3),
                "average_points": (
                    round(sum(histories[code]) / len(histories[code]), 3)
                    if histories[code]
                    else 0
                ),
            }
            for code in driver_codes
        ],
    }


@web_app.get("/api/compare/multi")
async def api_compare_multi(
    drivers: str = Query(..., min_length=1),
    season: int = Query(2026),
):
    """Compare one or more season drivers in a single data load."""
    driver_codes = list(
        dict.fromkeys(
            code.strip().upper()
            for code in drivers.split(",")
            if code.strip()
        )
    )
    if not driver_codes:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одного пилота")
    if len(driver_codes) > 30:
        raise HTTPException(status_code=400, detail="Слишком много пилотов для сравнения")
    return await _build_driver_comparison(driver_codes, season)


@web_app.get("/api/compare")
async def api_compare(d1: str, d2: str, season: int = 2026):
    """Backward-compatible pair comparison for existing clients."""
    codes = [d1.strip().upper(), d2.strip().upper()]
    payload = await _build_driver_comparison(codes, season)
    if payload.get("error"):
        return payload
    series = payload["series"]
    return {
        "labels": payload["labels"],
        "q_score": [series[0]["quali_wins"], series[1]["quali_wins"]],
        "data1": {
            "code": series[0]["code"],
            "history": series[0]["history"],
            "color": "#ff8700",
        },
        "data2": {
            "code": series[1]["code"],
            "history": series[1]["history"],
            "color": "#00d2be",
        },
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


def _team_points_for_comparison(df: pd.DataFrame, team_name: str) -> float:
    """Return one constructor's points from a race result table."""
    if df is None or isinstance(df, Exception) or df.empty:
        return 0.0
    col = "TeamName" if "TeamName" in df.columns else "Constructor"
    if col not in df.columns:
        return 0.0
    mask = df[col].apply(lambda value: _team_matches(team_name, value))
    team_rows = df[mask]
    if team_rows.empty:
        return 0.0
    pts_col = "Points" if "Points" in df.columns else ("points" if "points" in df.columns else None)
    points = team_rows[pts_col].fillna(0).astype(float).sum() if pts_col else 0
    if points == 0 and "Position" in team_rows.columns:
        for position in team_rows["Position"]:
            if position is not None and pd.notna(position):
                try:
                    points += points_for_race_position(int(position))
                except (TypeError, ValueError):
                    pass
    return float(points)


async def _build_team_comparison(team_names: list[str], season: int):
    """Load a season once and build comparison series for any number of teams."""
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"error": f"Нет расписания на {season} год"}

    now = datetime.now(timezone.utc)
    passed_races = _get_passed_races(schedule, now)

    if not passed_races:
        return {"error": f"В {season} году ещё не было прошедших гонок для сравнения."}

    labels: list[str] = []
    tasks = []
    for race in passed_races:
        round_num = race["round"]
        labels.append(race.get("event_name", f"Этап {round_num}").replace(" Grand Prix", "").replace("Gp", ""))
        tasks.append(get_race_results_async(season, round_num))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    histories: dict[str, list[float]] = {name: [] for name in team_names}
    race_wins: dict[str, int] = {name: 0 for name in team_names}

    for df in results:
        round_points = {
            name: (
                _team_points_for_comparison(df, name)
                if isinstance(df, pd.DataFrame)
                else 0.0
            )
            for name in team_names
        }
        for name, points in round_points.items():
            histories[name].append(points)
        best_points = max(round_points.values(), default=0)
        if best_points > 0:
            for name, points in round_points.items():
                if points == best_points:
                    race_wins[name] += 1

    return {
        "labels": labels,
        "series": [
            {
                "code": name,
                "history": histories[name],
                "race_wins": race_wins[name],
                "quali_wins": 0,
                "total_points": round(sum(histories[name]), 3),
                "average_points": (
                    round(sum(histories[name]) / len(histories[name]), 3)
                    if histories[name]
                    else 0
                ),
            }
            for name in team_names
        ],
    }


@web_app.get("/api/compare/teams/multi")
async def api_compare_teams_multi(
    teams: str = Query(..., min_length=1),
    season: int = Query(...),
):
    """Compare one or more constructors in a single data load."""
    team_names = list(
        dict.fromkeys(
            name.strip()
            for name in teams.split(",")
            if name.strip()
        )
    )
    if not team_names:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одну команду")
    if len(team_names) > 20:
        raise HTTPException(status_code=400, detail="Слишком много команд для сравнения")
    return await _build_team_comparison(team_names, season)


@web_app.get("/api/compare/teams")
async def api_compare_teams(c1: str, c2: str, season: int = Query(...)):
    """Backward-compatible pair constructor comparison."""
    payload = await _build_team_comparison([c1.strip(), c2.strip()], season)
    if payload.get("error"):
        return payload
    series = payload["series"]
    return {
        "labels": payload["labels"],
        "q_score": [0, 0],
        "data1": {
            "code": series[0]["code"],
            "history": series[0]["history"],
            "color": "#ff8700",
        },
        "data2": {
            "code": series[1]["code"],
            "history": series[1]["history"],
            "color": "#00d2be",
        },
    }


# Модель для принятия данных с фронтенда (до catch-all, чтобы эндпоинты матчились)
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
