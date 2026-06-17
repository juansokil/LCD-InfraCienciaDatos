import json
import os
from datetime import datetime

from airflow.decorators import dag, task


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'TpFinal')}"
)


def _parse_payload(raw_json):
    if isinstance(raw_json, str):
        return json.loads(raw_json)
    return raw_json


def _get_value(values, idx):
    if not values or idx >= len(values):
        return None
    return values[idx]


def _hourly_rows(row):
    payload = _parse_payload(row.raw_json)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []

    rows = []
    for idx, forecast_time in enumerate(times):
        rows.append(
            {
                "city": row.city,
                "forecast_time": forecast_time,
                "temperature_2m": _get_value(hourly.get("temperature_2m"), idx),
                "precipitation": _get_value(hourly.get("precipitation"), idx),
                "wind_speed_10m": _get_value(hourly.get("wind_speed_10m"), idx),
                "ingested_at": row.ingested_at,
                "source_raw_id": row.id,
            }
        )
    return rows


@dag(
    dag_id="g08_openmeteo_silver",
    start_date=datetime(2026, 6, 17),
    schedule="10 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g08", "silver", "openmeteo"],
)
def openmeteo_silver():
    @task
    def transform_weather_hourly():
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS silver.weather_hourly (
                        city TEXT NOT NULL,
                        forecast_time TIMESTAMPTZ NOT NULL,
                        temperature_2m DOUBLE PRECISION,
                        precipitation DOUBLE PRECISION,
                        wind_speed_10m DOUBLE PRECISION,
                        ingested_at TIMESTAMPTZ NOT NULL,
                        source_raw_id BIGINT NOT NULL,
                        PRIMARY KEY (city, forecast_time)
                    );
                    """
                )
            )

            bronze_exists = conn.execute(
                sqlalchemy.text("SELECT to_regclass('bronze.weather_raw')")
            ).scalar()
            if not bronze_exists:
                print("bronze.weather_raw no existe todavia. Ejecutar Bronze primero.")
                return

            bronze_rows = conn.execute(
                sqlalchemy.text(
                    """
                    SELECT id, city, raw_json, ingested_at
                    FROM bronze.weather_raw
                    ORDER BY id
                    """
                )
            ).fetchall()

            insert_sql = sqlalchemy.text(
                """
                INSERT INTO silver.weather_hourly (
                    city,
                    forecast_time,
                    temperature_2m,
                    precipitation,
                    wind_speed_10m,
                    ingested_at,
                    source_raw_id
                )
                VALUES (
                    :city,
                    :forecast_time,
                    :temperature_2m,
                    :precipitation,
                    :wind_speed_10m,
                    :ingested_at,
                    :source_raw_id
                )
                ON CONFLICT (city, forecast_time)
                DO UPDATE SET
                    temperature_2m = EXCLUDED.temperature_2m,
                    precipitation = EXCLUDED.precipitation,
                    wind_speed_10m = EXCLUDED.wind_speed_10m,
                    ingested_at = EXCLUDED.ingested_at,
                    source_raw_id = EXCLUDED.source_raw_id;
                """
            )

            total_rows = 0
            skipped_rows = 0
            for row in bronze_rows:
                rows = _hourly_rows(row)
                if not rows:
                    skipped_rows += 1
                    continue

                conn.execute(insert_sql, rows)
                total_rows += len(rows)

        print(
            "Silver Open-Meteo: "
            f"{total_rows} filas horarias procesadas, "
            f"{skipped_rows} registros Bronze sin datos hourly."
        )

    transform_weather_hourly()


openmeteo_silver()
