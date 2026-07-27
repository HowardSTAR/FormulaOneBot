"""Role-protected administration API.

Every mutation uses the existing cookie-session CSRF validation from
``require_web_session`` and is also written to an immutable audit trail.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import aiosqlite
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.auth_api import (
    COOKIE_NAME,
    WebSessionContext,
    get_auth_service,
    require_web_session,
)
from app.auth import get_current_user_id as get_telegram_user_id
from app.db import db
from app.emailer import EmailDeliveryError
from app.f1_data import get_season_schedule_short_async
from app.services.activity_service import is_primary_admin, record_user_activity, utc_iso
from app.services.auth_service import AuthError, normalize_email
from app.services.prediction_service import recalculate_prediction_round

router = APIRouter(prefix="/api/admin", tags=["administration"])
AdminRole = Literal["admin", "superadmin"]
ManagedRole = Literal["user", "admin"]
MetricSource = Literal["all", "site", "bot"]
MetricPeriod = Literal["7d", "30d", "90d", "all"]
UserSortField = Literal["created_at", "last_activity", "role"]
SortOrder = Literal["asc", "desc"]


class AdminContext(BaseModel):
    id: int
    role: AdminRole
    email: str | None = None
    telegram_id: int | None = None


class RoleUpdateRequest(BaseModel):
    role: ManagedRole


class EmailUpdateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class PredictionRecalculationRequest(BaseModel):
    season: int = Field(ge=1950, le=2100)
    round: int = Field(ge=1, le=40)
    race_positions: dict[str, int] | None = None
    pole_driver: str | None = Field(default=None, min_length=2, max_length=4)
    sprint_pole_driver: str | None = Field(default=None, min_length=2, max_length=4)
    sprint_winner_driver: str | None = Field(default=None, min_length=2, max_length=4)
    safety_car: bool | None = None
    first_retirement_driver: str | None = Field(default=None, min_length=2, max_length=4)
    fastest_lap_driver: str | None = Field(default=None, min_length=2, max_length=4)


async def require_admin_session(
    request: Request,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
    cookie_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> AdminContext:
    user: dict
    if x_telegram_init_data:
        telegram_id = await get_telegram_user_id(x_telegram_init_data)
        assert db.conn is not None
        async with db.write_lock:
            await db.conn.execute(
                "INSERT OR IGNORE INTO users(telegram_id) VALUES (?)",
                (int(telegram_id),),
            )
            await db.conn.execute(
                """
                UPDATE users
                SET role = CASE WHEN ? THEN 'superadmin' ELSE role END,
                    updated_at = ?
                WHERE telegram_id = ?
                """,
                (
                    is_primary_admin(None, int(telegram_id)),
                    utc_iso(),
                    int(telegram_id),
                ),
            )
            async with db.conn.execute(
                "SELECT * FROM users WHERE telegram_id = ? AND archived_at IS NULL",
                (int(telegram_id),),
            ) as cursor:
                row = await cursor.fetchone()
            await db.conn.commit()
        if not row:
            raise HTTPException(401, detail="Telegram account not found")
        user = dict(row)
        await record_user_activity(db, int(user["id"]), "site")
    else:
        session: WebSessionContext = await require_web_session(
            request=request,
            authorization=authorization,
            x_csrf_token=x_csrf_token,
            cookie_token=cookie_token,
        )
        user = session.user
    role = user.get("role")
    if role not in {"admin", "superadmin"}:
        raise HTTPException(
            403,
            detail={"code": "admin_required", "message": "Доступ разрешён только администраторам"},
        )
    return AdminContext(
        id=int(user["id"]),
        role=role,
        email=user.get("email"),
        telegram_id=user.get("telegram_id"),
    )


async def require_superadmin(
    admin: AdminContext = Depends(require_admin_session),
) -> AdminContext:
    if admin.role != "superadmin":
        raise HTTPException(
            403,
            detail={"code": "superadmin_required", "message": "Требуются права superadmin"},
        )
    return admin


async def _get_user(user_id: int):
    assert db.conn is not None
    async with db.conn.execute(
        "SELECT * FROM users WHERE id = ? AND archived_at IS NULL",
        (int(user_id),),
    ) as cursor:
        user = await cursor.fetchone()
    if not user:
        raise HTTPException(404, detail={"code": "user_not_found", "message": "Пользователь не найден"})
    return user


def _ensure_mutable_target(user) -> None:
    if user["role"] == "superadmin" or is_primary_admin(user["email"], user["telegram_id"]):
        raise HTTPException(
            403,
            detail={
                "code": "protected_superadmin",
                "message": "Главный администратор и superadmin защищены от изменения",
            },
        )


async def _audit(
    actor_user_id: int,
    action: str,
    target_user_id: int | None,
    details: dict,
) -> None:
    assert db.conn is not None
    await db.conn.execute(
        """
        INSERT INTO admin_audit_log(actor_user_id, target_user_id, action, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(actor_user_id),
            int(target_user_id) if target_user_id is not None else None,
            action,
            json.dumps(details, ensure_ascii=False, separators=(",", ":")),
            utc_iso(),
        ),
    )


def _public_web_url(request: Request) -> str:
    value = (
        os.getenv("PUBLIC_WEB_URL")
        or os.getenv("FRONTEND_URL")
        or os.getenv("MINI_APP_URL")
        or str(request.base_url)
    ).strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise HTTPException(503, detail="PUBLIC_WEB_URL is not configured")
    return value


@router.get("/me")
async def admin_me(admin: AdminContext = Depends(require_admin_session)):
    return admin.model_dump()


@router.get("/metrics")
async def admin_metrics(
    period: MetricPeriod = Query("30d"),
    source: MetricSource = Query("all"),
    _: AdminContext = Depends(require_admin_session),
):
    assert db.conn is not None
    now = datetime.now(timezone.utc)
    period_days = {"7d": 7, "30d": 30, "90d": 90}.get(period)
    if period_days is None:
        async with db.conn.execute(
            "SELECT MIN(occurred_at) AS started_at FROM user_activity_events"
        ) as cursor:
            row = await cursor.fetchone()
        try:
            start = datetime.fromisoformat(row["started_at"]) if row and row["started_at"] else now
        except ValueError:
            start = now
    else:
        start = now - timedelta(days=period_days - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    async def unique_since(hours: int, metric_source: str | None) -> int:
        clauses = ["datetime(occurred_at) >= datetime(?)"]
        params: list[object] = [(now - timedelta(hours=hours)).isoformat()]
        if metric_source:
            clauses.append("source = ?")
            params.append(metric_source)
        async with db.conn.execute(
            f"SELECT COUNT(DISTINCT user_id) AS total FROM user_activity_events WHERE {' AND '.join(clauses)}",
            params,
        ) as cursor:
            result = await cursor.fetchone()
        return int(result["total"] or 0)

    cards: dict[str, dict[str, int]] = {}
    for metric_source in ("site", "bot"):
        cards[metric_source] = {
            "dau": await unique_since(24, metric_source),
            "wau": await unique_since(24 * 7, metric_source),
            "mau": await unique_since(24 * 30, metric_source),
        }
    cards["all"] = {
        metric: int(cards["site"].get(metric) or 0) + int(cards["bot"].get(metric) or 0)
        for metric in ("dau", "wau", "mau")
    }

    clauses = ["datetime(occurred_at) >= datetime(?)"]
    params: list[object] = [start.isoformat()]
    if source != "all":
        clauses.append("source = ?")
        params.append(source)
    async with db.conn.execute(
        f"""
        SELECT date(occurred_at) AS day, source, COUNT(DISTINCT user_id) AS users
        FROM user_activity_events
        WHERE {' AND '.join(clauses)}
        GROUP BY date(occurred_at), source
        ORDER BY day ASC
        """,
        params,
    ) as cursor:
        rows = await cursor.fetchall()

    daily: dict[str, dict[str, int | str]] = {}
    for row in rows:
        point = daily.setdefault(row["day"], {"day": row["day"], "site": 0, "bot": 0})
        point[row["source"]] = int(row["users"])
    return {
        "period": period,
        "source": source,
        "cards": cards,
        "series": list(daily.values()),
        "started_at": start.date().isoformat(),
        "generated_at": now.isoformat(),
    }


@router.get("/users")
async def admin_users(
    search: str = Query("", max_length=120),
    role: Literal["all", "user", "admin", "superadmin"] = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=10, le=100),
    sort_by: UserSortField = Query("last_activity", alias="sortBy"),
    sort_order: SortOrder = Query("desc", alias="sortOrder"),
    _: AdminContext = Depends(require_admin_session),
):
    assert db.conn is not None
    clauses = ["u.archived_at IS NULL"]
    params: list[object] = []
    query = search.strip()
    if query:
        like = f"%{query}%"
        clauses.append(
            "(u.email LIKE ? OR CAST(u.telegram_id AS TEXT) LIKE ? "
            "OR u.display_name LIKE ? OR u.telegram_username LIKE ?)"
        )
        params.extend([like, like, like, like])
    if role != "all":
        clauses.append("u.role = ?")
        params.append(role)
    where = " AND ".join(clauses)
    async with db.conn.execute(
        f"SELECT COUNT(*) AS total FROM users u WHERE {where}",
        params,
    ) as cursor:
        count_row = await cursor.fetchone()
    total = int(count_row["total"])
    offset = (page - 1) * page_size
    sort_expressions = {
        "created_at": "datetime(u.created_at)",
        "last_activity": "datetime(COALESCE(MAX(a.occurred_at), u.created_at))",
        "role": "u.role COLLATE NOCASE",
    }
    order_expression = sort_expressions[sort_by]
    order_direction = "ASC" if sort_order == "asc" else "DESC"
    async with db.conn.execute(
        f"""
        SELECT
            u.id, u.email, u.telegram_id, u.telegram_username, u.display_name,
            u.created_at, u.role, u.email_verified,
            MAX(a.occurred_at) AS last_activity
        FROM users u
        LEFT JOIN user_activity_events a ON a.user_id = u.id
        WHERE {where}
        GROUP BY u.id
        ORDER BY {order_expression} {order_direction}, u.id {order_direction}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ) as cursor:
        users = [dict(row) for row in await cursor.fetchall()]
    for user in users:
        user["email_verified"] = bool(user["email_verified"])
        user["protected"] = user["role"] == "superadmin" or is_primary_admin(
            user["email"], user["telegram_id"]
        )
    return {
        "items": users,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, math.ceil(total / page_size)),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    data: RoleUpdateRequest,
    admin: AdminContext = Depends(require_superadmin),
):
    assert db.conn is not None
    async with db.write_lock:
        user = await _get_user(user_id)
        _ensure_mutable_target(user)
        old_role = user["role"]
        await db.conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (data.role, utc_iso(), int(user_id)),
        )
        await _audit(admin.id, "user.role_changed", user_id, {"from": old_role, "to": data.role})
        await db.conn.commit()
    return {"id": user_id, "role": data.role}


@router.patch("/users/{user_id}/email")
async def update_user_email(
    user_id: int,
    data: EmailUpdateRequest,
    admin: AdminContext = Depends(require_admin_session),
):
    assert db.conn is not None
    normalized = normalize_email(data.email)
    async with db.write_lock:
        user = await _get_user(user_id)
        _ensure_mutable_target(user)
        try:
            await db.conn.execute(
                """
                UPDATE users
                SET email = ?, email_verified = 1, updated_at = ?
                WHERE id = ?
                """,
                (normalized, utc_iso(), int(user_id)),
            )
            now = utc_iso()
            await db.conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, int(user_id)),
            )
            await db.conn.execute(
                """
                UPDATE password_reset_tokens SET consumed_at = ?
                WHERE user_id = ? AND consumed_at IS NULL
                """,
                (now, int(user_id)),
            )
            await _audit(
                admin.id,
                "user.email_changed",
                user_id,
                {"from": user["email"], "to": normalized},
            )
            await db.conn.commit()
        except aiosqlite.IntegrityError as exc:
            await db.conn.rollback()
            raise HTTPException(
                409,
                detail={"code": "email_conflict", "message": "Этот email уже используется"},
            ) from exc
    return {"id": user_id, "email": normalized, "email_verified": True}


@router.post("/users/{user_id}/unlink-telegram")
async def unlink_user_telegram(
    user_id: int,
    admin: AdminContext = Depends(require_admin_session),
):
    assert db.conn is not None
    async with db.write_lock:
        user = await _get_user(user_id)
        _ensure_mutable_target(user)
        telegram_id = user["telegram_id"]
        if telegram_id is None:
            return {"id": user_id, "telegram_id": None}
        now = utc_iso()
        await db.conn.execute(
            "UPDATE users SET telegram_id = NULL, telegram_username = NULL, updated_at = ? WHERE id = ?",
            (now, int(user_id)),
        )
        await db.conn.execute(
            "DELETE FROM telegram_login_codes WHERE telegram_id = ?",
            (int(telegram_id),),
        )
        await db.conn.execute(
            """
            UPDATE telegram_link_sessions
            SET telegram_id = NULL, status = 'cancelled', updated_at = ?
            WHERE telegram_id = ? AND status = 'pending'
            """,
            (now, int(telegram_id)),
        )
        await _audit(
            admin.id,
            "user.telegram_unlinked",
            user_id,
            {"telegram_id": int(telegram_id)},
        )
        await db.conn.commit()
    return {"id": user_id, "telegram_id": None}


@router.post("/users/{user_id}/password-reset")
async def send_user_password_reset(
    user_id: int,
    request: Request,
    admin: AdminContext = Depends(require_admin_session),
):
    user = await _get_user(user_id)
    _ensure_mutable_target(user)
    if not user["email"] or not user["password_hash"]:
        raise HTTPException(
            422,
            detail={"code": "email_account_required", "message": "У пользователя нет email-входа"},
        )
    try:
        await get_auth_service().request_password_reset(user["email"], _public_web_url(request))
    except EmailDeliveryError as exc:
        raise HTTPException(503, detail={"code": "email_delivery_failed", "message": str(exc)}) from exc
    except AuthError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": str(exc)}) from exc
    assert db.conn is not None
    async with db.write_lock:
        await _audit(admin.id, "user.password_reset_sent", user_id, {"email": user["email"]})
        await db.conn.commit()
    return {"message": "Письмо для сброса пароля отправлено"}


@router.post("/predictions/recalculate")
async def recalculate_predictions(
    data: PredictionRecalculationRequest,
    admin: AdminContext = Depends(require_superadmin),
):
    """Rebuild one round from fresh official classifications.

    Manual overrides are intentionally limited to facts that may be absent from
    the result feed. Every execution is revisioned in ``prediction_score_runs``.
    """
    schedule = await get_season_schedule_short_async(data.season) or []
    event = next(
        (item for item in schedule if int(item.get("round") or 0) == data.round),
        None,
    )
    if not event:
        raise HTTPException(
            404,
            detail={"code": "round_not_found", "message": "Этап не найден в календаре"},
        )
    if event.get("is_cancelled"):
        raise HTTPException(
            409,
            detail={"code": "round_cancelled", "message": "Отменённый этап нельзя рассчитать"},
        )

    extra_facts = {
        key: value
        for key, value in {
            "_race_positions": data.race_positions,
            "pole_driver": data.pole_driver,
            "sprint_pole_driver": data.sprint_pole_driver,
            "sprint_winner_driver": data.sprint_winner_driver,
            "safety_car": data.safety_car,
            "first_retirement_driver": data.first_retirement_driver,
            "fastest_lap_driver": data.fastest_lap_driver,
        }.items()
        if value is not None
    }
    try:
        result = await recalculate_prediction_round(
            data.season,
            data.round,
            str(event.get("event_name") or "Гран-при"),
            has_sprint=bool(
                event.get("sprint_start_utc")
                or event.get("sprint_quali_start_utc")
            ),
            extra_facts=extra_facts,
            actor_user_id=admin.id,
            calculation_source="admin",
        )
    except ValueError as exc:
        raise HTTPException(
            409,
            detail={"code": "official_results_unavailable", "message": str(exc)},
        ) from exc

    assert db.conn is not None
    async with db.write_lock:
        await _audit(
            admin.id,
            "predictions.round_recalculated",
            None,
            {
                "season": data.season,
                "round": data.round,
                "revision": result["revision"],
                "answers_hash": result["answers_hash"],
                "scored": result["scored"],
                "overrides": sorted(extra_facts),
            },
        )
        await db.conn.commit()
    return result


@router.get("/predictions/score-runs")
async def prediction_score_runs(
    season: int = Query(..., ge=1950, le=2100),
    round_num: int = Query(..., ge=1, le=40, alias="round"),
    _: AdminContext = Depends(require_admin_session),
):
    assert db.conn is not None
    async with db.conn.execute(
        """
        SELECT id, season, round, revision, source, actor_user_id, answers_hash,
               max_points, predictions_scored, created_at
        FROM prediction_score_runs
        WHERE season = ? AND round = ?
        ORDER BY revision DESC
        """,
        (season, round_num),
    ) as cursor:
        return {"items": [dict(row) for row in await cursor.fetchall()]}


@router.get("/audit-log")
async def get_audit_log(
    limit: int = Query(50, ge=1, le=200),
    _: AdminContext = Depends(require_admin_session),
):
    assert db.conn is not None
    async with db.conn.execute(
        """
        SELECT
            l.id, l.action, l.details_json, l.created_at, l.target_user_id,
            actor.email AS actor_email, actor.telegram_id AS actor_telegram_id
        FROM admin_audit_log l
        LEFT JOIN users actor ON actor.id = l.actor_user_id
        ORDER BY l.id DESC
        LIMIT ?
        """,
        (limit,),
    ) as cursor:
        rows = await cursor.fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json"))
        except json.JSONDecodeError:
            item["details"] = {}
        items.append(item)
    return {"items": items}
