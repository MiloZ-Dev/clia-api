"""CSV cleaning service: split an uploaded dataset into per-city files.

Migrated from the standalone *Clean_data* project. Given a DataFrame containing a
``city`` column, it writes one CSV per city under
``{datasets_dir}/{city}/ciudad_{city}_{date}.csv``.
"""

import os
import re
from datetime import datetime, timezone

import pandas as pd

from app.core.config import settings

# Column that identifies the city each row belongs to.
CITY_COLUMN = "city"


def _safe_name(value: str) -> str:
    """Make a city name safe to use as a directory/file path component.

    Replaces path separators and other awkward characters with underscores so a
    value like ``"Washington, D.C."`` cannot escape the output directory.
    """
    return re.sub(r"[^\w\-. ]", "_", str(value)).strip()


def split_csv_by_city(df: pd.DataFrame, output_dir: str | None = None) -> dict:
    """Split ``df`` by city and persist one CSV per city.

    Args:
        df: Source data; must contain a ``city`` column.
        output_dir: Destination root. Defaults to the configured ``datasets_dir``.

    Returns:
        A summary dict with the total number of cities and the per-city row counts.

    Raises:
        KeyError: If the required ``city`` column is missing.
    """
    if CITY_COLUMN not in df.columns:
        raise KeyError(f"Expected a '{CITY_COLUMN}' column in the uploaded CSV")

    output_dir = output_dir or settings.datasets_dir
    os.makedirs(output_dir, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cities = df[CITY_COLUMN].dropna().unique()
    results: list[dict] = []

    for city in cities:
        city_df = df[df[CITY_COLUMN] == city]
        safe_city = _safe_name(city)

        city_dir = os.path.join(output_dir, safe_city)
        os.makedirs(city_dir, exist_ok=True)

        output_file = os.path.join(city_dir, f"ciudad_{safe_city}_{today}.csv")
        city_df.to_csv(output_file, index=False)

        results.append({"city": city, "rows": int(len(city_df)), "file": output_file})

    return {
        "message": "Split by city completed",
        "total_cities": int(len(cities)),
        "results": results,
    }
