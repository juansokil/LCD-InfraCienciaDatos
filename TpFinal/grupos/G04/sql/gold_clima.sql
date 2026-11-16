-- =====================================================================
-- CAPA GOLD: DIMENSIONES Y TABLA DE HECHOS — CLIMA OPEN-METEO
-- =====================================================================

-- 1. Dimensión de Ciudades
CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
    ciudad_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    latitud NUMERIC(8,4) NOT NULL,
    longitud NUMERIC(8,4) NOT NULL
);

-- Poblar / Upsert dim_ciudad directamente desde silver.clima_actual (o valores canónicos)
INSERT INTO gold.dim_ciudad (ciudad_id, nombre, latitud, longitud)
SELECT DISTINCT ciudad_id, ciudad_nombre, latitud, longitud
FROM silver.clima_actual -- (o silver.clima_actual según corresponda)
ON CONFLICT (ciudad_id) DO UPDATE 
SET nombre = EXCLUDED.nombre,
    latitud = EXCLUDED.latitud,
    longitud = EXCLUDED.longitud;


-- 2. Dimensión de Tiempo
CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    fecha_id INTEGER PRIMARY KEY, -- Formato YYYYMMDD (ej. 20261104)
    fecha DATE UNIQUE NOT NULL,
    anio SMALLINT NOT NULL,
    mes SMALLINT NOT NULL,
    dia SMALLINT NOT NULL,
    dia_semana SMALLINT NOT NULL -- ISO: 1 (Lunes) a 7 (Domingo)
);

-- Poblar dim_tiempo de forma segura basada en las fechas existentes en silver.pronostico_diario
INSERT INTO gold.dim_tiempo (fecha_id, fecha, anio, mes, dia, dia_semana)
SELECT DISTINCT 
    CAST(TO_CHAR(fecha_pronostico, 'YYYYMMDD') AS INTEGER) AS fecha_id,
    fecha_pronostico AS fecha,
    EXTRACT(YEAR FROM fecha_pronostico)::SMALLINT AS anio,
    EXTRACT(MONTH FROM fecha_pronostico)::SMALLINT AS mes,
    EXTRACT(DAY FROM fecha_pronostico)::SMALLINT AS dia,
    EXTRACT(ISODOW FROM fecha_pronostico)::SMALLINT AS dia_semana
FROM silver.pronostico_diario
ON CONFLICT (fecha_id) DO NOTHING;


-- 3. Tabla de Hechos: Clima Diario (Forecast)
CREATE TABLE IF NOT EXISTS gold.fact_clima_diario (
    consulta_id UUID,
    ciudad_id TEXT REFERENCES gold.dim_ciudad(ciudad_id),
    fecha_id INTEGER REFERENCES gold.dim_tiempo(fecha_id),
    fecha_consulta_utc TIMESTAMPTZ NOT NULL,
    temp_max_c NUMERIC(6,2) NOT NULL,
    temp_min_c NUMERIC(6,2) NOT NULL,
    sensacion_termica_max_c NUMERIC(6,2),
    precipitacion_mm NUMERIC(8,2) NOT NULL,
    viento_max_kmh NUMERIC(7,2),
    PRIMARY KEY (consulta_id, fecha_id)
);

-- Cargar la tabla de hechos con idempotencia (ON CONFLICT DO NOTHING)
INSERT INTO gold.fact_clima_diario (
    consulta_id,
    ciudad_id,
    fecha_id,
    fecha_consulta_utc,
    temp_max_c,
    temp_min_c,
    sensacion_termica_max_c,
    precipitacion_mm,
    viento_max_kmh
)
SELECT 
    p.consulta_id,
    p.ciudad_id,
    CAST(TO_CHAR(p.fecha_pronostico, 'YYYYMMDD') AS INTEGER) AS fecha_id,
    p.ingested_at AS fecha_consulta_utc,
    p.temp_max_c,
    p.temp_min_c,
    p.sensacion_termica_max_c,
    p.precipitacion_mm,
    p.viento_max_kmh
FROM silver.pronostico_diario p
ON CONFLICT (consulta_id, fecha_id) DO NOTHING;