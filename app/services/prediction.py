"""Climate prediction service.

Forecasts the next N days of weather for a city from its recent history in
PostgreSQL. When enough history is available the per-field forecast is produced
with Facebook Prophet; otherwise it falls back to a simple rolling average so
the endpoint still returns useful numbers for sparsely-sampled cities.
"""

from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.weather import WeatherData

# Fields we forecast. Keys are both the ORM column names and the output keys.
PREDICTED_FIELDS = ["temperature", "humidity", "wind_speed", "precipitation"]

# Trailing window of history pulled from the database, in days.
HISTORY_DAYS = 30

# Minimum distinct daily samples required to use Prophet; below this we fall
# back to a rolling average.
PROPHET_MIN_DAYS = 14

# Window size (in days) for the rolling-average fallback.
ROLLING_WINDOW_DAYS = 7


def predict_weather(city: str, days: int = 5, db: Session | None = None) -> list[dict]:
    """Predict the next ``days`` days of weather for ``city``.

    Pulls the last :data:`HISTORY_DAYS` days of records for the city, aggregates
    them to one value per day per field, and forecasts forward. Prophet is used
    when at least :data:`PROPHET_MIN_DAYS` daily samples exist; otherwise a
    rolling average over the most recent days is projected flat.

    Args:
        city: City name to forecast (case-sensitive match).
        days: Number of future days to predict (default 5).
        db: Optional database session. When omitted a short-lived session is
            opened and closed internally.

    Returns:
        A list of ``days`` dicts, each shaped
        ``{"date": "YYYY-MM-DD", "temperature": ..., "humidity": ...,
        "wind_speed": ..., "precipitation": ...}``. Empty if the city has no
        history.
    """
    owns_session = db is None
    db = db or SessionLocal()
    try:
        daily = _load_daily_history(db, city)
    finally:
        if owns_session:
            db.close()

    if daily.empty:
        return []

    future_dates = _future_dates(daily["ds"].max(), days)

    use_prophet = len(daily) >= PROPHET_MIN_DAYS
    forecasts: dict[str, list[float]] = {}
    for field in PREDICTED_FIELDS:
        if use_prophet:
            forecasts[field] = _forecast_prophet(daily, field, days)
        else:
            forecasts[field] = _forecast_rolling(daily, field, days)

    return [
        {
            "date": future_dates[i].strftime("%Y-%m-%d"),
            **{field: forecasts[field][i] for field in PREDICTED_FIELDS},
        }
        for i in range(days)
    ]


def _load_daily_history(db: Session, city: str) -> pd.DataFrame:
    """Load and daily-aggregate the city's recent history.

    Returns a DataFrame with a ``ds`` (datetime) column plus one column per
    predicted field, averaged per calendar day and sorted ascending. Empty if
    the city has no records in the window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
    records = (
        db.query(WeatherData)
        .filter(WeatherData.city == city)
        .filter(WeatherData.recorded_at >= cutoff)
        .order_by(WeatherData.recorded_at.asc())
        .all()
    )

    if not records:
        return pd.DataFrame()

    rows = [
        {
            "ds": r.recorded_at,
            **{field: getattr(r, field) for field in PREDICTED_FIELDS},
        }
        for r in records
    ]
    df = pd.DataFrame(rows)

    # Collapse multiple intra-day observations into one mean value per day so the
    # forecasters see an evenly-spaced daily series.
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None).dt.normalize()
    daily = df.groupby("ds", as_index=False)[PREDICTED_FIELDS].mean()
    return daily.sort_values("ds").reset_index(drop=True)


def _future_dates(last: pd.Timestamp, days: int) -> list[date]:
    """Return the ``days`` calendar days following ``last``."""
    base = last.date()
    return [base + timedelta(days=i + 1) for i in range(days)]


def _forecast_prophet(daily: pd.DataFrame, field: str, days: int) -> list[float]:
    """Forecast ``field`` ``days`` steps ahead with Prophet.

    Imported lazily so the dependency is only required when actually used.
    """
    from prophet import Prophet

    series = daily[["ds", field]].rename(columns={field: "y"}).dropna()
    if len(series) < PROPHET_MIN_DAYS:
        return _forecast_rolling(daily, field, days)

    model = Prophet(daily_seasonality=False, weekly_seasonality=True)
    model.fit(series)

    future = model.make_future_dataframe(periods=days)
    forecast = model.predict(future)
    predicted = forecast["yhat"].tail(days).tolist()
    return [round(float(value), 2) for value in predicted]


def _forecast_rolling(daily: pd.DataFrame, field: str, days: int) -> list[float]:
    """Project a flat forecast from the recent rolling average of ``field``."""
    recent = daily[field].dropna().tail(ROLLING_WINDOW_DAYS)
    average = float(recent.mean()) if not recent.empty else 0.0
    average = round(average, 2)
    return [average for _ in range(days)]
