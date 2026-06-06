"""AI-powered agricultural climate analysis via the Anthropic (Claude) API.

Combines a city's recent stored observations with a Prophet forecast and asks
Claude to act as an agricultural climate analyst, returning a structured JSON
assessment (trend, risk level, recommendations, forecast interpretation, etc.).

The Anthropic Messages API is called directly over HTTP with ``httpx`` rather
than through an SDK so the request stays a thin, explicit dependency alongside
the other async weather clients in this codebase.
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.weather import WeatherData
from app.services.prediction import predict_weather

# Anthropic Messages API endpoint and pinned wire version.
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_MAX_TOKENS = 1000

# Trailing window of stored observations handed to the model, in days.
ANALYSIS_HISTORY_DAYS = 7

# How many forecast days to request from the Prophet predictor.
FORECAST_DAYS = 5

# How long to wait on the Anthropic API before giving up, in seconds.
REQUEST_TIMEOUT = 60

# Weather-record fields serialized into the prompt context. Kept explicit (and
# tolerant of missing/None values) so newer enrichment columns flow through
# without breaking older records that predate them.
_RECORD_FIELDS = [
    "recorded_at", "temperature", "humidity", "condition", "wind_speed",
    "wind_direction", "pressure", "precipitation", "cloud_cover", "feels_like",
    "dew_point", "visibility", "uv_index", "gust_speed",
    "soil_temperature", "solar_radiation", "evapotranspiration", "wind_gusts_10m",
    "aqi", "co", "pm2_5", "pm10",
]


async def analyze_city(city: str, db: Session) -> dict:
    """Produce an AI agricultural climate analysis for ``city``.

    Pulls the last :data:`ANALYSIS_HISTORY_DAYS` days of observations and a
    Prophet forecast, asks Claude to interpret them as an agricultural climate
    analyst, and returns the parsed structured assessment.

    Args:
        city: City name to analyze (case-sensitive match).
        db: Active database session.

    Returns:
        The model's structured assessment, always annotated with
        ``generated_at`` (UTC ISO string) and ``data_points_analyzed`` (int).
        ``{"city": city, "error": "No data available"}`` if the city has no
        recent records. ``{"raw": ..., "parse_error": True, ...}`` if the model
        response could not be parsed as JSON.

    Raises:
        ValueError: If ``ANTHROPIC_API_KEY`` is not configured.
    """
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    records = _load_recent_records(db, city)
    if not records:
        return {"city": city, "error": "No data available"}

    recent = [_serialize_record(r) for r in records]
    forecast = predict_weather(city, days=FORECAST_DAYS, db=db)

    prompt = _build_prompt(city, recent, forecast)
    result = await _request_analysis(prompt)

    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["data_points_analyzed"] = len(records)
    return result


def _load_recent_records(db: Session, city: str) -> list[WeatherData]:
    """Return the city's observations from the last window, newest-first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ANALYSIS_HISTORY_DAYS)
    return (
        db.query(WeatherData)
        .filter(WeatherData.city == city)
        .filter(WeatherData.recorded_at >= cutoff)
        .order_by(WeatherData.recorded_at.desc())
        .all()
    )


def _serialize_record(record: WeatherData) -> dict:
    """Map a :class:`WeatherData` row to a JSON-serializable dict."""
    row: dict = {}
    for field in _RECORD_FIELDS:
        value = getattr(record, field, None)
        if isinstance(value, datetime):
            value = value.isoformat()
        row[field] = value
    return row


def _build_prompt(city: str, recent: list[dict], forecast: list[dict]) -> str:
    """Assemble the analyst instruction plus the JSON data context."""
    schema = {
        "city": "string",
        "summary": "2-3 sentences in Spanish about current conditions",
        "trend": "mejorando | estable | empeorando",
        "agricultural_risk": "bajo | medio | alto | crítico",
        "risk_factors": ["list of detected risk factors"],
        "recommendations": [
            "2-3 actionable recommendations for farmers in Spanish"
        ],
        "forecast_insight": (
            "plain-language interpretation of the Prophet forecast in Spanish"
        ),
        "alert": None,
        "confidence": "baja | media | alta",
        "data_sources": ["WeatherAPI", "Open-Meteo", "OpenWeatherMap"],
    }

    return (
        "You are an agricultural climate analyst. Analyze the recent weather "
        f"observations and the Prophet forecast for the city of {city} and "
        "assess the conditions and agricultural risk.\n\n"
        "Respond with ONLY valid JSON. No markdown, no code fences, no "
        "explanation outside the JSON. Use exactly this structure and these "
        "keys:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "Recent weather records (most recent first):\n"
        f"{json.dumps(recent, ensure_ascii=False)}\n\n"
        "Prophet forecast (next days):\n"
        f"{json.dumps(forecast, ensure_ascii=False)}"
    )


async def _request_analysis(prompt: str) -> dict:
    """Call the Anthropic API and parse the JSON assessment from the reply.

    Returns the parsed object on success, or ``{"raw": ..., "parse_error":
    True}`` when the model text is not valid JSON.
    """
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

    text = _extract_text(data)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"raw": text, "parse_error": True}


def _extract_text(data: dict) -> str:
    """Concatenate the text blocks from an Anthropic Messages API response."""
    blocks = data.get("content", [])
    return "".join(
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )
