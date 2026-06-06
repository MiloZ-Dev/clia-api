"""SQLAlchemy ORM model for the scheduler control row.

A single-row table acting as the control channel between the API process and
the standalone scheduler process. The API writes configuration (interval,
export time, enabled flag); the scheduler reads it each loop tick and writes
back its last-run statistics.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class SchedulerConfig(Base):
    """The single scheduler control/status row (always ``id == 1``)."""

    __tablename__ = "scheduler_config"

    id = Column(Integer, primary_key=True, default=1)
    fetch_interval_minutes = Column(Integer, default=30)
    csv_export_time = Column(String, default="23:59")
    is_enabled = Column(Boolean, default=True)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Read-only stats written by the scheduler process itself
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String, nullable=True)  # "success" | "error"
    next_run_at = Column(DateTime(timezone=True), nullable=True)
