"""Experimental analytics: authorization is enforced on every endpoint."""
import asyncio
import json
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.api.admin_api import AdminContext, require_admin_session
from app.db import db
from app.f1_data import get_season_schedule_short_async

router = APIRouter(prefix="/api/admin/prediction-analytics", tags=["prediction analytics"],
                   dependencies=[Depends(require_admin_session)])


class GenerateRequest(BaseModel):
    season: int = Field(ge=2018, le=2100)
    round: int = Field(ge=1, le=30)
    session: Literal["race", "qualifying"]


@router.get("")
async def index(response: Response, season: int = Query(ge=2018, le=2100)):
    response.headers["Cache-Control"] = "no-store"
    try:
        events = await asyncio.wait_for(get_season_schedule_short_async(season), 10)
        warning = None
    except Exception:
        events, warning = [], "Расписание временно недоступно. Сохранённые прогнозы доступны ниже"
    rows = await (await db.conn.execute("SELECT id,season,round,session,created_at,status,error,settled_at FROM prediction_analytics WHERE season=? ORDER BY created_at DESC LIMIT 100", (season,))).fetchall()
    return {"events": events, "snapshots": [dict(r) for r in rows], "warning": warning}


@router.get("/{forecast_id}")
async def detail(forecast_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    row = await (await db.conn.execute("SELECT * FROM prediction_analytics WHERE id=?", (forecast_id,))).fetchone()
    if not row:
        raise HTTPException(404, "Прогноз не найден")
    result = dict(row)
    result.pop("lease_token", None)
    result.pop("snapshot", None)
    for key in ("payload", "actual"):
        result[key] = json.loads(result[key]) if result[key] else None
    return result


@router.post("", status_code=202)
async def generate(body: GenerateRequest,
                   admin: AdminContext = Depends(require_admin_session)):
    now = time.time()
    async with db.write_lock:
        # Shared SQLite check serializes generation requests even across web workers.
        await db.conn.execute("BEGIN IMMEDIATE")
        try:
            existing = await (await db.conn.execute("SELECT id FROM prediction_analytics WHERE (status='pending' OR (created_at>? AND status='ready')) AND season=? AND round=? AND session=? LIMIT 1", (now - 300, body.season, body.round, body.session))).fetchone()
            if existing:
                await db.conn.rollback()
                return {"id": existing["id"]}
            job_id = uuid.uuid4().hex
            await db.conn.execute("INSERT INTO prediction_analytics(id,season,round,session,created_at,created_by) VALUES(?,?,?,?,?,?)", (job_id, body.season, body.round, body.session, now, admin.id))
            await db.conn.commit()
        except Exception:
            await db.conn.rollback()
            raise
    return {"id": job_id}
