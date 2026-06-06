"""Application configuration.

Centralizes all environment-driven settings in a single typed object so the rest
of the codebase never reads ``os.environ`` directly. Values are loaded from the
process environment and, as a convenience for local development, from a ``.env``
file in the project root.
"""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from the environment.

    Attribute names map to environment variables case-insensitively, so
    ``WEATHER_API_KEY`` populates :attr:`weather_api_key`.
    """

    # --- WeatherAPI.com integration ---------------------------------------
    weather_api_key: str = ""
    weather_api_base_url: str = "http://api.weatherapi.com/v1/current.json"

    # --- Anthropic (Claude) AI analysis -----------------------------------
    anthropic_api_key: str = ""

    # --- OpenWeatherMap air-quality enrichment ----------------------------
    openweathermap_api_key: str = ""

    # --- PostgreSQL connection --------------------------------------------
    postgres_user: str = "clia_user"
    postgres_password: str = "clia_password"
    postgres_db: str = "clia_db"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # --- Scheduler behaviour ----------------------------------------------
    fetch_interval_minutes: int = 30
    csv_export_time: str = "23:59"

    # --- Output locations -------------------------------------------------
    exports_dir: str = "exports"
    datasets_dir: str = "datasets"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Build the SQLAlchemy PostgreSQL connection URL from discrete parts.

        The user and password are percent-encoded so credentials containing
        URL-reserved characters (e.g. ``@``, ``:``, ``[``, ``$``) do not corrupt
        the connection string.
        """
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    The cache guarantees the environment is parsed only once per process.
    """
    return Settings()


# Module-level singleton for convenient importing: ``from app.core.config import settings``.
settings = get_settings()
