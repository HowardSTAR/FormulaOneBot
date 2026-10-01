from datetime import datetime, timezone
import re

from fastapi import APIRouter, HTTPException, Query, Response
from typing import Literal
from app.services.driver_guides import get_driver_guide
from app.services.race_recap import get_race_recap_with_news as get_race_recap
from app.services.standings_history import get_standings_history

router = APIRouter(prefix="/api", tags=["F1 insights"])


@router.get("/standings-history")
async def standings_history(kind: Literal["drivers", "constructors"], ids: str,
                            start_year: int = Query(ge=1950), end_year: int = Query(ge=1950)):
    identifiers = list(dict.fromkeys(ids.split(",")))
    minimum = 1950 if kind == "drivers" else 1958
    if (not 1 <= len(identifiers) <= 3 or any(not re.fullmatch(r"[a-z0-9_-]{1,60}", identifier) for identifier in identifiers)
            or not minimum <= start_year <= end_year <= datetime.now(timezone.utc).year
            or end_year - start_year > 9):
        raise HTTPException(422, "Выберите до трёх участников и диапазон до 10 сезонов. Личный зачёт — с 1950, Кубок конструкторов — с 1958.")
    return await get_standings_history(kind, identifiers, start_year, end_year)


@router.get("/driver-guide")
async def driver_guide(driverId: str = Query(pattern=r"^[a-z0-9_-]{1,60}$")):
    return {"guide": get_driver_guide(driverId)}


@router.get("/race-recap")
async def race_recap(response: Response, season: int = Query(ge=1950), round_num: int = Query(ge=1, le=30)):
    if season > datetime.now(timezone.utc).year:
        raise HTTPException(422, "Сезон ещё не начался")
    response.headers["Cache-Control"] = "no-store"
    return await get_race_recap(season, round_num)
