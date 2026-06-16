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
CREATE TABLE IF NOT EXISTS silver.weather_current (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL, 
    latitude FLOAT,
    longitude FLOAT,
    time TIMESTAMP NOT NULL,
    temperature FLOAT NOT NULL,
    windspeed FLOAT,
    winddirection FLOAT,
    precipitation FLOAT,
    is_day INTEGER,
    weather_current INTEGER,
    timezone VARCHAR(100) NOT NULL,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ciudad, time)
);

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
    id INTEGER PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL UNIQUE,
    pais VARCHAR(100),
    latitud NUMERIC,
    longitud NUMERIC
);

CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    fecha DATE PRIMARY KEY,
    anio INTEGER,
    mes INTEGER,
    dia INTEGER,
    dia_semana VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS gold.fact_clima_real (
    fecha DATE,
    ciudad_id INTEGER,
    temp_promedio NUMERIC,
    temp_max NUMERIC,
    temp_min NUMERIC,
    lluvia_acumulada NUMERIC,
    viento_promedio NUMERIC,
    PRIMARY KEY (fecha, ciudad_id),
    FOREIGN KEY (ciudad_id) REFERENCES gold.dim_ciudad(id)
);

CREATE TABLE IF NOT EXISTS gold.fact_pronostico (
    fecha_pronostico DATE,
    ciudad_id INTEGER,
    temp_min_esperada NUMERIC,
    temp_max_esperada NUMERIC,
    prob_lluvia NUMERIC,
    PRIMARY KEY (fecha_pronostico, ciudad_id),
    FOREIGN KEY (ciudad_id) REFERENCES gold.dim_ciudad(id)
);

-- ============================================================================
-- 5. SEMILLAS / POBLADO AUTOMÁTICO
-- ============================================================================
INSERT INTO gold.dim_ciudad (id, ciudad, pais, latitud, longitud) VALUES
(1, 'Buenos Aires', 'Argentina', -34.61315, -58.37723),
(2, 'Madrid', 'España', 40.4168, -3.7038),
(3, 'Ciudad de México', 'México', 19.4326, -99.1332),
(4, 'Bogotá', 'Colombia', 4.7110, -74.0721),
(5, 'Santiago', 'Chile', -33.4489, -70.6693),
(6, 'Lima', 'Perú', -12.0464, -77.0428),
(7, 'Barcelona', 'España', 41.3874, 2.1686),
(8, 'Berlín', 'Alemania', 52.5200, 13.4050)
ON CONFLICT (id) DO NOTHING;

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