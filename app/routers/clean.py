"""CSV processing endpoints, mounted under ``/clean``.

Migrated from the standalone *Clean_data* project. Accepts a CSV upload and
splits it into per-city files via :mod:`app.services.cleaning`.
"""

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.cleaning import split_csv_by_city

router = APIRouter(prefix="/clean", tags=["clean"])


@router.get("")
def health_check() -> dict:
    """Lightweight readiness probe for the cleaning subsystem."""
    return {"status": "ok"}


@router.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...)) -> dict:
    """Accept a CSV upload and split its rows into per-city files.

    Args:
        file: An uploaded ``.csv`` file containing a ``city`` column.

    Returns:
        Metadata about the parsed file plus the per-city split summary.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    try:
        df = pd.read_csv(file.file)
    except Exception as exc:  # noqa: BLE001 - bad upload is a client error
        raise HTTPException(
            status_code=400, detail=f"Could not read CSV file: {exc}"
        ) from exc

    try:
        result = split_csv_by_city(df)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "columns": df.columns.tolist(),
        "row_count": int(df.shape[0]),
        "result": result,
        "message": "CSV file processed successfully",
    }
