-- Creamos el esquema si no existe
CREATE SCHEMA IF NOT EXISTS silver;

-- Dimensión Estaciones (Datos que no cambian a cada minuto)
CREATE TABLE IF NOT EXISTS silver.dim_stations (
    station_id VARCHAR(255) PRIMARY KEY,
    network_id VARCHAR(255),
    name VARCHAR(255),
    latitude NUMERIC,
    longitude NUMERIC,
    last_updated TIMESTAMP
);

-- Tabla de Hechos (El historial de las bicicletas)
CREATE TABLE IF NOT EXISTS silver.fact_station_status (
    status_id SERIAL PRIMARY KEY,
    station_id VARCHAR(255),
    free_bikes INT,
    empty_slots INT,
    timestamp_api TIMESTAMP,
    timestamp_ingesta TIMESTAMP
);