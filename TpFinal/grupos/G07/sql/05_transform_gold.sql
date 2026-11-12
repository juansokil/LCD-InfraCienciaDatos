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

INSERT INTO gold.dim_ubicacion (latitud, longitud, nombre_region)
SELECT DISTINCT
    s.latitud,
    s.longitud,
    COALESCE(
        NULLIF(TRIM(REGEXP_REPLACE(s.lugar, '^.*,\s*', '')), ''),
        'Desconocido'
    ) AS nombre_region
FROM silver.sismos s
WHERE s.latitud IS NOT NULL AND s.longitud IS NOT NULL
ON CONFLICT (latitud, longitud, nombre_region) DO NOTHING;

INSERT INTO gold.fact_sismos (
    sismo_id, fecha_id, ubicacion_id, magnitud, profundidad_km, es_tsunami, cantidad
)
SELECT
    s.event_id,
    TO_CHAR(s.fecha_utc, 'YYYYMMDD')::INT,
    u.ubicacion_id,
    s.magnitud,
    s.profundidad_km,
    COALESCE(s.es_tsunami, 0),
    1
FROM silver.sismos s
LEFT JOIN gold.dim_ubicacion u
    ON u.latitud = s.latitud
    AND u.longitud = s.longitud
    AND u.nombre_region = COALESCE(NULLIF(TRIM(REGEXP_REPLACE(s.lugar, '^.*,\s*', '')), ''), 'Desconocido')
WHERE s.event_id IS NOT NULL
ON CONFLICT (sismo_id) DO UPDATE SET
    fecha_id       = EXCLUDED.fecha_id,
    ubicacion_id   = EXCLUDED.ubicacion_id,
    magnitud       = EXCLUDED.magnitud,
    profundidad_km = EXCLUDED.profundidad_km,
    es_tsunami     = EXCLUDED.es_tsunami,
    actualizado_en = CURRENT_TIMESTAMP;