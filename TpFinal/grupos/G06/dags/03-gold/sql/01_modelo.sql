-- Gold: modelo estrella (grano de fact_clima_diario = una ciudad en un dia)
-- Idempotente: se puede correr N veces.

-- Umbrales de negocio en una tabla, para poder ajustarlos sin tocar el codigo.
CREATE TABLE IF NOT EXISTS gold.umbrales (
    nombre TEXT PRIMARY KEY,
    valor  NUMERIC NOT NULL,
    descripcion TEXT
);
INSERT INTO gold.umbrales (nombre, valor, descripcion) VALUES
    ('temp_calor_extremo',   35, 'tmax >= este valor (°C) => calor extremo'),
    ('temp_frio_extremo',    -5, 'tmin <= este valor (°C) => frio extremo'),
    ('lluvia_dia_mm',         1, 'precipitacion >= este valor (mm) => dia lluvioso'),
    ('agradable_tmax_min',   12, 'dia agradable: tmax >= este valor (°C)'),
    ('agradable_tmax_max',   34, 'dia agradable: tmax <= este valor (°C)'),
    ('agradable_tmin_min',    2, 'dia agradable: tmin >= este valor (°C)'),
    ('agradable_rafaga_max', 75, 'dia agradable: rafaga maxima < este valor (km/h)')
ON CONFLICT (nombre) DO NOTHING;

CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
    ciudad_id         SMALLINT PRIMARY KEY,
    destino           TEXT NOT NULL UNIQUE,   -- clave natural: coincide con silver.clima_diario.destino
    nombre_completo   TEXT NOT NULL,
    provincia         TEXT NOT NULL,
    region            TEXT NOT NULL,
    categoria_destino TEXT NOT NULL,
    latitud           NUMERIC(8,4) NOT NULL,
    longitud          NUMERIC(8,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    fecha       DATE PRIMARY KEY,
    anio        SMALLINT NOT NULL,
    mes         SMALLINT NOT NULL,
    nombre_mes  TEXT NOT NULL,
    trimestre   SMALLINT NOT NULL,
    estacion    TEXT NOT NULL,                -- hemisferio sur
    dia_semana  SMALLINT NOT NULL,            -- 1=lunes ... 7=domingo
    es_fin_de_semana BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.fact_clima_diario (
    ciudad_id              SMALLINT NOT NULL REFERENCES gold.dim_ciudad (ciudad_id),
    fecha                  DATE     NOT NULL REFERENCES gold.dim_tiempo (fecha),
    temperatura_minima     NUMERIC(5,2),
    temperatura_media      NUMERIC(5,2),
    temperatura_maxima     NUMERIC(5,2),
    precipitacion_mm       NUMERIC(7,2),
    horas_luz              NUMERIC(5,2),
    rafagas_viento_max_kmh NUMERIC(6,2),
    -- Banderas: true / false / NULL. NULL = no se pudo determinar por falta de datos;
    -- esos dias NO cuentan en los porcentajes de las vistas.
    es_calor_extremo       BOOLEAN,
    es_frio_extremo        BOOLEAN,
    es_temp_extrema        BOOLEAN,            -- alimenta las alertas del dashboard
    es_dia_lluvioso        BOOLEAN,
    es_dia_agradable       BOOLEAN,
    PRIMARY KEY (ciudad_id, fecha)
);

-- Si la tabla ya existia con las banderas NOT NULL (versiones anteriores), se las saca.
-- Es inofensivo si ya eran nullable.
ALTER TABLE gold.fact_clima_diario ALTER COLUMN es_calor_extremo DROP NOT NULL;
ALTER TABLE gold.fact_clima_diario ALTER COLUMN es_frio_extremo  DROP NOT NULL;
ALTER TABLE gold.fact_clima_diario ALTER COLUMN es_temp_extrema  DROP NOT NULL;
ALTER TABLE gold.fact_clima_diario ALTER COLUMN es_dia_lluvioso  DROP NOT NULL;
ALTER TABLE gold.fact_clima_diario ALTER COLUMN es_dia_agradable DROP NOT NULL;
