from datetime import datetime, timezone
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

BRONZE_ASSET = Asset(
    name="g09_bronze_open_meteo_raw",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/bronze/open_meteo_raw",
)
SILVER_ASSET = Asset(
    name="g09_silver_open_meteo_clean",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/silver/clima_diario_clean",
)

def get_database_engine():
    return create_engine(
        URL.create(
            drivername="postgresql+psycopg2",
            username=os.environ.get("SOURCE_DB_USER", "admin"),
            password=os.environ.get("SOURCE_DB_PASS", "admin"),
            host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
            port=int(os.getenv("SOURCE_DB_PORT", "5432")),
            database=os.environ.get("SOURCE_DB_NAME", "InfraCienciaDatos"),
        ),
        pool_pre_ping=True,
    )


CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS silver"

DROP_SQL = "DROP TABLE IF EXISTS silver.clima_diario_clean CASCADE"

# Una fila por ciudad y dia, a partir de la ULTIMA ingesta de cada ciudad.
TRANSFORM_SQL = """
CREATE TABLE silver.clima_diario_clean AS
SELECT
    r.city AS ciudad,
    r.region_type AS region,
    (r.response_payload->'daily'->'time'->>i)::date AS fecha,
    (r.response_payload->'daily'->'temperature_2m_mean'->>i)::numeric AS temp_media_c,
    (r.response_payload->'daily'->'temperature_2m_max'->>i)::numeric AS temp_max_c,
    (r.response_payload->'daily'->'temperature_2m_min'->>i)::numeric AS temp_min_c,
    (r.response_payload->'daily'->'precipitation_sum'->>i)::numeric AS lluvia_mm,
    (r.response_payload->'daily'->'wind_speed_10m_mean'->>i)::numeric AS viento_kmh
FROM (
    SELECT DISTINCT ON (location_id) *
    FROM bronze.open_meteo_raw
    ORDER BY location_id, ingested_at DESC
) r
CROSS JOIN LATERAL generate_series(
    0, jsonb_array_length(r.response_payload->'daily'->'time') - 1
) AS i
WHERE (r.response_payload->'daily'->'temperature_2m_mean'->>i) IS NOT NULL
"""


@dag(
    dag_id="g09_silver_open_meteo",
    description="Limpieza y aplanado de datos Open-Meteo (SQL)",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[BRONZE_ASSET],
    catchup=False,
    max_active_runs=1,
    tags=["g09", "silver"],
)
def g09_silver_open_meteo():

    @task(outlets=[SILVER_ASSET])
    def clean_daily_data():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.execute(text(CREATE_SCHEMA_SQL))
                conn.execute(text(DROP_SQL))
                conn.execute(text(TRANSFORM_SQL))
                n = conn.execute(
                    text("SELECT COUNT(*) FROM silver.clima_diario_clean")
                ).scalar()
            print(f"silver.clima_diario_clean: {n} filas")
        finally:
            engine.dispose()

    clean_daily_data()


g09_silver_open_meteo()