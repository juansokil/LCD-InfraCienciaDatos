-- Carga de datos para la capa Silver
-- Se insertan los registros limpios en la tabla definitiva.
-- Si ya existe el mismo destino y fecha, se actualizan sus valores.

INSERT INTO silver.clima_diario (
    destino,
    fecha,
    temperatura_minima,
    temperatura_media,
    temperatura_maxima,
    precipitacion_mm,
    duracion_luz_segundos,
    rafagas_viento_max_kmh
)
SELECT
    destino,
    fecha,
    temperatura_minima,
    temperatura_media,
    temperatura_maxima,
    precipitacion_mm,
    duracion_luz_segundos,
    rafagas_viento_max_kmh
FROM silver.clima_limpio
WHERE destino IS NOT NULL
  AND fecha IS NOT NULL

ON CONFLICT (destino, fecha)
DO UPDATE SET
    temperatura_minima = EXCLUDED.temperatura_minima,
    temperatura_media = EXCLUDED.temperatura_media,
    temperatura_maxima = EXCLUDED.temperatura_maxima,
    precipitacion_mm = EXCLUDED.precipitacion_mm,
    duracion_luz_segundos = EXCLUDED.duracion_luz_segundos,
    rafagas_viento_max_kmh = EXCLUDED.rafagas_viento_max_kmh;

