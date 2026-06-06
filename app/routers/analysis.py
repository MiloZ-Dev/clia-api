"""AI analysis endpoints: per-city, batch, and regional risk scanning.

Wraps :func:`app.services.analysis.analyze_city`, which asks Claude to interpret
a city's recent observations and Prophet forecast as an agricultural climate
analyst. Mounted with explicit ``/analyze/*`` paths.
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.analysis import analyze_city

router = APIRouter(tags=["analysis"])

# Cap on how many cities a single batch request may analyze.
MAX_BATCH_CITIES = 10

# Risk levels considered noteworthy for the regional alert scan.
ALERTING_RISK_LEVELS = {"medio", "alto", "crítico"}

# Cities scanned per region by the regional alert endpoint.
REGION_CITIES: dict[str, list[str]] = {
    "latam": [
        "Bogota", "Cali", "Medellin", "Lima", "Candelaria",
        "Barranquilla", "Cartagena",
    ],
    "europe": ["London", "Madrid", "Paris", "Berlin", "Rome"],
    "asia": ["Tokyo", "Bangkok", "Mumbai", "Dubai", "Beijing"],
    "africa": ["Cairo", "Lagos", "Nairobi", "Johannesburg", "Casablanca"],
}


@router.post("/analyze/batch")
async def analyze_batch(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    """Analyze up to :data:`MAX_BATCH_CITIES` cities sequentially.

    Args:
        payload: JSON body shaped ``{"cities": ["Bogota", "Cali", ...]}``.
        db: Database session dependency.

    Returns:
        ``{"total": n, "results": [...]}`` where each result is the analysis
        for one city.

    Raises:
        HTTPException: 400 if ``cities`` is missing/invalid or exceeds the cap;
            503 if the Anthropic API key is not configured.
    """
    cities = payload.get("cities")
    if not isinstance(cities, list) or not cities:
        raise HTTPException(
            status_code=400, detail="Body must include a non-empty 'cities' list"
        )
    if len(cities) > MAX_BATCH_CITIES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_BATCH_CITIES} cities may be analyzed per batch",
        )

    results = []
    for city in cities:
        try:
            results.append(await analyze_city(city, db))
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - record per-city failure, keep going
            results.append({"city": city, "error": str(exc)})

    return {"total": len(results), "results": results}


@router.get("/analyze/alerts/regional")
async def regional_alerts(
    region: str = Query(default="latam", description="Region key to scan."),
    db: Session = Depends(get_db),
) -> dict:
    """Scan a region's cities and return only those with notable risk.

    A city is included when its ``agricultural_risk`` is one of
    :data:`ALERTING_RISK_LEVELS` or it carries a non-null ``alert``.

    Args:
        region: One of ``latam``, ``europe``, ``asia``, ``africa``.
        db: Database session dependency.

    Returns:
        ``{"region": ..., "scanned": n, "alerts": [...]}``.

    Raises:
        HTTPException: 400 for an unknown region; 503 if the Anthropic API key
            is not configured.
    """
    cities = REGION_CITIES.get(region)
    if cities is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown region '{region}'. Valid: {sorted(REGION_CITIES)}",
        )

    alerts = []
    for city in cities:
        try:
            analysis = await analyze_city(city, db)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:  # noqa: BLE001 - skip cities that fail to analyze
            continue

        risk = analysis.get("agricultural_risk")
        if risk in ALERTING_RISK_LEVELS or analysis.get("alert") is not None:
            alerts.append(analysis)

    return {"region": region, "scanned": len(cities), "alerts": alerts}


@router.get("/analyze/{city}")
async def analyze_one(city: str, db: Session = Depends(get_db)) -> dict:
    """Return the AI agricultural climate analysis for a single city.

    Args:
        city: City name to analyze (case-sensitive match).
        db: Database session dependency.

    Raises:
        HTTPException: 503 if the Anthropic API key is not configured; 500 on
            any other failure.
    """
    try:
        return await analyze_city(city, db)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface unexpected errors as 500
        raise HTTPException(status_code=500, detail=str(exc)) from exc
