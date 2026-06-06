"""Alert detection service.

Inspects a freshly collected weather observation and records an
:class:`app.models.alert.Alert` for every agricultural-risk threshold it
crosses. The thresholds are intentionally conservative; they flag genuinely
extreme conditions rather than routine variation.
"""

from sqlalchemy.orm import Session

from app.models.alert import Alert

# Each rule maps a weather field to (alert_type, threshold). An alert fires when
# the observed value is strictly greater than the threshold.
ALERT_RULES: list[tuple[str, str, float]] = [
    ("temperature", "high_temperature", 40.0),
    ("wind_speed", "high_wind", 80.0),
    ("uv_index", "high_uv", 10.0),
    ("precipitation", "high_precipitation", 50.0),
]


def check_and_store_alerts(db: Session, weather_data: dict) -> list[Alert]:
    """Create and stage alerts for any thresholds ``weather_data`` exceeds.

    The alerts are added to ``db`` but not committed; the caller owns the
    transaction so a city's observation and its alerts persist atomically.

    Args:
        db: Active database session.
        weather_data: A dict shaped like
            :class:`app.models.weather.WeatherData` columns (as returned by
            :func:`app.services.weather_api.get_weather_city`).

    Returns:
        The list of :class:`Alert` objects staged on the session (possibly empty).
    """
    city = weather_data.get("city")
    alerts: list[Alert] = []

    for field, alert_type, threshold in ALERT_RULES:
        value = weather_data.get(field)
        if value is None:
            continue
        if value > threshold:
            alert = Alert(
                city=city,
                alert_type=alert_type,
                value=float(value),
                threshold=threshold,
            )
            db.add(alert)
            alerts.append(alert)

    return alerts
