-- ============================================================================
-- 1. ESQUEMAS DE LA ARQUITECTURA MEDALLION
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ============================================================================
-- 2. CAPA BRONZE (Datos Crudos)
-- ============================================================================
CREATE TABLE IF NOT EXISTS bronze.raw_weather_data (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    raw_json JSONB NOT NULL,
    tiempo_extraccion TIMESTAMP NOT NULL
);

-- ============================================================================
-- 3. CAPA SILVER (Datos Limpios y Normalizados)
-- ============================================================================

-- Clima histórico y actual consolidado
CREATE TABLE IF NOT EXISTS silver.weather_current (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL, 
    latitude FLOAT,
    longitude FLOAT,
    time TIMESTAMP NOT NULL,
    temperature FLOAT NOT NULL,
    windspeed FLOAT,
    winddirection FLOAT,
    precipitation FLOAT, -- <--- MODIFICADO: Agregamos la columna para medir lluvia real
    is_day INTEGER,
    weather_current INTEGER,
    timezone VARCHAR(100) NOT NULL,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ciudad, time) -- Evita duplicados si reprocesamos la misma hora
);

-- Pronóstico futuro
CREATE TABLE IF NOT EXISTS silver.weather_forecast (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    fecha_pronostico DATE NOT NULL,
    temp_min FLOAT NOT NULL,
    temp_max FLOAT NOT NULL,
    prob_lluvia FLOAT,
    weather_forecast INTEGER,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ciudad, fecha_pronostico)
);

-- ============================================================================
-- 4. CAPA GOLD (Modelo Dimensional para Dashboard)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    pais VARCHAR(100),
    latitud NUMERIC,
    longitud NUMERIC,
    UNIQUE (ciudad, pais)
);

CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    fecha DATE PRIMARY KEY,
    anio INTEGER,
    mes INTEGER,
    dia INTEGER,
    dia_semana VARCHAR(20)
);

-- Clima observado actual e histórico consolidado

CREATE TABLE IF NOT EXISTS gold.fact_clima_real (
    fecha DATE,
    ciudad_id INTEGER,
    temp_promedio NUMERIC,
    temp_max NUMERIC,
    temp_min NUMERIC,
    lluvia_acumulada NUMERIC,
    viento_promedio NUMERIC,
    PRIMARY KEY (fecha, ciudad_id),
    FOREIGN KEY (ciudad_id) REFERENCES gold.dim_ciudad(id),
    FOREIGN KEY (fecha) REFERENCES gold.dim_tiempo(fecha)
);

-- Pronóstico futuro consolidado (para análisis de precisión y visualización)

CREATE TABLE IF NOT EXISTS gold.fact_pronostico (
    fecha_pronostico DATE,
    ciudad_id INTEGER,
    temp_min_esperada NUMERIC,
    temp_max_esperada NUMERIC,
    prob_lluvia NUMERIC,
    PRIMARY KEY (fecha_pronostico, ciudad_id),
    FOREIGN KEY (ciudad_id) REFERENCES gold.dim_ciudad(id),
    FOREIGN KEY (fecha_pronostico) REFERENCES gold.dim_tiempo(fecha)
);

-- ============================================================================
-- 5. SEMILLAS / POBLADO AUTOMÁTICO (Para el arranque autónomo del stack)
-- ============================================================================

-- Precarga de las ciudades principales para linkear IDs sin errores
INSERT INTO gold.dim_ciudad (ciudad, pais, latitud, longitud) VALUES
('Buenos Aires', 'Argentina', -34.61315, -58.37723),
('San Martin', 'Argentina', -34.57713, -58.53697)
ON CONFLICT (ciudad, pais) DO NOTHING;

-- Generación automática del calendario indexado en la dimensión tiempo (2025 al 2027)
INSERT INTO gold.dim_tiempo (fecha, anio, mes, dia, dia_semana)
SELECT 
    datum AS fecha,
    EXTRACT(YEAR FROM datum) AS anio,
    EXTRACT(MONTH FROM datum) AS mes,
    EXTRACT(DAY FROM datum) AS dia,
    TO_CHAR(datum, 'TMDay') AS dia_semana
FROM (
    SELECT '2025-01-01'::DATE + SEQUENCE.DAY AS datum
    FROM generate_series(0, 1000) AS SEQUENCE(DAY)
) sub
ON CONFLICT (fecha) DO NOTHING;