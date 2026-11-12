    INSERT INTO gold.dim_fecha (fecha_id, fecha, anio, mes, nombre_mes, dia, dia_semana)
    SELECT DISTINCT
        CAST(TO_CHAR(fecha_utc, 'YYYYMMDD') AS INT) AS fecha_id,
        DATE(fecha_utc) AS fecha,
        EXTRACT(YEAR FROM fecha_utc) AS anio,
        EXTRACT(MONTH FROM fecha_utc) AS mes,
        TO_CHAR(fecha_utc, 'TMMonth') AS nombre_mes,
        EXTRACT(DAY FROM fecha_utc) AS dia,
        TO_CHAR(fecha_utc, 'TMDay') AS dia_semana
    FROM silver.sismos
    ON CONFLICT (fecha_id) DO NOTHING;

    INSERT INTO gold.dim_region (nombre_region)
    SELECT DISTINCT COALESCE(lugar, 'Desconocido') AS nombre_region
    FROM silver.sismos
    ON CONFLICT (nombre_region) DO NOTHING;

    INSERT INTO gold.fact_sismos (sismo_id, fecha_id, region_id, magnitud, profundidad_km, cantidad)
    SELECT
        s.event_id AS sismo_id,
        f.fecha_id,
        r.region_id,
        s.magnitud,
        s.profundidad_km,
        1 AS cantidad
    FROM silver.sismos s
    JOIN gold.dim_fecha f ON DATE(s.fecha_utc) = f.fecha
    JOIN gold.dim_region r ON COALESCE(s.lugar, 'Desconocido') = r.nombre_region
    ON CONFLICT (sismo_id) DO UPDATE SET
        magnitud = EXCLUDED.magnitud,
        profundidad_km = EXCLUDED.profundidad_km,
        fecha_id = EXCLUDED.fecha_id,
        region_id = EXCLUDED.region_id;