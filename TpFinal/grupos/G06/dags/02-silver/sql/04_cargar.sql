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


-- Carga de datos meteorologicos horarios en Silver.
-- Se insertan los registros limpios provenientes de Bronze.
-- Si ya existe el destino y la hora, se actualizan sus valores.

INSERT INTO silver.clima_horario (
    destino,
    fecha_hora,
    temperatura_2m,
    precipitacion_mm,
    rafagas_viento_kmh
)
SELECT
    destino,
    fecha_hora,
    temperatura_2m,
    precipitacion_mm,
    rafagas_viento_kmh
FROM silver.clima_horario_limpio
WHERE destino IS NOT NULL
  AND fecha_hora IS NOT NULL

ON CONFLICT (destino, fecha_hora)
DO UPDATE SET
    temperatura_2m = EXCLUDED.temperatura_2m,
    precipitacion_mm = EXCLUDED.precipitacion_mm,
    rafagas_viento_kmh = EXCLUDED.rafagas_viento_kmh;