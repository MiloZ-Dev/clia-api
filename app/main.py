"""CLIA application entrypoint.

Wires the weather and cleaning routers into a single FastAPI app and ensures the
database schema exists on startup.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine

# Import every ORM model so it registers on ``Base.metadata`` before
# ``create_all`` runs below. The router imports pull most models in transitively,
# but importing the modules explicitly keeps schema creation independent of
# router wiring.
from app.models import alert as _alert  # noqa: F401
from app.models import scheduler_config as _scheduler_config  # noqa: F401
from app.models import weather as _weather  # noqa: F401
from app.routers import alerts, analysis, clean, predict, scheduler, weather

# Create tables for any models that do not yet exist. Imported models register
# themselves on ``Base.metadata`` at import time (via the model imports above).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CLIA",
    version="1.0.0",
    description="AI-powered climate data pipeline — ingestion, processing & agricultural risk analysis",
)

# Allow any origin for now so the React frontend can consume the API during
# development. Tighten ``allow_origins`` before deploying to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(weather.router)
app.include_router(clean.router)
app.include_router(alerts.router)
app.include_router(predict.router)
app.include_router(analysis.router)
app.include_router(scheduler.router)


@app.get("/", tags=["health"])
def root() -> dict:
    """Root health check."""
    return {"message": "CLIA up and running"}
