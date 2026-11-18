-- Vista que responde la pregunta principal: ¿en que mes conviene viajar a cada destino?
-- Se recrea (DROP) porque cambia el conjunto de columnas respecto de versiones anteriores.
-- Los porcentajes se calculan solo sobre los dias con dato: AVG ignora los NULL.
DROP VIEW IF EXISTS gold.v_mejor_epoca;
CREATE VIEW gold.v_mejor_epoca AS
WITH mensual AS (
    SELECT c.destino,
           c.categoria_destino,
           t.mes,
           t.nombre_mes,
           COUNT(f.estado_climatico)                         AS dias_observados,
           COUNT(*) - COUNT(f.estado_climatico)              AS dias_sin_dato,
           ROUND(100.0 * COUNT(*) FILTER (WHERE f.estado_climatico = 'FAVORABLE')
                 / NULLIF(COUNT(f.estado_climatico), 0), 1)  AS pct_dias_favorables,
           ROUND(100.0 * COUNT(*) FILTER (WHERE f.estado_climatico = 'PRECAUCION')
                 / NULLIF(COUNT(f.estado_climatico), 0), 1)  AS pct_dias_precaucion,
           ROUND(100.0 * COUNT(*) FILTER (WHERE f.estado_climatico = 'DESFAVORABLE')
                 / NULLIF(COUNT(f.estado_climatico), 0), 1)  AS pct_dias_desfavorables,
           ROUND(100.0 * AVG(f.es_dia_agradable::int), 1)    AS pct_dias_agradables,
           ROUND(100.0 * AVG(f.es_dia_lluvioso::int), 1)     AS pct_dias_lluviosos,
           ROUND(AVG(f.temperatura_media), 1)                AS temp_media,
           ROUND(AVG(f.temperatura_maxima), 1)               AS temp_max_promedio,
           ROUND(AVG(f.temperatura_minima), 1)               AS temp_min_promedio,
           ROUND(SUM(f.precipitacion_mm) / NULLIF(COUNT(DISTINCT t.anio), 0), 1) AS lluvia_mm_por_mes,
           ROUND(AVG(f.rafagas_viento_max_kmh), 1)           AS rafaga_promedio_kmh,
           ROUND(AVG(f.horas_luz), 1)                        AS horas_luz_promedio,
           SUM(f.es_temp_extrema::int)                       AS dias_temp_extrema
    FROM gold.fact_clima_diario f
    JOIN gold.dim_ciudad c ON c.ciudad_id = f.ciudad_id
    JOIN gold.dim_tiempo t ON t.fecha     = f.fecha
    GROUP BY c.destino, c.categoria_destino, t.mes, t.nombre_mes
)
SELECT m.*,
       RANK() OVER (PARTITION BY destino
                    ORDER BY pct_dias_favorables DESC NULLS LAST,
                             pct_dias_desfavorables ASC NULLS LAST) AS ranking_en_destino
FROM mensual m;

-- Alertas de temperatura extrema (para el dashboard): una fila por dia extremo.
CREATE OR REPLACE VIEW gold.v_alertas_temperatura AS
SELECT c.destino, f.fecha, f.temperatura_minima, f.temperatura_maxima,
       CASE WHEN f.es_calor_extremo THEN 'Calor extremo' ELSE 'Frío extremo' END AS tipo_alerta
FROM gold.fact_clima_diario f
JOIN gold.dim_ciudad c ON c.ciudad_id = f.ciudad_id
WHERE f.es_temp_extrema;

-- Historial de lluvia mensual por destino y año.
CREATE OR REPLACE VIEW gold.v_lluvia_mensual AS
SELECT c.destino, t.anio, t.mes, t.nombre_mes,
       ROUND(SUM(f.precipitacion_mm), 1)       AS lluvia_mm,
       SUM(f.es_dia_lluvioso::int)             AS dias_con_lluvia
FROM gold.fact_clima_diario f
JOIN gold.dim_ciudad c ON c.ciudad_id = f.ciudad_id
JOIN gold.dim_tiempo t ON t.fecha     = f.fecha
GROUP BY c.destino, t.anio, t.mes, t.nombre_mes;


-- Vista de datos meteorologicos horarios.
-- Permite consultar las condiciones de cada destino por hora.

CREATE OR REPLACE VIEW gold.v_clima_horario AS
SELECT
    c.destino,
    c.provincia,
    c.region,
    f.fecha_hora,
    f.temperatura_2m,
    f.precipitacion_mm,
    f.rafagas_viento_kmh
FROM gold.fact_clima_horario f
JOIN gold.dim_ciudad c
    ON c.ciudad_id = f.ciudad_id;