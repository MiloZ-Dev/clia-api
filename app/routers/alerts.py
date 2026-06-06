"""Alert endpoints: query recorded threshold breaches.

Mounted under ``/alerts``. Alerts are written by
:func:`app.services.alerts.check_and_store_alerts` during collection; this
router only reads them back.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertResponse

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    city: str | None = None,
    days: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Return a paginated page of recorded alerts, most recent first.

    Args:
        city: Restrict results to this city (case-sensitive match).
        days: Only include alerts recorded within the last ``days`` days.
        limit: Maximum number of alerts to return (1-500, default 50).
        offset: Number of alerts to skip for pagination (default 0).
        db: Database session dependency.

    Returns:
        ``{"total": n, "limit": ..., "offset": ..., "alerts": [...]}`` where
        ``total`` is the full match count before pagination and ``alerts`` is
        the requested page, ordered newest-first.
    """
    query = db.query(Alert)

    if city:
        query = query.filter(Alert.city == city)

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(Alert.recorded_at >= cutoff)

    total = query.count()
    alerts = (
        query.order_by(Alert.recorded_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "alerts": [AlertResponse.model_validate(alert) for alert in alerts],
    }
