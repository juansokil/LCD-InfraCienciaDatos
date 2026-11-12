CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.sismos (
    event_id           TEXT PRIMARY KEY,
    magnitud           DOUBLE PRECISION,
    lugar              TEXT,
    fecha_utc          TIMESTAMPTZ,
    latitud            DOUBLE PRECISION,
    longitud           DOUBLE PRECISION,
    profundidad_km     DOUBLE PRECISION,
    es_tsunami         SMALLINT NOT NULL DEFAULT 0,
    source_updated_ms  BIGINT,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Índice para las consultas más frecuentes de Gold
CREATE INDEX IF NOT EXISTS idx_silver_sismos_fecha
    ON silver.sismos (fecha_utc);