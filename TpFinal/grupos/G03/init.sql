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