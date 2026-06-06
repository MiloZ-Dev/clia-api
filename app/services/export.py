"""Export stored weather observations to daily CSV files."""

import os
from datetime import date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.weather import WeatherData

# Column order used for exported CSVs, matching the ORM model.
EXPORT_COLUMNS = [
    "id", "city", "region", "country", "latitude", "longitude", "timezone",
    "temperature", "humidity", "condition", "wind_speed", "wind_direction",
    "pressure", "precipitation", "cloud_cover", "feels_like", "dew_point",
    "visibility", "uv_index", "gust_speed", "recorded_at",
]


def export_csv(
    filename: str | None = None, target_date: date | None = None
) -> str | None:
    """Export a single day's weather records to a CSV file.

    Args:
        filename: Explicit output path. When omitted, a timestamped file is
            created inside the configured ``exports_dir``.
        target_date: Day to export. Defaults to the current day.

    Returns:
        The path of the written CSV, or ``None`` if there were no records for
        the requested day.
    """
    db: Session = SessionLocal()
    try:
        day = target_date or date.today()
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        records = (
            db.query(WeatherData)
            .filter(WeatherData.recorded_at >= start)
            .filter(WeatherData.recorded_at <= end)
            .all()
        )
    finally:
        db.close()

    if not records:
        print(f"⚠️  No weather records found for {day}; nothing to export.")
        return None

    os.makedirs(settings.exports_dir, exist_ok=True)

    rows = [
        {
            "id": r.id,
            "city": r.city,
            "region": r.region,
            "country": r.country,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "timezone": r.timezone,
            "temperature": r.temperature,
            "humidity": r.humidity,
            "condition": r.condition,
            "wind_speed": r.wind_speed,
            "wind_direction": r.wind_direction,
            "pressure": r.pressure,
            "precipitation": r.precipitation,
            "cloud_cover": r.cloud_cover,
            "feels_like": r.feels_like,
            "dew_point": r.dew_point,
            "visibility": r.visibility,
            "uv_index": r.uv_index,
            "gust_speed": r.gust_speed,
            "recorded_at": r.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for r in records
    ]

    df = pd.DataFrame(rows, columns=EXPORT_COLUMNS)

    if not filename:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(settings.exports_dir, f"weather_data_{stamp}.csv")

    df.to_csv(filename, index=False)
    print(f"📁 Exported CSV: {filename}")
    return filename
