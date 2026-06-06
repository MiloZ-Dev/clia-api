"""Pydantic schemas for serializing weather data over the API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WeatherBase(BaseModel):
    """Shared weather fields, independent of persistence concerns."""

    city: str
    region: str
    country: str
    latitude: float
    longitude: float
    timezone: str

    temperature: float
    humidity: int
    condition: str
    wind_speed: float
    wind_direction: str
    pressure: float
    precipitation: float
    cloud_cover: int
    feels_like: float
    dew_point: float
    visibility: float
    uv_index: int
    gust_speed: float


class WeatherResponse(WeatherBase):
    """Weather record as returned by the API, including persisted metadata."""

    id: int
    recorded_at: datetime

    # Allow construction directly from ORM objects (Pydantic v2 style).
    model_config = ConfigDict(from_attributes=True)
