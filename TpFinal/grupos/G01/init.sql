
-- INICIALIZACIÓN DEL DATA WAREHOUSE - G01 - Open-Meteo 

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;


-- CAPA BRONZE


CREATE TABLE IF NOT EXISTS bronze.open_meteo_raw (
    id           SERIAL PRIMARY KEY,
    id_provincia VARCHAR(50),
    payload      JSONB,
    ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source       VARCHAR(255) DEFAULT 'open-meteo'
);


-- CAPA SILVER


CREATE TABLE IF NOT EXISTS silver.clima_actual (
    id_provincia        VARCHAR(50),
    fecha_hora          TIMESTAMP,
    temperatura_c       NUMERIC(4,2),
    sensacion_termica_c NUMERIC(4,2),
    humedad_relativa    INT,
    lluvia_mm           NUMERIC(5,2),
    viento_kmh          NUMERIC(5,2),
    weather_code        INT,
    actualizado_at      TIMESTAMP,
    PRIMARY KEY (id_provincia, fecha_hora)
);

CREATE TABLE IF NOT EXISTS silver.clima_pronostico (
    id_provincia              VARCHAR(50),
    fecha_pronostico          DATE,
    snapshot_ts               TIMESTAMP,
    temp_max_c                NUMERIC(4,2),
    temp_min_c                NUMERIC(4,2),
    sensacion_max_c           NUMERIC(4,2),
    sensacion_min_c           NUMERIC(4,2),
    lluvia_acumulada_mm       NUMERIC(5,2),
    precipitacion_prob_pct    INT,
    viento_max_kmh            NUMERIC(5,2),
    weather_code              INT,
    calculado_at              TIMESTAMP,
    PRIMARY KEY (id_provincia, fecha_pronostico)
);


-- CAPA GOLD


CREATE TABLE IF NOT EXISTS gold.dim_provincia (
    id_provincia     VARCHAR(50) PRIMARY KEY,
    nombre_provincia VARCHAR(100),
    latitud          NUMERIC(8,5),
    longitud         NUMERIC(8,5)
);

CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    fecha            DATE PRIMARY KEY,
    anio             INT,
    mes              INT,
    dia              INT,
    dia_semana       VARCHAR(20),
    es_fin_de_semana BOOLEAN
);

CREATE TABLE IF NOT EXISTS gold.dim_weather_code (
    code        INT PRIMARY KEY,
    descripcion VARCHAR(100),
    categoria   VARCHAR(20),
    es_alerta   BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS gold.fact_clima_diario (
    id_fact         SERIAL PRIMARY KEY,
    id_provincia    VARCHAR(50) REFERENCES gold.dim_provincia(id_provincia),
    fecha           DATE        REFERENCES gold.dim_tiempo(fecha),
    temp_promedio_c NUMERIC(4,2),
    temp_max_real_c NUMERIC(4,2),
    temp_min_real_c NUMERIC(4,2),
    lluvia_total_mm NUMERIC(5,2),
    confort_termico VARCHAR(20),
    registro_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_provincia, fecha)
);

CREATE TABLE IF NOT EXISTS gold.fact_desvio_pronostico (
    id_desvio             SERIAL PRIMARY KEY,
    id_provincia          VARCHAR(50) REFERENCES gold.dim_provincia(id_provincia),
    fecha_evaluada        DATE        REFERENCES gold.dim_tiempo(fecha),
    temp_max_pronosticada NUMERIC(4,2),
    temp_max_real         NUMERIC(4,2),
    error_max_c           NUMERIC(4,2),
    lluvio_pronostico     BOOLEAN,
    lluvio_real           BOOLEAN,
    acierto_lluvia        BOOLEAN,
    registro_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);