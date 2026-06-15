-- ==================================================
-- INICIALIZACIÓN DE BASE DE DATOS - LIC. CIENCIA DE DATOS
-- ==================================================

-- 1. Esquema Origen (Donde caen los datos crudos del sistema externo)
CREATE SCHEMA IF NOT EXISTS "InfraCienciaDatos";

-- 2. Esquemas de Arquitectura Medallón (Procesamiento ELT)
CREATE SCHEMA IF NOT EXISTS "bronze";
CREATE SCHEMA IF NOT EXISTS "silver";
CREATE SCHEMA IF NOT EXISTS "gold";

-- 1. Dimensión Estaciones
CREATE TABLE IF NOT EXISTS gold.dim_station (
    station_id VARCHAR(50) PRIMARY KEY,
    station_name VARCHAR(255) NOT NULL,
    address TEXT,
    total_capacity INT NOT NULL,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL
);

-- 2. Dimensión Tiempo
CREATE TABLE IF NOT EXISTS gold.dim_time (
    time_id INT PRIMARY KEY,
    full_timestamp TIMESTAMP WITH TIME ZONE UNIQUE NOT NULL,
    hour INT NOT NULL,
    minute INT NOT NULL,
    day_of_week VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- 3. Tabla de Hechos (La estrella central)
CREATE TABLE IF NOT EXISTS gold.fact_station_availability (
    fact_key SERIAL PRIMARY KEY,
    time_id INT NOT NULL REFERENCES gold.dim_time(time_id),
    station_id VARCHAR(50) NOT NULL REFERENCES gold.dim_station(station_id),
    bikes_available INT NOT NULL,
    slots_available INT NOT NULL,
    occupancy_ratio FLOAT NOT NULL,
    CONSTRAINT unique_snapshot_station UNIQUE (time_id, station_id)
);

-- Comentario pedagógico:
-- En 'InfraCienciaDatos' simulamos el sistema origen.
-- En 'bronze', 'silver' y 'gold' realizamos la refinación de los datos.
