"""Scheduler control endpoints — read and update the shared config row."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scheduler_config import SchedulerConfig

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _get_or_create_config(db: Session) -> SchedulerConfig:
    """Return the single config row, creating it with defaults if absent."""
    config = db.query(SchedulerConfig).filter(SchedulerConfig.id == 1).first()
    if not config:
        config = SchedulerConfig(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get("/status")
def get_status(db: Session = Depends(get_db)) -> dict:
    """Return current scheduler config and last run stats."""
    config = _get_or_create_config(db)
    return {
        "is_enabled": config.is_enabled,
        "fetch_interval_minutes": config.fetch_interval_minutes,
        "csv_export_time": config.csv_export_time,
        "last_run_at": config.last_run_at,
        "last_run_status": config.last_run_status,
        "next_run_at": config.next_run_at,
        "updated_at": config.updated_at,
    }


class SchedulerUpdate(BaseModel):
    fetch_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    csv_export_time: str | None = None
    is_enabled: bool | None = None


@router.patch("/config")
def update_config(payload: SchedulerUpdate, db: Session = Depends(get_db)) -> dict:
    """Update scheduler settings. Changes take effect on the next scheduler loop tick."""
    config = _get_or_create_config(db)

    if payload.fetch_interval_minutes is not None:
        config.fetch_interval_minutes = payload.fetch_interval_minutes
    if payload.csv_export_time is not None:
        # Basic HH:MM validation
        try:
            datetime.strptime(payload.csv_export_time, "%H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="csv_export_time must be HH:MM")
        config.csv_export_time = payload.csv_export_time
    if payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled

    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    return {"message": "Config updated", "config": {
        "is_enabled": config.is_enabled,
        "fetch_interval_minutes": config.fetch_interval_minutes,
        "csv_export_time": config.csv_export_time,
        "updated_at": config.updated_at,
    }}
