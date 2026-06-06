# CLIA — Climate Intelligence & Analytics

CLIA is a FastAPI service that collects, enriches, stores, and interprets
climate data for agricultural decision-making. It polls ~120 cities for current
conditions, enriches every observation with soil, solar, evapotranspiration, and
air-quality data, persists a full history in PostgreSQL, forecasts the days ahead
with Facebook Prophet, and asks Claude (Anthropic) to translate that raw data
into a structured agricultural-risk assessment. It is built for agronomists,
farm operators, and climate analysts who need more than a raw forecast — they
need an interpreted, risk-scored, recommendation-bearing read on what the weather
means for crops.

---

## Architecture

```
   WeatherAPI.com ──────────────┐
   (current conditions)         │
                                ▼
                          ┌───────────┐      ┌──────────────┐
   Open-Meteo ──────────► │ enrichment │ ───► │  scheduler   │
   (soil/solar/ET/gusts)  │   layer    │      │ (every 30m)  │
                          └───────────┘      └──────┬───────┘
   OpenWeatherMap ─────────────┘                    │
   (AQI / CO / PM2.5 / PM10)                        ▼
                                              ┌──────────────┐
                                              │  PostgreSQL  │
                                              │  (history)   │
                                              └──────┬───────┘
                                                     │
                          ┌──────────────────────────┼──────────────────┐
                          ▼                           ▼                  ▼
                  ┌───────────────┐          ┌────────────────┐   ┌───────────┐
                  │    Prophet    │ ───────► │   Claude AI    │   │  /alerts  │
                  │  forecasting  │          │    analysis    │   │  /stats   │
                  └───────────────┘          └────────┬───────┘   │  /export  │
                                                      ▼            └───────────┘
                                              /analyze/* endpoints
```

- **WeatherAPI.com → scheduler → PostgreSQL** — on each interval the scheduler
  fetches all cities concurrently (`asyncio.gather`) and appends every reading to
  PostgreSQL in a single transaction.
- **Open-Meteo → enrichment layer → PostgreSQL** — each reading is enriched with
  soil temperature, solar radiation, evapotranspiration, and wind gusts.
- **OpenWeatherMap → enrichment layer → PostgreSQL** — each reading is enriched
  with air-quality index and pollutant concentrations.
- **PostgreSQL → Prophet → Claude AI → /analyze** — stored history feeds the
  Prophet forecaster and the Claude analyst, exposed via the `/analyze/*` routes.

---

## Endpoints

| Method | Path                         | Description                                                          |
| ------ | ---------------------------- | -------------------------------------------------------------------- |
| GET    | `/`                          | Service health check                                                 |
| GET    | `/weather/{city}`            | Fetch + enrich live weather for a city, store it, return the record  |
| GET    | `/weather/latest/{city}`     | Latest stored record for a city from the DB (no external call; 404 if none) |
| POST   | `/weather/fetch_all`         | Manually trigger a full collection run across all configured cities  |
| GET    | `/weather/history/{city}`    | Stored history for a city within an optional date range (paginated)  |
| GET    | `/cities`                    | Full list of monitored city names                                    |
| GET    | `/stats/total`               | Total count of all weather records in the database                   |
| GET    | `/stats/{city}`              | avg/max/min aggregates for a city over a trailing window             |
| GET    | `/export`                    | Export a day's records to CSV and download the file                  |
| GET    | `/predict/{city}`            | Prophet forecast of the next N days for a city                       |
| GET    | `/alerts`                    | Recorded threshold breaches, paginated (`limit`, `offset`)           |
| GET    | `/clean`                     | Cleaning subsystem health check                                      |
| POST   | `/clean/upload_csv`          | Upload a CSV and split its rows into per-city files                  |
| GET    | `/analyze/{city}`            | AI agricultural climate analysis for a single city                   |
| POST   | `/analyze/batch`             | Analyze up to 10 cities in one request (`{"cities": [...]}`)         |
| GET    | `/analyze/alerts/regional`   | Scan a region's cities, return only those with notable risk          |
| GET    | `/scheduler/status`          | Current scheduler config and last-run stats                          |
| PATCH  | `/scheduler/config`          | Update interval, export time, or enabled flag (next tick applies)    |

Interactive API docs are available at `/docs` once the app is running.

---

## Data Sources

| API                | Provides                                                        | Key required |
| ------------------ | -------------------------------------------------------------- | ------------ |
| **WeatherAPI.com** | Current conditions: temperature, humidity, wind, pressure, UV  | Yes          |
| **Open-Meteo**     | Soil temperature, solar radiation, evapotranspiration, gusts   | No           |
| **OpenWeatherMap** | Air quality: AQI, CO, PM2.5, PM10                              | Yes          |
| **Anthropic**      | Claude AI agricultural-risk analysis of the above              | Yes          |

Enrichment fails soft: if Open-Meteo is unreachable or the OpenWeatherMap key is
missing, the base WeatherAPI.com reading is still stored — the enrichment columns
are simply left null for that record.

---

## AI Analysis

The `/analyze/*` endpoints combine a city's **last 7 days** of stored
observations with a **5-day Prophet forecast** and send both to Claude
(`claude-sonnet-4-20250514`) with an agricultural-climate-analyst prompt. Claude
returns a strict JSON assessment — current-conditions summary, trend, an
agricultural risk level, detected risk factors, actionable recommendations for
farmers, a plain-language reading of the forecast, an optional alert, and a
confidence level. The service then annotates the result with `generated_at` and
`data_points_analyzed`.

Example response:

```json
{
  "city": "Cali",
  "summary": "Las condiciones actuales son cálidas y húmedas, con lluvias moderadas en los últimos días. La humedad del suelo se mantiene en niveles favorables para los cultivos.",
  "trend": "estable",
  "agricultural_risk": "medio",
  "risk_factors": ["humedad elevada", "riesgo de hongos foliares"],
  "recommendations": [
    "Monitorear cultivos sensibles a hongos y aplicar fungicida preventivo.",
    "Aprovechar la humedad del suelo para siembras de ciclo corto."
  ],
  "forecast_insight": "El pronóstico de Prophet indica temperaturas estables y precipitación constante durante los próximos 5 días.",
  "alert": null,
  "confidence": "media",
  "data_sources": ["WeatherAPI", "Open-Meteo", "OpenWeatherMap"],
  "generated_at": "2026-06-05T18:42:11.482931+00:00",
  "data_points_analyzed": 84
}
```

If Claude's reply cannot be parsed as JSON, the endpoint returns
`{"raw": "<model text>", "parse_error": true, ...}` so nothing is silently lost.

---

## Scheduler Control

The scheduler runs as a separate process (`clia_scheduler`), so the API cannot
control it in-memory. Instead, a single-row `scheduler_config` table acts as a
shared control channel:

- The API writes settings via `PATCH /scheduler/config` — `fetch_interval_minutes`
  (1–1440), `csv_export_time` (`HH:MM`), and `is_enabled`.
- The scheduler reads that row on every loop tick: it skips collection while
  `is_enabled` is false, and re-registers its jobs whenever the interval changes.
  Changes therefore take effect on the next tick, with no restart.
- Each collection run fetches all configured cities **concurrently** via
  `asyncio.gather`, so a full sweep takes roughly as long as the slowest single
  city rather than the sum of every request.
- After each collection run the scheduler writes back `last_run_at`,
  `last_run_status` (`success` / `error`), and `next_run_at`, which the API
  surfaces via `GET /scheduler/status`.

---

## Configuration

All configuration is environment-driven. Copy `.env.example` to `.env` and fill
in your values:

```bash
cp .env.example .env
```

| Variable                 | Default                                          | Description                              |
| ------------------------ | ------------------------------------------------ | ---------------------------------------- |
| `WEATHER_API_KEY`        | *(required)*                                     | WeatherAPI.com API key                   |
| `WEATHER_API_BASE_URL`   | `http://api.weatherapi.com/v1/current.json`      | WeatherAPI.com endpoint                  |
| `ANTHROPIC_API_KEY`      | *(required for /analyze)*                        | Anthropic (Claude) API key               |
| `OPENWEATHERMAP_API_KEY` | *(optional)*                                     | OpenWeatherMap key for air-quality data  |
| `POSTGRES_USER`          | `clia_user`                                      | Database user                            |
| `POSTGRES_PASSWORD`      | `clia_password`                                  | Database password                        |
| `POSTGRES_DB`            | `clia_db`                                         | Database name                            |
| `POSTGRES_HOST`          | `db`                                             | Database host (`db` in compose)          |
| `POSTGRES_PORT`          | `5432`                                           | Database port                            |
| `FETCH_INTERVAL_MINUTES` | `30`                                             | Collection interval in minutes           |
| `CSV_EXPORT_TIME`        | `23:59`                                          | Daily export time (`HH:MM`, 24h)         |
| `EXPORTS_DIR`            | `exports`                                        | Where daily CSV backups are written      |
| `DATASETS_DIR`           | `datasets`                                       | Where per-city splits are written        |

---

## Running with Docker Compose

```bash
cp .env.example .env        # then edit .env with your keys
docker compose up --build
```

This starts three containers:

- `clia_db` — PostgreSQL 15
- `clia_api` — FastAPI app on http://localhost:8000
- `clia_scheduler` — background collection + daily export

---

## Running locally (without Docker)

Requires Python 3.11+ and a reachable PostgreSQL instance.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # set POSTGRES_HOST=localhost for local DB

# API
uvicorn app.main:app --reload --port 8000

# Scheduler (separate terminal)
python -m app.core.scheduler
```

---

## Tech stack

| Component                          | Role                                                |
| ---------------------------------- | --------------------------------------------------- |
| **FastAPI** + **Uvicorn**          | Async web framework and server                      |
| **PostgreSQL** + **SQLAlchemy**    | Relational storage (2.0-style ORM)                  |
| **Pydantic** + **pydantic-settings** | Validation and typed configuration                |
| **httpx**                          | Async client for WeatherAPI, Open-Meteo, OWM, Claude |
| **Prophet**                        | Time-series climate forecasting                     |
| **Anthropic Claude**               | AI agricultural-risk analysis                       |
| **pandas**                         | CSV reading, splitting, and export                  |
| **schedule**                       | Recurring background jobs                            |
| **Docker Compose**                 | Orchestrates the API, database, and scheduler       |

---

## Author

**MiloDev** — [github.com/Zp07](https://github.com/Zp07)
