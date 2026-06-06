"""SQLAlchemy ORM model for stored weather observations."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.core.database import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    Used as the default for :attr:`WeatherData.recorded_at`. Prefer this over the
    deprecated ``datetime.utcnow`` so stored timestamps carry tzinfo.
    """
    return datetime.now(timezone.utc)


class WeatherData(Base):
    """A single weather observation for a city at a point in time."""

    __tablename__ = "weather_data"

    # Location
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    region = Column(String)
    country = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    timezone = Column(String)

    # Measurements
    temperature = Column(Float)
    humidity = Column(Integer)
    condition = Column(String)
    wind_speed = Column(Float)
    wind_direction = Column(String)
    pressure = Column(Float)
    precipitation = Column(Float)
    cloud_cover = Column(Integer)
    feels_like = Column(Float)
    dew_point = Column(Float)
    visibility = Column(Float)
    uv_index = Column(Integer)
    gust_speed = Column(Float)

    # Open-Meteo enrichment
    soil_temperature = Column(Float, nullable=True)
    solar_radiation = Column(Float, nullable=True)
    evapotranspiration = Column(Float, nullable=True)
    wind_gusts_10m = Column(Float, nullable=True)

    # OpenWeatherMap air quality
    aqi = Column(Integer, nullable=True)
    co = Column(Float, nullable=True)
    pm2_5 = Column(Float, nullable=True)
    pm10 = Column(Float, nullable=True)

    # Bookkeeping
    recorded_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
