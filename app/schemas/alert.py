"""Pydantic schemas for serializing alerts over the API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    """A recorded threshold breach as returned by the API."""

    id: int
    city: str
    alert_type: str
    value: float
    threshold: float
    recorded_at: datetime

    # Allow construction directly from ORM objects (Pydantic v2 style).
    model_config = ConfigDict(from_attributes=True)
