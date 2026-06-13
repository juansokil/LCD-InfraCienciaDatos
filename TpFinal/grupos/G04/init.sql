-- ============================================================
-- init.sql  —  se ejecuta SOLO la primera vez que arranca el
-- contenedor del warehouse (montado en /docker-entrypoint-initdb.d).
-- Crea los schemas y todas las tablas de las 3 capas.
-- Las tablas se crean acá para que el dashboard nunca falle por
-- "tabla inexistente", incluso antes de la primera corrida de los DAGs.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ---------- BRONZE: datos crudos tal como llegan ----------
CREATE TABLE IF NOT EXISTS bronze.citybikes_stations_raw (
    ingestion_id    BIGSERIAL   PRIMARY KEY,
    network_id      TEXT        NOT NULL,
    network_name    TEXT,
    city            TEXT,
    country         TEXT,
    station_id      TEXT        NOT NULL,
    station_payload JSONB       NOT NULL,
    source          TEXT        NOT NULL DEFAULT 'api.citybik.es/v2',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_ingested_at ON bronze.citybikes_stations_raw (ingested_at);
CREATE INDEX IF NOT EXISTS ix_bronze_network     ON bronze.citybikes_stations_raw (network_id);

-- ---------- SILVER: limpio, tipado, validado ----------
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
CREATE INDEX IF NOT EXISTS ix_silver_network_time ON silver.station_status (network_id, snapshot_at);

-- ---------- GOLD: modelo dimensional + agregados ----------
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

-- Hecho: estado agregado por estacion y hora
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
CREATE INDEX IF NOT EXISTS ix_gold_hour ON gold.fact_station_hourly (hour_bucket);

-- Foto "actual" de cada estacion (para el mapa en vivo del dashboard)
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
