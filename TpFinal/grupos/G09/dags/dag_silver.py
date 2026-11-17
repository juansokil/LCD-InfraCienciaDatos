from datetime import datetime, timezone
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

BRONZE_ASSET = Asset(
    name="g09_bronze_open_meteo_raw",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/bronze/open_meteo_raw",
)
SILVER_ASSET = Asset(
    name="g09_silver_open_meteo_clean",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/silver/clima_horario",
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

# 1. DDL (Creación de tablas)
DDL_SQL = """
CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.clima_horario (
    ciudad              TEXT        NOT NULL,
    region              TEXT        NOT NULL,
    fecha_hora          TIMESTAMP   NOT NULL,
    temp_c              NUMERIC(5,2),
    sensacion_c         NUMERIC(5,2),
    humedad_pct         NUMERIC(5,2),
    lluvia_mm           NUMERIC(6,2),
    viento_kmh          NUMERIC(6,2),
    nubosidad_pct       NUMERIC(5,2),
    weather_code        INT,
    es_pronostico       BOOLEAN     NOT NULL,
    source_snapshot_ts  TIMESTAMPTZ NOT NULL,
    source_ingested_at  TIMESTAMPTZ NOT NULL,
    silver_updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ciudad, fecha_hora)
);

CREATE TABLE IF NOT EXISTS silver.quarantine_clima_horario (
    ciudad              TEXT        NOT NULL,
    region              TEXT,
    fecha_hora          TIMESTAMP   NOT NULL,
    motivo              TEXT        NOT NULL,
    fila_original       JSONB,
    source_snapshot_ts  TIMESTAMPTZ NOT NULL,
    quarantined_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ciudad, fecha_hora, motivo, source_snapshot_ts)
);
"""

# 2. Staging (Tabla persistente, ya NO tiene ON COMMIT DROP)

STAGE_SQL = """
DROP TABLE IF EXISTS silver.stg_clima;

CREATE TABLE silver.stg_clima AS

WITH nuevos AS (
    SELECT
        city,
        region_type,
        snapshot_ts,
        ingested_at,
        api_url,
        response_payload AS p
    FROM bronze.open_meteo_raw
    WHERE ingested_at > COALESCE(
        (
            SELECT MAX(source_ingested_at)
            FROM silver.clima_horario
        ),
        '-infinity'::timestamptz
    )
),

expandido AS (
    SELECT
        n.city AS ciudad,
        n.region_type AS region,
        n.snapshot_ts,
        n.ingested_at,
        n.api_url,

        datos.fecha_hora_txt::timestamp AS fecha_hora,
        datos.temp_txt::numeric AS temp_c,
        datos.sensacion_txt::numeric AS sensacion_c,
        datos.humedad_txt::numeric AS humedad_pct,
        datos.lluvia_txt::numeric AS lluvia_mm,
        datos.viento_txt::numeric AS viento_kmh,
        datos.nubosidad_txt::numeric AS nubosidad_pct,
        datos.weather_code_txt::numeric::int AS weather_code

    FROM nuevos n

    CROSS JOIN LATERAL ROWS FROM (
        jsonb_array_elements_text(n.p->'hourly'->'time'),
        jsonb_array_elements_text(n.p->'hourly'->'temperature_2m'),
        jsonb_array_elements_text(n.p->'hourly'->'apparent_temperature'),
        jsonb_array_elements_text(n.p->'hourly'->'relative_humidity_2m'),
        jsonb_array_elements_text(n.p->'hourly'->'precipitation'),
        jsonb_array_elements_text(n.p->'hourly'->'wind_speed_10m'),
        jsonb_array_elements_text(n.p->'hourly'->'cloud_cover'),
        jsonb_array_elements_text(n.p->'hourly'->'weather_code')
    ) AS datos(
        fecha_hora_txt,
        temp_txt,
        sensacion_txt,
        humedad_txt,
        lluvia_txt,
        viento_txt,
        nubosidad_txt,
        weather_code_txt
    )
)

SELECT DISTINCT ON (ciudad, fecha_hora)

    ciudad,
    region,
    fecha_hora,

    temp_c,
    sensacion_c,
    humedad_pct,
    lluvia_mm,
    viento_kmh,
    nubosidad_pct,
    weather_code,

    CASE
        WHEN api_url = 'https://api.open-meteo.com/v1/forecast'
        THEN (
            fecha_hora AT TIME ZONE 'America/Argentina/Buenos_Aires'
        ) > snapshot_ts
        ELSE FALSE
    END AS es_pronostico,

    snapshot_ts AS source_snapshot_ts,
    ingested_at AS source_ingested_at,

    CASE
        WHEN temp_c IS NULL
            THEN 'temp_nula'

        WHEN temp_c NOT BETWEEN -60 AND 60
            THEN 'temp_fuera_de_rango'

        WHEN humedad_pct IS NULL
            THEN 'humedad_nula'

        WHEN humedad_pct NOT BETWEEN 0 AND 100
            THEN 'humedad_fuera_de_rango'

        WHEN lluvia_mm IS NULL
            THEN 'lluvia_nula'

        WHEN lluvia_mm < 0
            THEN 'lluvia_negativa'

        WHEN viento_kmh IS NULL
            THEN 'viento_nulo'

        WHEN viento_kmh < 0
            THEN 'viento_negativo'
    END AS motivo

FROM expandido

ORDER BY
    ciudad,
    fecha_hora,

    -- Priorizar el histórico cuando existe para esa fecha.
    CASE
        WHEN api_url = 'https://archive-api.open-meteo.com/v1/archive'
        THEN 1
        ELSE 0
    END DESC,

    -- Si hay varios snapshots de pronóstico, elegir el más reciente.
    snapshot_ts DESC;
"""


# 3. UPSERT de válidos
UPSERT_SQL = """
INSERT INTO silver.clima_horario (
    ciudad, region, fecha_hora, temp_c, sensacion_c, humedad_pct, lluvia_mm,
    viento_kmh, nubosidad_pct, weather_code, es_pronostico,
    source_snapshot_ts, source_ingested_at
)
SELECT
    ciudad, region, fecha_hora, temp_c, sensacion_c, humedad_pct, lluvia_mm,
    viento_kmh, nubosidad_pct, weather_code, es_pronostico,
    source_snapshot_ts, source_ingested_at
FROM silver.stg_clima
WHERE motivo IS NULL
ON CONFLICT (ciudad, fecha_hora) DO UPDATE SET
    region             = EXCLUDED.region,
    temp_c             = EXCLUDED.temp_c,
    sensacion_c        = EXCLUDED.sensacion_c,
    humedad_pct        = EXCLUDED.humedad_pct,
    lluvia_mm          = EXCLUDED.lluvia_mm,
    viento_kmh         = EXCLUDED.viento_kmh,
    nubosidad_pct      = EXCLUDED.nubosidad_pct,
    weather_code       = EXCLUDED.weather_code,
    es_pronostico      = EXCLUDED.es_pronostico,
    source_snapshot_ts = EXCLUDED.source_snapshot_ts,
    source_ingested_at = EXCLUDED.source_ingested_at,
    silver_updated_at  = NOW()
WHERE silver.clima_horario.source_snapshot_ts <= EXCLUDED.source_snapshot_ts;
"""

# 4. Inserción en Cuarentena
QUARANTINE_SQL = """
INSERT INTO silver.quarantine_clima_horario
    (ciudad, region, fecha_hora, motivo, fila_original, source_snapshot_ts)
SELECT ciudad, region, fecha_hora, motivo, to_jsonb(s) - 'motivo', source_snapshot_ts
FROM silver.stg_clima s
WHERE motivo IS NOT NULL
ON CONFLICT DO NOTHING;
"""

@dag(
    dag_id="g09_silver_open_meteo",
    description="Limpieza incremental de Open-Meteo (SQL) multi-task",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[BRONZE_ASSET],
    catchup=False,
    max_active_runs=1,
    tags=["g09", "silver"],
)
def g09_silver_open_meteo():

    @task
    def create_tables():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(DDL_SQL)
        finally:
            engine.dispose()

    @task
    def stage_data():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(STAGE_SQL)
        finally:
            engine.dispose()

    @task
    def load_silver():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(UPSERT_SQL)
        finally:
            engine.dispose()

    @task
    def load_quarantine():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(QUARANTINE_SQL)
        finally:
            engine.dispose()

    @task(outlets=[SILVER_ASSET])
    def publish_silver_asset():
        print("Silver procesado y listo. Gold puede arrancar.")

    # El grafo (lo que se ve en la UI)
    t_setup = create_tables()
    t_stage = stage_data()
    t_silver = load_silver()
    t_quarantine = load_quarantine()
    t_publish = publish_silver_asset()

    # Dependencias: Setup -> Stage -> (Silver || Quarantine) -> Publish
    t_setup >> t_stage >> [t_silver, t_quarantine] >> t_publish

g09_silver_open_meteo()