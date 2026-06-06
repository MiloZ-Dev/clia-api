"""Background scheduler: periodic weather collection and daily CSV export.

Run as a standalone process: ``python -m app.core.scheduler``.

The job functions are importable on their own (e.g. the API exposes a manual
trigger), so the recurring schedule is registered only inside
:func:`run_scheduler` rather than at import time.
"""

import asyncio
import time
import traceback
from datetime import date, datetime, timezone

import pandas as pd
import schedule
from sqlalchemy.orm import Session

from app.config.cities import ALL_CITIES
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.scheduler_config import SchedulerConfig
from app.models.weather import WeatherData
from app.services.alerts import check_and_store_alerts
from app.services.cleaning import split_csv_by_city
from app.services.export import export_csv
from app.services.weather_api import get_weather_city

# Columns extracted from each stored record when handing the day's data to the
# in-memory cleaning step. ``city`` is required by :func:`split_csv_by_city`.
_CLEAN_COLUMNS = [
    "id", "city", "region", "country", "latitude", "longitude", "timezone",
    "temperature", "humidity", "condition", "wind_speed", "wind_direction",
    "pressure", "precipitation", "cloud_cover", "feels_like", "dew_point",
    "visibility", "uv_index", "gust_speed", "recorded_at",
]


async def _fetch_all_cities(db) -> None:
    """Fetch weather for all cities concurrently and persist results."""
    async def fetch_one(city: str):
        try:
            weather_data = await get_weather_city(city)
            if weather_data:
                return weather_data
            else:
                print(f"[{datetime.now()}] ⚠️  No data for: {city}")
                return None
        except Exception as exc:
            print(f"[{datetime.now()}] ⚠️  Failed {city}: {exc}")
            return None

    results = await asyncio.gather(*[fetch_one(city) for city in ALL_CITIES])

    saved = 0
    for weather_data in results:
        if weather_data:
            db.add(WeatherData(**weather_data))
            check_and_store_alerts(db, weather_data)
            saved += 1

    db.commit()
    print(f"[{datetime.now()}] 💾 {saved}/{len(ALL_CITIES)} records saved.")


def fetch_and_store_weather() -> None:
    """Fetch current weather for every configured city and persist it."""
    print(f"[{datetime.now()}] ⏳ Starting weather collection...")
    db = SessionLocal()
    try:
        asyncio.run(_fetch_all_cities(db))
        _clean_todays_records(db)
        _update_run_stats("success")
    except Exception as exc:
        db.rollback()
        print(f"[{datetime.now()}] ❌ Error: {exc}")
        traceback.print_exc()
        _update_run_stats("error")
    finally:
        db.close()
        print(f"[{datetime.now()}] 🔒 Session closed.\n")


def _clean_todays_records(db: Session) -> None:
    """Split the current day's stored records into per-city files, in memory.

    Queries today's :class:`WeatherData` rows, builds a DataFrame directly from
    them, and passes it to :func:`split_csv_by_city` — avoiding the round-trip
    through a combined CSV on disk.

    Args:
        db: Active database session to query today's records from.
    """
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    records = (
        db.query(WeatherData)
        .filter(WeatherData.recorded_at >= start)
        .filter(WeatherData.recorded_at <= end)
        .all()
    )

    if not records:
        print(f"[{datetime.now()}] ⚠️  No records for today; skipping cleaning.")
        return

    rows = [{col: getattr(r, col) for col in _CLEAN_COLUMNS} for r in records]
    df = pd.DataFrame(rows, columns=_CLEAN_COLUMNS)

    result = split_csv_by_city(df)
    print(
        f"[{datetime.now()}] 🧹 Cleaning completed: "
        f"{result['total_cities']} cities from {len(records)} records."
    )


def export_daily_csv() -> None:
    """Export the day's accumulated records to a CSV backup file."""
    try:
        filename = export_csv()
        if filename:
            print(f"[{datetime.now()}] 📊 CSV export completed: {filename}")
    except Exception as exc:  # noqa: BLE001 - log and keep the scheduler alive
        print(f"[{datetime.now()}] ❌ Error exporting CSV: {exc}")
        traceback.print_exc()


def _get_db_config() -> dict:
    """Read scheduler config from DB. Returns defaults if table is missing or empty."""
    db = SessionLocal()
    try:
        config = db.query(SchedulerConfig).filter(SchedulerConfig.id == 1).first()
        if not config:
            return {
                "fetch_interval_minutes": settings.fetch_interval_minutes,
                "is_enabled": True,
            }
        return {
            "fetch_interval_minutes": config.fetch_interval_minutes,
            "is_enabled": config.is_enabled,
        }
    except Exception:
        # Table doesn't exist yet (API hasn't run create_all) — use env defaults
        return {
            "fetch_interval_minutes": settings.fetch_interval_minutes,
            "is_enabled": True,
        }
    finally:
        db.close()


def _update_run_stats(status: str, next_run_at=None) -> None:
    """Write last_run_at, last_run_status, and next_run_at back to DB."""
    db = SessionLocal()
    try:
        config = db.query(SchedulerConfig).filter(SchedulerConfig.id == 1).first()
        if config:
            config.last_run_at = datetime.now(timezone.utc)
            config.last_run_status = status
            if next_run_at:
                config.next_run_at = next_run_at
            db.commit()
    finally:
        db.close()


def run_scheduler() -> None:
    print(f"[{datetime.now()}] 🔄 Scheduler started 🍄\n")
    current_interval = None

    while True:
        db_config = _get_db_config()

        # Skip collection if scheduler is disabled via DB flag
        if not db_config["is_enabled"]:
            print(f"[{datetime.now()}] ⏸ Scheduler is disabled. Sleeping 60s.")
            time.sleep(60)
            continue

        interval = db_config["fetch_interval_minutes"]

        # Re-register jobs only when the interval changes
        if interval != current_interval:
            schedule.clear()
            schedule.every(interval).minutes.do(fetch_and_store_weather)
            schedule.every().day.at(settings.csv_export_time).do(export_daily_csv)
            current_interval = interval
            print(f"[{datetime.now()}] ⚙️  Interval set to {interval} min.")

        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
