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
),
resumen_horario AS (
    SELECT
        COUNT(*) AS total_registros_horarios,
        COUNT(*) FILTER (
            WHERE destino IS NULL
        ) AS destinos_nulos_horarios,
        COUNT(*) FILTER (
            WHERE fecha_hora IS NULL
        ) AS fechas_nulas_horarias,
        COUNT(*) FILTER (
            WHERE temperatura_2m IS NULL
        ) AS temperaturas_nulas_horarias,
        COUNT(*) FILTER (
            WHERE precipitacion_mm IS NULL
        ) AS precipitaciones_nulas_horarias,
        COUNT(*) FILTER (
            WHERE rafagas_viento_kmh IS NULL
        ) AS rafagas_nulas_horarias
    FROM silver.clima_horario_limpio
),
duplicados_horarios AS (
    SELECT COUNT(*) AS grupos_duplicados_horarios
    FROM (
        SELECT destino, fecha_hora
        FROM silver.clima_horario_limpio
        GROUP BY destino, fecha_hora
        HAVING COUNT(*) > 1
    ) d
)
SELECT *
FROM resumen
CROSS JOIN duplicados
CROSS JOIN resumen_horario
CROSS JOIN duplicados_horarios;