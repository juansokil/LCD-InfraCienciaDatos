-- Vista que responde la pregunta principal: ¿en que mes conviene viajar a cada destino?
CREATE OR REPLACE VIEW gold.v_mejor_epoca AS
WITH mensual AS (
    SELECT c.destino,
           c.categoria_destino,
           t.mes,
           t.nombre_mes,
           COUNT(*)                                          AS dias_observados,
           ROUND(100.0 * AVG(f.es_dia_agradable::int), 1)    AS pct_dias_agradables,
           ROUND(100.0 * AVG(f.es_dia_lluvioso::int), 1)     AS pct_dias_lluviosos,
           ROUND(AVG(f.temperatura_media), 1)                AS temp_media,
           ROUND(AVG(f.temperatura_maxima), 1)               AS temp_max_promedio,
           ROUND(AVG(f.temperatura_minima), 1)               AS temp_min_promedio,
           ROUND(SUM(f.precipitacion_mm) / COUNT(DISTINCT t.anio), 1) AS lluvia_mm_por_mes,
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
                    ORDER BY pct_dias_agradables DESC, pct_dias_lluviosos ASC) AS ranking_en_destino
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
