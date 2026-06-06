"""Climate prediction endpoint.

Exposes :func:`app.services.prediction.predict_weather` over HTTP at
``/predict/{city}``.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.prediction import predict_weather

router = APIRouter(tags=["predict"])


@router.get("/predict/{city}")
def predict_city_weather(
    city: str,
    days: int = Query(default=5, ge=1, le=30),
    db: Session = Depends(get_db),
) -> dict:
    """Forecast the next ``days`` days of weather for ``city``.

    Args:
        city: City name to forecast (case-sensitive match).
        days: Number of future days to predict (default 5).
        db: Database session dependency.

    Returns:
        A dict with the city, horizon, and the per-day ``predictions`` list.

    Raises:
        HTTPException: 404 if no historical data exists for the city.
    """
    predictions = predict_weather(city, days=days, db=db)
    if not predictions:
        raise HTTPException(
            status_code=404, detail=f"No historical data available for {city}"
        )

    return {"city": city, "days": days, "predictions": predictions}
