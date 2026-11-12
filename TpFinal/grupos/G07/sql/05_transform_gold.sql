-- 1. Calendario completo: cubre rango de Silver ± 7 días
INSERT INTO gold.dim_fecha (fecha_id, fecha, anio, mes, nombre_mes, dia, dia_semana)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT,
    d::date,
    EXTRACT(YEAR  FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    TO_CHAR(d, 'TMMonth'),
    EXTRACT(DAY   FROM d)::INT,
    TO_CHAR(d, 'TMDay')
FROM generate_series(
    (SELECT DATE(MIN(fecha_utc)) - INTERVAL '7 days' FROM silver.sismos),
    (SELECT DATE(MAX(fecha_utc)) + INTERVAL '1 day'  FROM silver.sismos),
    '1 day'::interval
) AS d
ON CONFLICT (fecha_id) DO NOTHING;

-- 2. Región: último segmento del "place"
INSERT INTO gold.dim_region (nombre_region)
SELECT DISTINCT
    COALESCE(
        NULLIF(TRIM(REGEXP_REPLACE(lugar, '^.*,\s*', '')), ''),
        'Desconocido'
    ) AS nombre_region
FROM silver.sismos
WHERE lugar IS NOT NULL
ON CONFLICT (nombre_region) DO NOTHING;

-- 3. Fact (LEFT JOIN y ON CONFLICT)
INSERT INTO gold.fact_sismos (
    sismo_id, fecha_id, region_id, magnitud, profundidad_km,
    latitud, longitud, es_tsunami, cantidad
)
SELECT
    s.event_id,
    TO_CHAR(s.fecha_utc, 'YYYYMMDD')::INT,
    r.region_id,
    s.magnitud,
    s.profundidad_km,
    s.latitud,
    s.longitud,
    COALESCE(s.es_tsunami, 0),
    1
FROM silver.sismos s
LEFT JOIN gold.dim_region r
    ON r.nombre_region = COALESCE(
        NULLIF(TRIM(REGEXP_REPLACE(s.lugar, '^.*,\s*', '')), ''),
        'Desconocido'
    )
WHERE s.event_id IS NOT NULL
ON CONFLICT (sismo_id) DO UPDATE SET
    fecha_id       = EXCLUDED.fecha_id,
    region_id      = EXCLUDED.region_id,
    magnitud       = EXCLUDED.magnitud,
    profundidad_km = EXCLUDED.profundidad_km,
    latitud        = EXCLUDED.latitud,
    longitud       = EXCLUDED.longitud,
    es_tsunami     = EXCLUDED.es_tsunami,
    actualizado_en = CURRENT_TIMESTAMP;