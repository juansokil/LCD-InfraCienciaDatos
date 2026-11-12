-- =====================================================================
-- CAPA GOLD: VISTAS ANALÍTICAS PARA EL DASHBOARD
-- =====================================================================

-- 1. Vista: Último pronóstico disponible por ciudad y día de pronóstico
-- Utiliza ROW_NUMBER() particionando por ciudad y fecha para asegurar 
-- que siempre tomemos la predicción más reciente (basada en la fecha de consulta).
CREATE OR REPLACE VIEW gold.v_ultimo_pronostico AS
WITH pronosticos_ordenados AS (
    SELECT 
        f.consulta_id,
        f.ciudad_id,
        c.nombre AS ciudad_nombre,
        c.latitud,
        c.longitud,
        t.fecha AS fecha_pronostico,
        f.fecha_consulta_utc,
        f.temp_max_c,
        f.temp_min_c,
        f.sensacion_termica_max_c,
        f.precipitacion_mm,
        f.viento_max_kmh,
        ROW_NUMBER() OVER (
            PARTITION BY f.ciudad_id, t.fecha 
            RELATED ORDER BY f.fecha_consulta_utc DESC
        ) AS rn
    FROM gold.fact_clima_diario f
    JOIN gold.dim_ciudad c ON f.ciudad_id = c.ciudad_id
    JOIN gold.dim_tiempo t ON f.fecha_id = t.fecha_id
)
SELECT 
    consulta_id,
    ciudad_id,
    ciudad_nombre,
    latitud,
    longitud,
    fecha_pronostico,
    fecha_consulta_utc,
    temp_max_c,
    temp_min_c,
    sensacion_termica_max_c,
    precipitacion_mm,
    viento_max_kmh
FROM pronosticos_ordenados
WHERE rn = 1;


-- 2. Vista: Comparación de ciudades y alertas de clima extremo
-- Facilita métricas analíticas listas para graficar en el dashboard de Streamlit,
-- calculando amplitud térmica y disparando banderas de alerta.
CREATE OR REPLACE VIEW gold.v_comparacion_ciudades AS
SELECT 
    ciudad_id,
    ciudad_nombre,
    fecha_pronostico,
    temp_max_c,
    temp_min_c,
    (temp_max_c - temp_min_c) AS amplitud_termica_c,
    sensacion_termica_max_c,
    precipitacion_mm,
    viento_max_kmh,
    -- Indicadores de alerta lógica para el dashboard
    CASE 
        WHEN temp_max_c >= 35.0 THEN 'ALERTA: Calor Extremo'
        WHEN temp_min_c <= 0.0 THEN 'ALERTA: Helada'
        ELSE 'Normal'
    END AS alerta_temperatura,
    CASE 
        WHEN precipitacion_mm >= 20.0 THEN 'ALERTA: Lluvias Intensas'
        ELSE 'Normal'
    END AS alerta_precipitacion
FROM gold.v_ultimo_pronostico;