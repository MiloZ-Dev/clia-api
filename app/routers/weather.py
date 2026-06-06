"""Weather endpoints: live lookups, bulk collection, and CSV export.

Paths are declared explicitly (no router prefix) so the public contract matches
the original Skynow API: ``/weather/{city}``, ``/weather/fetch_all``, ``/export``.
"""

import os
from datetime import date as _date
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.cities import CITIES
from app.core.database import get_db
from app.core.scheduler import fetch_and_store_weather
from app.models.weather import WeatherData
from app.schemas.weather import WeatherResponse
from app.services.export import export_csv
from app.services.weather_api import get_weather_city

router = APIRouter(tags=["weather"])

# Numeric fields aggregated by the ``/stats`` endpoint.
_STATS_FIELDS = ["temperature", "humidity", "wind_speed", "pressure", "uv_index"]


@router.get("/weather/latest/{city}")
def get_latest_weather(city: str, db: Session = Depends(get_db)):
    """Return the most recently stored weather record for a city from DB.
    Returns 404 if no record exists yet."""
    record = (
        db.query(WeatherData)
        .filter(WeatherData.city == city)
        .order_by(WeatherData.recorded_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"No data for {city}")
    return record


@router.get("/weather/{city}", response_model=WeatherResponse)
async def get_weather(city: str, db: Session = Depends(get_db)) -> WeatherData:
    """Fetch live weather for ``city``, store it, and return the saved record."""
    weather_data = await get_weather_city(city)
    if not weather_data:
        raise HTTPException(status_code=404, detail="City not found")

    entry = WeatherData(**weather_data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/weather/fetch_all")
def fetch_all_weather() -> dict:
    """Manually trigger a full collection run across all configured cities."""
    try:
        fetch_and_store_weather()
        return {"message": "✅ Manual collection completed"}
    except Exception as exc:  # noqa: BLE001 - surface as a 500 to the client
        raise HTTPException(status_code=500, detail=f"❌ Error: {exc}") from exc


@router.get("/export")
def export_weather_data(
    date: str | None = Query(
        default=None,
        description="Day to export as YYYY-MM-DD. Defaults to today.",
    ),
) -> FileResponse:
    """Export a day's records to CSV and return the file.

    Args:
        date: Optional ``YYYY-MM-DD`` day to export. When omitted, the current
            day is exported.
    """
    target_date: _date | None = None
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid date; expected YYYY-MM-DD"
            ) from exc

    filename = export_csv(target_date=target_date)
    if not filename:
        raise HTTPException(status_code=404, detail="No data to export")

    return FileResponse(
        path=filename,
        filename=os.path.basename(filename),
        media_type="text/csv",
    )


@router.get("/weather/history/{city}", response_model=list[WeatherResponse])
def get_weather_history(
    city: str,
    start: str | None = Query(
        default=None, description="Range start as YYYY-MM-DD (inclusive)."
    ),
    end: str | None = Query(
        default=None, description="Range end as YYYY-MM-DD (inclusive)."
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[WeatherData]:
    """Return stored records for ``city`` within an optional date range.

    Args:
        city: City name to match (case-sensitive).
        start: Inclusive range start, ``YYYY-MM-DD``. Open-ended if omitted.
        end: Inclusive range end, ``YYYY-MM-DD``. Open-ended if omitted.
        limit: Maximum number of records to return (default 100).
        offset: Number of records to skip for pagination (default 0).
        db: Database session dependency.

    Returns:
        Matching :class:`WeatherData` records ordered newest-first.
    """
    query = db.query(WeatherData).filter(WeatherData.city == city)

    if start:
        start_dt = _parse_day(start, datetime.min.time())
        query = query.filter(WeatherData.recorded_at >= start_dt)
    if end:
        end_dt = _parse_day(end, datetime.max.time())
        query = query.filter(WeatherData.recorded_at <= end_dt)

    return (
        query.order_by(WeatherData.recorded_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/cities", tags=["weather"])
def list_cities() -> list[str]:
    """Return the full list of monitored city names."""
    return CITIES


# Declared before ``/stats/{city}`` so FastAPI matches the literal "total"
# segment here rather than treating it as a ``city`` path parameter.
@router.get("/stats/total", tags=["weather"])
def get_total_records(db: Session = Depends(get_db)) -> dict:
    """Return the total count of all weather records in the database."""
    total = db.query(func.count(WeatherData.id)).scalar()
    return {"total": int(total or 0)}


@router.get("/stats/{city}")
def get_weather_stats(
    city: str,
    days: int = Query(default=7, ge=1),
    db: Session = Depends(get_db),
) -> dict:
    """Return avg/max/min aggregates for ``city`` over the last ``days`` days.

    Aggregation is performed in the database via SQLAlchemy ``func`` rather than
    pulling rows into pandas.

    Args:
        city: City name to match (case-sensitive).
        days: Size of the trailing window in days (default 7).
        db: Database session dependency.

    Returns:
        A dict with the city, window size, sample count, and per-field
        ``avg``/``max``/``min`` values. Aggregates are ``None`` when no records
        fall in the window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    columns = [func.count(WeatherData.id)]
    for field in _STATS_FIELDS:
        column = getattr(WeatherData, field)
        columns.extend([func.avg(column), func.max(column), func.min(column)])

    row = (
        db.query(*columns)
        .filter(WeatherData.city == city)
        .filter(WeatherData.recorded_at >= cutoff)
        .one()
    )

    count = row[0]
    stats: dict[str, dict[str, float | None]] = {}
    for index, field in enumerate(_STATS_FIELDS):
        avg, mx, mn = row[1 + index * 3 : 4 + index * 3]
        stats[field] = {
            "avg": float(avg) if avg is not None else None,
            "max": float(mx) if mx is not None else None,
            "min": float(mn) if mn is not None else None,
        }

    return {"city": city, "days": days, "count": int(count), "stats": stats}


def _parse_day(value: str, time_of_day: time) -> datetime:
    """Parse a ``YYYY-MM-DD`` string into a datetime at ``time_of_day``.

    Raises:
        HTTPException: 400 if ``value`` is not a valid ``YYYY-MM-DD`` date.
    """
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid date; expected YYYY-MM-DD"
        ) from exc
    return datetime.combine(day, time_of_day)
