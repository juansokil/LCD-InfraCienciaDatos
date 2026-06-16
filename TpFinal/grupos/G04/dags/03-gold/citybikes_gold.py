"""
DAG Gold — CityBikes
Construye el modelo de consumo desde Silver:
  - gold.dim_network    (red / ciudad)
  - gold.dim_station    (ultima info por estacion + first/last seen)
  - gold.fact_station_hourly  (agregados por estacion y hora)
  - gold.station_current      (ultima foto por estacion, para el mapa en vivo)

Schedule: cada 15 min -> mantiene fresca la foto actual y va refinando
los buckets de la hora en curso. Idempotente.
"""
from __future__ import annotations

import pendulum
from airflow.sdk import dag, task
from sqlalchemy import text

from citybikes_common import get_warehouse_engine

ENSURE_TABLES = """
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.dim_network (
    network_id TEXT PRIMARY KEY,
    name       TEXT,
    city       TEXT,
    country    TEXT
);

CREATE TABLE IF NOT EXISTS gold.dim_station (
    station_id   TEXT PRIMARY KEY,
    network_id   TEXT NOT NULL,
    station_name TEXT,
    city         TEXT,
    country      TEXT,
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    total_slots  INTEGER,
    first_seen   TIMESTAMPTZ,
    last_seen    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS gold.fact_station_hourly (
    station_id      TEXT        NOT NULL,
    network_id      TEXT        NOT NULL,
    hour_bucket     TIMESTAMPTZ NOT NULL,
    snapshots       INTEGER,
    avg_free_bikes  NUMERIC(8,2),
    min_free_bikes  INTEGER,
    max_free_bikes  INTEGER,
    avg_empty_slots NUMERIC(8,2),
    avg_occupancy   NUMERIC(5,4),
    pct_time_empty  NUMERIC(5,4),
    pct_time_full   NUMERIC(5,4),
    PRIMARY KEY (station_id, hour_bucket)
);

CREATE TABLE IF NOT EXISTS gold.station_current (
    station_id     TEXT PRIMARY KEY,
    network_id     TEXT,
    station_name   TEXT,
    city           TEXT,
    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION,
    free_bikes     INTEGER,
    empty_slots    INTEGER,
    total_slots    INTEGER,
    occupancy_rate NUMERIC(5,4),
    snapshot_at    TIMESTAMPTZ
);
"""

UPSERT_DIM_NETWORK = text("""
INSERT INTO gold.dim_network (network_id, name, city, country)
SELECT DISTINCT ON (network_id) network_id, network_name, city, country
FROM silver.station_status
ORDER BY network_id, snapshot_at DESC
ON CONFLICT (network_id) DO UPDATE SET
    name = EXCLUDED.name, city = EXCLUDED.city, country = EXCLUDED.country
""")

UPSERT_DIM_STATION = text("""
WITH latest AS (
    SELECT DISTINCT ON (station_id)
        station_id, network_id, station_name, city, country,
        latitude, longitude,
        (free_bikes + COALESCE(empty_slots, 0)) AS total_slots
    FROM silver.station_status
    ORDER BY station_id, snapshot_at DESC
),
span AS (
    SELECT station_id, MIN(snapshot_at) AS first_seen, MAX(snapshot_at) AS last_seen
    FROM silver.station_status
    GROUP BY station_id
)
INSERT INTO gold.dim_station (
    station_id, network_id, station_name, city, country,
    latitude, longitude, total_slots, first_seen, last_seen
)
SELECT l.station_id, l.network_id, l.station_name, l.city, l.country,
       l.latitude, l.longitude, l.total_slots, s.first_seen, s.last_seen
FROM latest l
JOIN span s USING (station_id)
ON CONFLICT (station_id) DO UPDATE SET
    network_id   = EXCLUDED.network_id,
    station_name = EXCLUDED.station_name,
    city         = EXCLUDED.city,
    country      = EXCLUDED.country,
    latitude     = EXCLUDED.latitude,
    longitude    = EXCLUDED.longitude,
    total_slots  = EXCLUDED.total_slots,
    first_seen   = LEAST(gold.dim_station.first_seen, EXCLUDED.first_seen),
    last_seen    = GREATEST(gold.dim_station.last_seen, EXCLUDED.last_seen)
""")

UPSERT_STATION_CURRENT = text("""
INSERT INTO gold.station_current (
    station_id, network_id, station_name, city, latitude, longitude,
    free_bikes, empty_slots, total_slots, occupancy_rate, snapshot_at
)
SELECT DISTINCT ON (station_id)
    station_id, network_id, station_name, city, latitude, longitude,
    free_bikes, empty_slots, total_slots, occupancy_rate, snapshot_at
FROM silver.station_status
ORDER BY station_id, snapshot_at DESC
ON CONFLICT (station_id) DO UPDATE SET
    network_id     = EXCLUDED.network_id,
    station_name   = EXCLUDED.station_name,
    city           = EXCLUDED.city,
    latitude       = EXCLUDED.latitude,
    longitude      = EXCLUDED.longitude,
    free_bikes     = EXCLUDED.free_bikes,
    empty_slots    = EXCLUDED.empty_slots,
    total_slots    = EXCLUDED.total_slots,
    occupancy_rate = EXCLUDED.occupancy_rate,
    snapshot_at    = EXCLUDED.snapshot_at
""")

# Recalcula las ultimas 3 horas (idempotente: borra y reinserta)
DELETE_RECENT_FACT = text("""
DELETE FROM gold.fact_station_hourly
WHERE hour_bucket >= date_trunc('hour', now()) - interval '3 hours'
""")

INSERT_FACT = text("""
INSERT INTO gold.fact_station_hourly (
    station_id, network_id, hour_bucket, snapshots,
    avg_free_bikes, min_free_bikes, max_free_bikes,
    avg_empty_slots, avg_occupancy, pct_time_empty, pct_time_full
)
SELECT
    station_id,
    network_id,
    date_trunc('hour', snapshot_at)                     AS hour_bucket,
    COUNT(*)                                            AS snapshots,
    ROUND(AVG(free_bikes), 2)                           AS avg_free_bikes,
    MIN(free_bikes)                                     AS min_free_bikes,
    MAX(free_bikes)                                     AS max_free_bikes,
    ROUND(AVG(empty_slots), 2)                          AS avg_empty_slots,
    ROUND(AVG(occupancy_rate), 4)                       AS avg_occupancy,
    ROUND(AVG(CASE WHEN is_empty THEN 1 ELSE 0 END), 4) AS pct_time_empty,
    ROUND(AVG(CASE WHEN is_full  THEN 1 ELSE 0 END), 4) AS pct_time_full
FROM silver.station_status
WHERE snapshot_at >= date_trunc('hour', now()) - interval '3 hours'
GROUP BY station_id, network_id, date_trunc('hour', snapshot_at)
""")


@dag(
    dag_id="citybikes_gold",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    tags=["citybikes", "gold"],
    # Reintentos: si el warehouse todavia no esta listo (arranque en frio), reintenta
    # en vez de quedar en rojo. Las tareas son idempotentes, asi que es seguro.
    default_args={"retries": 3, "retry_delay": pendulum.duration(seconds=30)},
)
def citybikes_gold():

    @task
    def ensure_tables():
        eng = get_warehouse_engine()
        with eng.begin() as conn:
            conn.execute(text(ENSURE_TABLES))

    @task
    def build_dimensions():
        eng = get_warehouse_engine()
        with eng.begin() as conn:
            conn.execute(UPSERT_DIM_NETWORK)
            conn.execute(UPSERT_DIM_STATION)
            conn.execute(UPSERT_STATION_CURRENT)

    @task
    def build_fact():
        eng = get_warehouse_engine()
        with eng.begin() as conn:
            conn.execute(DELETE_RECENT_FACT)
            res = conn.execute(INSERT_FACT)
            print(f"[GOLD] fact_station_hourly filas (ultimas 3h) = {res.rowcount}")

    ensure_tables() >> build_dimensions() >> build_fact()


citybikes_gold()
