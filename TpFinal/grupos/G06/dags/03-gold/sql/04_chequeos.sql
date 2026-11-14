-- Chequeos de calidad de Gold: cada fila devuelta es un problema.
SELECT 'fact_sin_ciudad' AS chequeo, COUNT(*) AS n
FROM gold.fact_clima_diario f LEFT JOIN gold.dim_ciudad c USING (ciudad_id) WHERE c.ciudad_id IS NULL
UNION ALL
SELECT 'fact_sin_fecha', COUNT(*)
FROM gold.fact_clima_diario f LEFT JOIN gold.dim_tiempo t USING (fecha) WHERE t.fecha IS NULL
UNION ALL
SELECT 'silver_destino_sin_dim_ciudad', COUNT(*)
FROM silver.clima_diario s LEFT JOIN gold.dim_ciudad c ON c.destino = s.destino WHERE c.ciudad_id IS NULL
UNION ALL
SELECT 'filas_silver_vs_fact', ABS((SELECT COUNT(*) FROM silver.clima_diario) - (SELECT COUNT(*) FROM gold.fact_clima_diario));
