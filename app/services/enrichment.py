"""Weather enrichment clients: Open-Meteo and OpenWeatherMap.

Augments a base WeatherAPI.com reading with agronomy-relevant fields
(soil temperature, solar radiation, evapotranspiration, wind gusts) from
Open-Meteo and air-quality fields (AQI plus pollutant concentrations) from
OpenWeatherMap. Both clients fail soft: any error returns ``{}`` so enrichment
never blocks the primary collection path.
"""

import asyncio

import httpx

from app.core.config import settings

# Upstream endpoints.
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPENWEATHERMAP_URL = "http://api.openweathermap.org/data/2.5/air_pollution"

# How long to wait on either enrichment API before giving up, in seconds.
REQUEST_TIMEOUT = 15

# Open-Meteo ``current`` variables requested, mapped to our column names.
_OPEN_METEO_FIELDS = {
    "soil_temperature_0cm": "soil_temperature",
    "shortwave_radiation": "solar_radiation",
    "et0_fao_evapotranspiration": "evapotranspiration",
    "wind_gusts_10m": "wind_gusts_10m",
}


async def enrich_open_meteo(lat: float, lon: float) -> dict:
    """Fetch Open-Meteo current conditions for a coordinate.

    No API key is required. Returns ``{}`` on any error.

    Returns:
        A dict with any of ``soil_temperature``, ``solar_radiation``,
        ``evapotranspiration``, ``wind_gusts_10m`` that the API provided.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(_OPEN_METEO_FIELDS),
        "wind_speed_unit": "kmh",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            current = response.json().get("current", {})
    except (httpx.HTTPError, ValueError):
        return {}

    return {
        column: current[source]
        for source, column in _OPEN_METEO_FIELDS.items()
        if current.get(source) is not None
    }


async def enrich_openweathermap(lat: float, lon: float) -> dict:
    """Fetch OpenWeatherMap air-quality data for a coordinate.

    Returns ``{}`` silently if no API key is configured or on any error.

    Returns:
        A dict with any of ``aqi``, ``co``, ``pm2_5``, ``pm10`` that the API
        provided.
    """
    if not settings.openweathermap_api_key:
        return {}

    params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.openweathermap_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(OPENWEATHERMAP_URL, params=params)
            response.raise_for_status()
            entry = response.json()["list"][0]
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return {}

    main = entry.get("main", {})
    components = entry.get("components", {})
    result: dict = {}
    if main.get("aqi") is not None:
        result["aqi"] = main["aqi"]
    for field in ("co", "pm2_5", "pm10"):
        if components.get(field) is not None:
            result[field] = components[field]
    return result


async def enrich_weather_record(record: dict) -> dict:
    """Merge Open-Meteo and OpenWeatherMap data into ``record`` in place.

    Both upstream calls run concurrently. Cities without usable coordinates are
    returned unchanged.

    Args:
        record: A weather dict carrying ``latitude`` / ``longitude``.

    Returns:
        The same ``record`` with any enrichment fields merged in.
    """
    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat is None or lon is None:
        return record

    meteo, owm = await asyncio.gather(
        enrich_open_meteo(lat, lon),
        enrich_openweathermap(lat, lon),
    )
    record.update(meteo)
    record.update(owm)
    return record
