-- Crear los esquemas de la arquitectura Medallion
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Crear la tabla de ingesta cruda (Bronze)
CREATE TABLE IF NOT EXISTS bronze.raw_weather_data (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    raw_json JSONB NOT NULL,                 -- Guardamos la respuesta completa de la API
    tiempo_extraccion TIMESTAMP NOT NULL    -- Momento exacto en que Airflow hizo la consulta
);

-- Crear la tabla de datos limpios (Silver)

-- Clima actual
CREATE TABLE IF NOT EXISTS silver.weather_current (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL, 
    latitude FLOAT,
    longitude FLOAT,
    time TIMESTAMP NOT NULL, -- Fecha de la medición,
    temperature FLOAT NOT NULL,
    windspeed FLOAT,
    winddirection FLOAT,
    is_day INTEGER,
    weather_current INTEGER, -- Código meteorológico actual
    timezone VARCHAR(100) NOT NULL,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Pronóstico futuro (por default 7 días)
CREATE TABLE IF NOT EXISTS silver.weather_forecast (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    fecha_pronostico DATE NOT NULL,
    temp_min FLOAT NOT NULL,
    temp_max FLOAT NOT NULL,
    prob_lluvia FLOAT,
    weather_forecast INTEGER, -- Código meteorológico pronosticado
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW()
);

