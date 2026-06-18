CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- a. Dimensión Estaciones
CREATE TABLE IF NOT EXISTS gold.dim_station (
    station_id VARCHAR(50) PRIMARY KEY,
    station_name VARCHAR(255) NOT NULL,
    address TEXT,
    total_capacity INT NOT NULL,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL
);

-- b. Dimensión Tiempo
CREATE TABLE IF NOT EXISTS gold.dim_time (
    time_id BIGINT PRIMARY KEY,
    full_timestamp TIMESTAMP WITH TIME ZONE UNIQUE NOT NULL,
    hour INT NOT NULL,
    minute INT NOT NULL,
    day_of_week VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- c. Tabla de Hechos (La estrella central)
CREATE TABLE IF NOT EXISTS gold.fact_station_availability (
    fact_key SERIAL PRIMARY KEY,
    time_id BIGINT NOT NULL REFERENCES gold.dim_time(time_id),
    station_id VARCHAR(50) NOT NULL REFERENCES gold.dim_station(station_id),
    bikes_available INT NOT NULL,
    slots_available INT NOT NULL,
    occupancy_ratio FLOAT NOT NULL,
    CONSTRAINT unique_snapshot_station UNIQUE (time_id, station_id)
);