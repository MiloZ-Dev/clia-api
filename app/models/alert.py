"""SQLAlchemy ORM model for weather threshold alerts.

An :class:`Alert` row is recorded whenever a freshly collected observation
crosses one of the agricultural-risk thresholds defined in
:mod:`app.services.alerts`.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.core.database import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    Used as the default for :attr:`Alert.recorded_at`, mirroring
    :class:`app.models.weather.WeatherData` so stored timestamps carry tzinfo.
    """
    return datetime.now(timezone.utc)


class Alert(Base):
    """A single threshold breach detected for a city at a point in time."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    alert_type = Column(String, index=True)
    value = Column(Float)
    threshold = Column(Float)
    recorded_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
