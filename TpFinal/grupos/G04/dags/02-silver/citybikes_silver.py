"""
DAG Silver — CityBikes
Toma lo nuevo de Bronze (watermark sobre ingested_at), aplana el JSON,
valida, tipa y calcula metricas por snapshot -> silver.station_status.

Schedule: cada 10 min. Activo por default. Idempotente (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import pendulum
from airflow.sdk import dag, task
from sqlalchemy import text

from citybikes_common import get_warehouse_engine

ENSURE_TABLE = """
CREATE SCHEMA IF NOT EXISTS silver;
CREATE TABLE IF NOT EXISTS silver.station_status (
    network_id     TEXT        NOT NULL,
    network_name   TEXT,
    city           TEXT,
    country        TEXT,
    station_id     TEXT        NOT NULL,
    station_name   TEXT,
    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION,
    free_bikes     INTEGER,
    empty_slots    INTEGER,
    total_slots    INTEGER,
    ebikes         INTEGER,
    has_ebikes     BOOLEAN,
    occupancy_rate NUMERIC(5,4),
    is_empty       BOOLEAN,
    is_full        BOOLEAN,
    snapshot_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (station_id, snapshot_at)
);
"""

GET_WATERMARK = text(
    "SELECT COALESCE(MAX(snapshot_at), '1970-01-01'::timestamptz) FROM silver.station_status"
)

# Transformacion + limpieza, todo en SQL sobre el JSONB de bronze.
TRANSFORM_SQL = text("""
WITH src AS (
    SELECT
        b.network_id,
        b.network_name,
        b.city,
        b.country,
        b.station_id,
        b.station_payload->>'name'                              AS station_name,
        (b.station_payload->>'latitude')::double precision      AS latitude,
        (b.station_payload->>'longitude')::double precision     AS longitude,
        NULLIF(b.station_payload->>'free_bikes','')::int        AS free_bikes,
        NULLIF(b.station_payload->>'empty_slots','')::int       AS empty_slots,
        NULLIF(b.station_payload->'extra'->>'ebikes','')::int   AS ebikes,
        (b.station_payload->'extra'->>'has_ebikes')::boolean    AS has_ebikes,
        b.ingested_at                                           AS snapshot_at
    FROM bronze.citybikes_stations_raw b
    WHERE b.ingested_at > :watermark
)
INSERT INTO silver.station_status (
    network_id, network_name, city, country, station_id, station_name,
    latitude, longitude, free_bikes, empty_slots, total_slots,
    ebikes, has_ebikes, occupancy_rate, is_empty, is_full, snapshot_at
)
SELECT
    network_id, network_name, city, country, station_id, station_name,
    latitude, longitude, free_bikes, empty_slots,
    (free_bikes + COALESCE(empty_slots, 0))                       AS total_slots,
    ebikes, has_ebikes,
    ROUND(free_bikes::numeric
          / NULLIF(free_bikes + COALESCE(empty_slots, 0), 0), 4)  AS occupancy_rate,
    (free_bikes = 0)                                              AS is_empty,
    (COALESCE(empty_slots, 0) = 0)                                AS is_full,
    snapshot_at
FROM src
WHERE free_bikes IS NOT NULL
  AND free_bikes >= 0
  AND latitude  IS NOT NULL
  AND longitude IS NOT NULL
  AND latitude  BETWEEN -90 AND 90
  AND longitude BETWEEN -180 AND 180
ON CONFLICT (station_id, snapshot_at) DO NOTHING
""")


@dag(
    dag_id="citybikes_silver",
    schedule="*/10 * * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    tags=["citybikes", "silver"],
)
def citybikes_silver():

    @task
    def ensure_table():
        eng = get_warehouse_engine()
        with eng.begin() as conn:
            conn.execute(text(ENSURE_TABLE))

    @task
    def transform():
        eng = get_warehouse_engine()
        with eng.begin() as conn:
            watermark = conn.execute(GET_WATERMARK).scalar()
            result = conn.execute(TRANSFORM_SQL, {"watermark": watermark})
            print(f"[SILVER] watermark={watermark} | filas nuevas={result.rowcount}")

    ensure_table() >> transform()


citybikes_silver()
