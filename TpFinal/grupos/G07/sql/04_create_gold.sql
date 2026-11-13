CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.dim_fecha (
    fecha_id    INT PRIMARY KEY,
    fecha       DATE NOT NULL UNIQUE,
    anio        INT NOT NULL,
    mes         INT NOT NULL,
    nombre_mes  VARCHAR(20) NOT NULL,
    dia         INT NOT NULL,
    dia_semana  VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_ubicacion (
    ubicacion_id   SERIAL PRIMARY KEY,
    latitud        DOUBLE PRECISION NOT NULL,
    longitud       DOUBLE PRECISION NOT NULL,
    nombre_region  VARCHAR(255) NOT NULL,
    UNIQUE (latitud, longitud, nombre_region)
);

CREATE TABLE IF NOT EXISTS gold.fact_sismos (
    sismo_id       VARCHAR(100) PRIMARY KEY,
    fecha_id       INT NOT NULL REFERENCES gold.dim_fecha(fecha_id),
    ubicacion_id   INT NOT NULL REFERENCES gold.dim_ubicacion(ubicacion_id),
    magnitud       NUMERIC(4,2),
    profundidad_km NUMERIC(8,2),
    es_tsunami     SMALLINT NOT NULL DEFAULT 0,
    cantidad       INT NOT NULL DEFAULT 1,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE OR REPLACE VIEW gold.v_sismos_dashboard AS
SELECT 
    f.sismo_id,
    f.magnitud,
    f.profundidad_km,
    u.latitud,
    u.longitud,
    u.nombre_region,
    f.es_tsunami,
    f.cantidad,
    d.fecha,
    d.anio,
    d.mes,
    d.nombre_mes,
    d.dia_semana
FROM gold.fact_sismos f
JOIN gold.dim_fecha d ON d.fecha_id = f.fecha_id
JOIN gold.dim_ubicacion u ON u.ubicacion_id = f.ubicacion_id;