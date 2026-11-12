CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.dim_fecha (
    fecha_id INT PRIMARY KEY,
    fecha DATE NOT NULL UNIQUE,
    anio INT NOT NULL,
    mes INT NOT NULL,
    nombre_mes VARCHAR(20) NOT NULL,
    dia INT NOT NULL,
    dia_semana VARCHAR(20) NOT NULL
);
CREATE TABLE IF NOT EXISTS gold.dim_fecha (
    fecha_id INT PRIMARY KEY,
    fecha DATE NOT NULL UNIQUE,
    anio INT NOT NULL,
    mes INT NOT NULL,
    nombre_mes VARCHAR(20) NOT NULL,
    dia INT NOT NULL,
    dia_semana VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_region (
    region_id SERIAL PRIMARY KEY,
    nombre_region VARCHAR(255) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS gold.dim_region (
    region_id SERIAL PRIMARY KEY,
    nombre_region VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS gold.fact_sismos (
    sismo_id VARCHAR(100) PRIMARY KEY,
    fecha_id INT NOT NULL REFERENCES gold.dim_fecha(fecha_id),
    region_id INT NOT NULL REFERENCES gold.dim_region(region_id),
    magnitud NUMERIC(4,2),
    profundidad_km NUMERIC(8,2),
    latitud NUMERIC(9,6),
    longitud NUMERIC(9,6),
    es_tsunami SMALLINT NOT NULL DEFAULT 0,
    cantidad INT NOT NULL DEFAULT 1,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);