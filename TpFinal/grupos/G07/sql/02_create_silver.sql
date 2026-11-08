CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.sismos (
    event_id TEXT PRIMARY KEY,
    magnitud DOUBLE PRECISION,
    lugar TEXT,
    fecha_utc TIMESTAMPTZ NOT NULL,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    profundidad_km DOUBLE PRECISION,
    source_updated_ms BIGINT NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
