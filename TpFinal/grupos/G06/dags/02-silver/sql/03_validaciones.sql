-- Validaciones de los datos para la capa Silver.
-- Se controlan los registros obtenidos luego de la limpieza.

WITH resumen AS (
    SELECT
        COUNT(*) AS total_registros,
        COUNT(*) FILTER (WHERE destino IS NULL) AS destinos_nulos,
        COUNT(*) FILTER (WHERE fecha IS NULL) AS fechas_nulas,
        COUNT(*) FILTER (
            WHERE temperatura_minima IS NULL
               OR temperatura_media IS NULL
               OR temperatura_maxima IS NULL
        ) AS temperaturas_nulas,
        COUNT(*) FILTER (WHERE precipitacion_mm IS NULL) AS precipitaciones_nulas,
        COUNT(*) FILTER (WHERE duracion_luz_segundos IS NULL) AS duracion_luz_nula,
        COUNT(*) FILTER (WHERE rafagas_viento_max_kmh IS NULL) AS rafagas_nulas
    FROM silver.clima_limpio
),
duplicados AS (
    SELECT COUNT(*) AS grupos_duplicados
    FROM (
        SELECT destino, fecha
        FROM silver.clima_limpio
        GROUP BY destino, fecha
        HAVING COUNT(*) > 1
    ) d
)
SELECT *
FROM resumen
CROSS JOIN duplicados;