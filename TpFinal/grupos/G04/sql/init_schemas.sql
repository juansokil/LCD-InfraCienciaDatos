-- =====================================
-- 1. SCHEMAS
-- =====================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;


-- =====================================
-- 2. BRONZE
-- =====================================

CREATE TABLE IF NOT EXISTS bronze.clima_raw (
    consulta_id UUID PRIMARY KEY,
    run_id TEXT NOT NULL,
    ciudad_id TEXT NOT NULL,
    ciudad_nombre TEXT NOT NULL,
    latitud NUMERIC(8,4) NOT NULL,
    longitud NUMERIC(8,4) NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    source_url TEXT NOT NULL,
    raw_path TEXT NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    payload JSONB NOT NULL,

    UNIQUE (run_id, ciudad_id)
);


-- =====================================
-- 3. SILVER - CLIMA ACTUAL
-- =====================================

CREATE TABLE IF NOT EXISTS silver.clima_actual (
    consulta_id UUID PRIMARY KEY
        REFERENCES bronze.clima_raw(consulta_id),

    ciudad_id TEXT NOT NULL,
    ciudad_nombre TEXT NOT NULL,
    latitud NUMERIC(8,4) NOT NULL,
    longitud NUMERIC(8,4) NOT NULL,
    instante_local TIMESTAMP NOT NULL,
    temperatura_c NUMERIC(6,2) NOT NULL,
    humedad_pct NUMERIC(5,2) NOT NULL,
    sensacion_termica_c NUMERIC(6,2),
    viento_kmh NUMERIC(7,2),
    ingested_at TIMESTAMPTZ NOT NULL
);


-- =====================================
-- 4. SILVER - PRONOSTICO DIARIO
-- =====================================

CREATE TABLE IF NOT EXISTS silver.pronostico_diario (
    consulta_id UUID NOT NULL
        REFERENCES bronze.clima_raw(consulta_id),

    ciudad_id TEXT NOT NULL,
    fecha_pronostico DATE NOT NULL,
    temp_max_c NUMERIC(6,2) NOT NULL,
    temp_min_c NUMERIC(6,2) NOT NULL,
    sensacion_termica_max_c NUMERIC(6,2),
    precipitacion_mm NUMERIC(8,2) NOT NULL,
    viento_max_kmh NUMERIC(7,2),
    ingested_at TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (consulta_id, fecha_pronostico)
);


-- =====================================
-- 5. SILVER - QUARANTINE
-- =====================================

CREATE TABLE IF NOT EXISTS silver.clima_quarantine (
    quarantine_id BIGSERIAL PRIMARY KEY,

    consulta_id UUID NOT NULL
        REFERENCES bronze.clima_raw(consulta_id),

    ciudad_id TEXT NOT NULL,
    tipo_registro TEXT NOT NULL
        CHECK (tipo_registro IN ('actual', 'diario')),
    fecha_pronostico DATE,
    motivo TEXT NOT NULL,
    raw_record JSONB NOT NULL,
    registrado_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW()
);

-- Evita duplicar el mismo rechazo en un reintento.
-- Incluye hash del registro para diferenciar rechazos distintos.

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_clima_quarantine_logica
ON silver.clima_quarantine (
    consulta_id,
    tipo_registro,
    COALESCE(fecha_pronostico, DATE '0001-01-01'),
    motivo,
    md5(raw_record::text)
);


-- =====================================
-- 6. GOLD - DIMENSION CIUDAD
-- =====================================

CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
    ciudad_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    latitud NUMERIC(8,4) NOT NULL,
    longitud NUMERIC(8,4) NOT NULL
);


-- =====================================
-- 7. GOLD - DIMENSION TIEMPO
-- =====================================

CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    fecha_id INTEGER PRIMARY KEY,
    fecha DATE UNIQUE NOT NULL,
    anio SMALLINT NOT NULL,
    mes SMALLINT NOT NULL
        CHECK (mes BETWEEN 1 AND 12),
    dia SMALLINT NOT NULL,
    dia_semana SMALLINT NOT NULL
        CHECK (dia_semana BETWEEN 1 AND 7)
);


-- =====================================
-- 8. GOLD - TABLA DE HECHOS
-- =====================================

CREATE TABLE IF NOT EXISTS gold.fact_clima_diario (
    consulta_id UUID NOT NULL,

    ciudad_id TEXT NOT NULL
        REFERENCES gold.dim_ciudad(ciudad_id),

    fecha_id INTEGER NOT NULL
        REFERENCES gold.dim_tiempo(fecha_id),

    fecha_consulta_utc TIMESTAMPTZ NOT NULL,
    temp_max_c NUMERIC(6,2) NOT NULL,
    temp_min_c NUMERIC(6,2) NOT NULL,
    sensacion_termica_max_c NUMERIC(6,2),
    precipitacion_mm NUMERIC(8,2) NOT NULL,
    viento_max_kmh NUMERIC(7,2),

    PRIMARY KEY (consulta_id, fecha_id)
);


-- =====================================
-- 9. INDICES
-- =====================================

CREATE INDEX IF NOT EXISTS idx_bronze_ciudad
ON bronze.clima_raw(ciudad_id);

CREATE INDEX IF NOT EXISTS idx_bronze_ingested
ON bronze.clima_raw(ingested_at);

CREATE INDEX IF NOT EXISTS idx_silver_diario_ciudad
ON silver.pronostico_diario(ciudad_id);

CREATE INDEX IF NOT EXISTS idx_silver_diario_fecha
ON silver.pronostico_diario(fecha_pronostico);

CREATE INDEX IF NOT EXISTS idx_gold_fact_ciudad
ON gold.fact_clima_diario(ciudad_id);

CREATE INDEX IF NOT EXISTS idx_gold_fact_fecha
ON gold.fact_clima_diario(fecha_id);