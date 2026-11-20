
-- Limpieza de datos (Silver).
-- Se extraen los datos diarios del JSON almacenado en Bronze.
-- Se normalizan valores y se eliminan duplicados por destino y fecha.

DROP TABLE IF EXISTS silver.clima_limpio;

CREATE TABLE silver.clima_limpio AS

WITH datos_extraidos AS (
    SELECT
    b.id AS bronze_id,
    b.ingested_at,
    b.source AS origen,
    b.destino,
        (t.fecha)::DATE AS fecha,
        (t.temperatura_minima)::DECIMAL AS temperatura_minima,
        (t.temperatura_media)::DECIMAL AS temperatura_media,
        (t.temperatura_maxima)::DECIMAL AS temperatura_maxima,
        (t.precipitacion_mm)::DECIMAL AS precipitacion_mm,
        (t.duracion_luz_segundos)::DECIMAL AS duracion_luz_segundos,
        (t.rafagas_viento_max_kmh)::DECIMAL AS rafagas_viento_max_kmh
    FROM bronze.openmeteo b
    CROSS JOIN LATERAL (
        SELECT
            fechas.valor AS fecha,
            minimas.valor AS temperatura_minima,
            medias.valor AS temperatura_media,
            maximas.valor AS temperatura_maxima,
            precipitaciones.valor AS precipitacion_mm,
            luz.valor AS duracion_luz_segundos,
            rafagas.valor AS rafagas_viento_max_kmh
        FROM jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'time')
            WITH ORDINALITY AS fechas(valor, posicion)
        LEFT JOIN jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'temperature_2m_min')
            WITH ORDINALITY AS minimas(valor, posicion) USING (posicion)
        LEFT JOIN jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'temperature_2m_mean')
            WITH ORDINALITY AS medias(valor, posicion) USING (posicion)
        LEFT JOIN jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'temperature_2m_max')
            WITH ORDINALITY AS maximas(valor, posicion) USING (posicion)
        LEFT JOIN jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'precipitation_sum')
            WITH ORDINALITY AS precipitaciones(valor, posicion) USING (posicion)
        LEFT JOIN jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'daylight_duration')
            WITH ORDINALITY AS luz(valor, posicion) USING (posicion)
        LEFT JOIN jsonb_array_elements_text(b.respuesta_json -> 'daily' -> 'wind_gusts_10m_max')
            WITH ORDINALITY AS rafagas(valor, posicion) USING (posicion)
    ) t
),
datos_limpios AS (
    SELECT
        bronze_id,
        ingested_at,
        origen,
        destino,
        fecha,
        CASE
            WHEN temperatura_minima <= temperatura_media
             AND temperatura_media <= temperatura_maxima
            THEN temperatura_minima
            ELSE NULL
        END AS temperatura_minima,
        CASE
            WHEN temperatura_minima <= temperatura_media
             AND temperatura_media <= temperatura_maxima
            THEN temperatura_media
            ELSE NULL
        END AS temperatura_media,
        CASE
            WHEN temperatura_minima <= temperatura_media
             AND temperatura_media <= temperatura_maxima
            THEN temperatura_maxima
            ELSE NULL
        END AS temperatura_maxima,
        CASE WHEN precipitacion_mm >= 0
             THEN precipitacion_mm ELSE NULL END AS precipitacion_mm,
        CASE WHEN duracion_luz_segundos BETWEEN 0 AND 86400
             THEN duracion_luz_segundos ELSE NULL END AS duracion_luz_segundos,
        CASE WHEN rafagas_viento_max_kmh >= 0
             THEN rafagas_viento_max_kmh ELSE NULL END AS rafagas_viento_max_kmh
    FROM datos_extraidos
),
datos_priorizados AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY destino, fecha
            ORDER BY
                CASE
                    WHEN origen = 'https://archive-api.open-meteo.com/v1/archive'
                        THEN 1
                    WHEN origen = 'https://api.open-meteo.com/v1/forecast'
                        THEN 2
                    ELSE 3
                END ASC,
                (
                    (temperatura_minima IS NOT NULL)::int +
                    (temperatura_media IS NOT NULL)::int +
                    (temperatura_maxima IS NOT NULL)::int +
                    (precipitacion_mm IS NOT NULL)::int +
                    (duracion_luz_segundos IS NOT NULL)::int +
                    (rafagas_viento_max_kmh IS NOT NULL)::int
                ) DESC,
                ingested_at DESC,
                bronze_id DESC
        ) AS numero_fila
    FROM datos_limpios
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
FROM datos_priorizados
WHERE numero_fila = 1;

-- Limpieza de datos meteorologicos horarios.
-- Se validan los registros de Bronze y se eliminan duplicados
-- por destino y fecha_hora.

DROP TABLE IF EXISTS silver.clima_horario_limpio;

CREATE TABLE silver.clima_horario_limpio AS

WITH datos_validados AS (
    SELECT
        destino,
        fecha_hora,
        CASE
            WHEN temperatura_2m BETWEEN -90 AND 60
            THEN temperatura_2m
            ELSE NULL
        END AS temperatura_2m,

        CASE
            WHEN precipitacion >= 0
            THEN precipitacion
            ELSE NULL
        END AS precipitacion_mm,

        CASE
            WHEN rafaga_viento_10m >= 0
            THEN rafaga_viento_10m
            ELSE NULL
        END AS rafagas_viento_kmh,

        ingested_at,
        id
    FROM bronze.clima_horario
),
datos_priorizados AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY destino, fecha_hora
            ORDER BY ingested_at DESC, id DESC
        ) AS numero_fila
    FROM datos_validados
)

SELECT
    destino,
    fecha_hora,
    temperatura_2m,
    precipitacion_mm,
    rafagas_viento_kmh
FROM datos_priorizados
WHERE numero_fila = 1;