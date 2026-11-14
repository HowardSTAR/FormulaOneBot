"""Versioned, presentation-independent weekend contract for native and web clients."""
import asyncio
from datetime import date as Date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, Field

from app.f1_data import get_season_schedule_short_async, get_weekend_schedule
from app.services.race_schedule import build_next_race_payload, parse_utc_iso

router = APIRouter(prefix="/api/v1", tags=["weekend v1"])

SessionCode = Literal[
    "practice_1", "practice_2", "practice_3", "qualifying", "sprint",
    "sprint_qualifying", "race", "unknown",
]
SESSION_CODES = {
    "Practice 1": "practice_1", "Practice 2": "practice_2", "Practice 3": "practice_3",
    "Qualifying": "qualifying", "Sprint": "sprint", "Sprint Qualifying": "sprint_qualifying",
    "Sprint Shootout": "sprint_qualifying", "Race": "race",
}


class WeekendSession(BaseModel):
    code: SessionCode
    source_name: str = Field(description="Provider name; never use this as an identifier or localized label.")
    starts_at: AwareDatetime | None


class WeekendEvent(BaseModel):
    id: str = Field(description="Stable event key: season:round, for example 2026:1.")
    round: int
    name: str
    country: str | None
    location: str | None
    date: Date | None = Field(description="Published race day; does not imply a known start time.")
    starts_at: AwareDatetime | None
    is_cancelled: bool


class WeekendResponse(BaseModel):
    status: Literal["ok", "no_schedule", "season_finished"]
    season: int
    event: WeekendEvent | None
    sessions: list[WeekendSession]
    schedule_status: Literal["available", "unavailable", "cancelled", "not_applicable"]


def _utc(value: str | None) -> datetime | None:
    parsed = parse_utc_iso(value)
    return parsed.astimezone(timezone.utc) if parsed else None


@router.get("/weekend", response_model=WeekendResponse, operation_id="getWeekend",
            responses={404: {"description": "Requested event is absent from the season schedule."}})
async def get_weekend(
    season: int = Query(..., ge=1950, le=2100),
    round_number: int | None = Query(None, alias="round", ge=1, le=100),
):
    """Public weekend. Omit round to apply the shared next-race selection rules.

    Empty sessions mean unavailable data, never proof that a session was cancelled.
    Dates are UTC instants; clients format and localize them themselves.
    """
    if round_number is None:
        race = await build_next_race_payload(season)
        if race["status"] != "ok":
            return WeekendResponse(status=race["status"], season=season, event=None,
                                   sessions=[], schedule_status="not_applicable")
    else:
        schedule = await get_season_schedule_short_async(season)
        if not schedule:
            return WeekendResponse(status="no_schedule", season=season, event=None,
                                   sessions=[], schedule_status="not_applicable")
        race = next((item for item in schedule if item.get("round") == round_number), None)
        if race is None:
            raise HTTPException(404, detail={"code": "weekend_not_found", "message": "Этап не найден"})

    cancelled = bool(race.get("is_cancelled", False))
    raw_sessions = [] if cancelled else await asyncio.to_thread(get_weekend_schedule, season, race["round"])
    sessions = [WeekendSession(
        code=SESSION_CODES.get(item.get("name"), "unknown"),
        source_name=item.get("name") or "Session",
        starts_at=_utc(item.get("utc_iso")),
    ) for item in (raw_sessions or [])]
    return WeekendResponse(
        status="ok", season=season,
        event=WeekendEvent(
            id=f"{season}:{race['round']}", round=race["round"],
            name=race.get("event_name") or f"Round {race['round']}",
            country=race.get("country"), location=race.get("location"),
            date=race.get("date") or None, starts_at=_utc(race.get("race_start_utc")),
            is_cancelled=cancelled,
        ),
        sessions=sessions,
        schedule_status="cancelled" if cancelled else "available" if sessions else "unavailable",
    )
