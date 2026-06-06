"""Client for the WeatherAPI.com current-conditions endpoint."""

import httpx

from app.core.config import settings
from app.services.enrichment import enrich_weather_record

# How long to wait on the upstream API before giving up, in seconds.
REQUEST_TIMEOUT = 15


async def get_weather_city(city: str) -> dict | None:
    """Fetch current weather for ``city`` and map it to our storage shape.

    The base WeatherAPI.com reading is enriched in place with Open-Meteo and
    OpenWeatherMap data (soil/solar/air-quality fields) before returning.

    Args:
        city: Free-text city query understood by WeatherAPI.com.

    Returns:
        A dict whose keys match :class:`app.models.weather.WeatherData` columns,
        or ``None`` if the API responds with a non-200 status.

    Raises:
        ValueError: If no API key is configured.
        httpx.HTTPError: On network errors or timeouts.
    """
    if not settings.weather_api_key:
        raise ValueError("WEATHER_API_KEY is not configured")

    params = {
        "key": settings.weather_api_key,
        "q": city,
        "aqi": "no",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(settings.weather_api_base_url, params=params)

    if response.status_code != 200:
        return None

    data = response.json()
    location = data["location"]
    current = data["current"]

    record = {
        "city": location["name"],
        "region": location["region"],
        "country": location["country"],
        "latitude": location["lat"],
        "longitude": location["lon"],
        "timezone": location["tz_id"],
        "temperature": current["temp_c"],
        "humidity": current["humidity"],
        "condition": current["condition"]["text"],
        "wind_speed": current["wind_kph"],
        "wind_direction": current["wind_dir"],
        "pressure": current["pressure_mb"],
        "precipitation": current["precip_mm"],
        "cloud_cover": current["cloud"],
        "feels_like": current["feelslike_c"],
        "dew_point": current["dewpoint_c"],
        "visibility": current["vis_km"],
        "uv_index": current["uv"],
        "gust_speed": current["gust_kph"],
    }

    return await enrich_weather_record(record)
