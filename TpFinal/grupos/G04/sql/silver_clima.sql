-- BLOQUE: quarantine
-- La cuarentena se inserta junto con cada transformación, en la misma sentencia SQL.
-- Requiere índice único lógico en quarantine, acordado con I5 (ver NOTAS_INTEGRACION.md).

-- BLOQUE: clima_actual
WITH extraido AS (
    SELECT b.consulta_id, b.ciudad_id, b.ciudad_nombre, b.latitud, b.longitud,
           b.ingested_at, b.payload->'current' AS original,
           b.payload->'current'->>'time' AS fecha_txt,
           b.payload->'current'->>'temperature_2m' AS temp_txt,
           b.payload->'current'->>'relative_humidity_2m' AS hum_txt,
           b.payload->'current'->>'apparent_temperature' AS sens_txt,
           b.payload->'current'->>'wind_speed_10m' AS viento_txt
    FROM bronze.clima_raw b
),
convertido AS (
    SELECT *,
           CASE WHEN fecha_txt ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$'
                     AND pg_input_is_valid(fecha_txt, 'timestamp without time zone')
                THEN fecha_txt::timestamp END AS fecha,
           CASE WHEN temp_txt ~ '^-?[0-9]{1,3}(\.[0-9]{1,6})?$' THEN temp_txt::numeric END AS temp,
           CASE WHEN hum_txt ~ '^[0-9]{1,3}(\.[0-9]{1,6})?$' THEN hum_txt::numeric END AS humedad,
           CASE WHEN sens_txt ~ '^-?[0-9]{1,3}(\.[0-9]{1,6})?$' THEN sens_txt::numeric END AS sensacion,
           CASE WHEN viento_txt ~ '^[0-9]{1,3}(\.[0-9]{1,6})?$' THEN viento_txt::numeric END AS viento
    FROM extraido
),
validado AS (
    SELECT *,
      concat_ws('; ',
        CASE WHEN ciudad_id NOT IN ('buenos_aires','cordoba','mendoza','bariloche','salta') OR ciudad_id IS NULL THEN 'Ciudad no autorizada' END,
        CASE WHEN jsonb_typeof(original) IS DISTINCT FROM 'object' THEN 'Seccion current invalida' END,
        CASE WHEN fecha IS NULL THEN 'Fecha invalida' END,
        CASE WHEN temp NOT BETWEEN current_setting('silver.temperature_min_c')::numeric AND current_setting('silver.temperature_max_c')::numeric OR temp IS NULL THEN 'Temperatura invalida' END,
        CASE WHEN humedad NOT BETWEEN current_setting('silver.humidity_min_pct')::numeric AND current_setting('silver.humidity_max_pct')::numeric OR humedad IS NULL THEN 'Humedad invalida' END,
        CASE WHEN sens_txt IS NOT NULL AND (sensacion NOT BETWEEN current_setting('silver.temperature_min_c')::numeric AND current_setting('silver.temperature_max_c')::numeric OR sensacion IS NULL) THEN 'Sensacion termica invalida' END,
        CASE WHEN viento_txt IS NOT NULL AND (viento NOT BETWEEN current_setting('silver.wind_min_kmh')::numeric AND current_setting('silver.wind_max_kmh')::numeric OR viento IS NULL) THEN 'Viento invalido' END
      ) AS motivo
    FROM convertido
),
validos AS (
    INSERT INTO silver.clima_actual
      (consulta_id, ciudad_id, ciudad_nombre, latitud, longitud, instante_local, temperatura_c,
       humedad_pct, sensacion_termica_c, viento_kmh, ingested_at)
    SELECT consulta_id, ciudad_id, ciudad_nombre, latitud, longitud, fecha, temp::numeric(6,2),
           humedad::numeric(5,2), sensacion::numeric(6,2), viento::numeric(7,2), ingested_at
    FROM validado WHERE motivo = ''
    ON CONFLICT (consulta_id) DO NOTHING RETURNING consulta_id
),
rechazados AS (
    INSERT INTO silver.clima_quarantine
      (consulta_id, ciudad_id, tipo_registro, fecha_pronostico, motivo, raw_record)
    SELECT consulta_id, ciudad_id, 'actual', NULL, motivo, COALESCE(original, '{}'::jsonb)
    FROM validado WHERE motivo <> ''
    ON CONFLICT DO NOTHING RETURNING quarantine_id
)
SELECT (SELECT count(*) FROM validos) AS actuales_insertados,
       (SELECT count(*) FROM rechazados) AS actuales_rechazados;

-- BLOQUE: pronostico_diario
WITH arrays AS (
    SELECT b.consulta_id, b.ciudad_id, b.ingested_at,
      CASE WHEN jsonb_typeof(b.payload->'daily'->'time') = 'array' THEN b.payload->'daily'->'time' ELSE '[]'::jsonb END AS fechas,
      CASE WHEN jsonb_typeof(b.payload->'daily'->'temperature_2m_max') = 'array' THEN b.payload->'daily'->'temperature_2m_max' ELSE '[]'::jsonb END AS maxs,
      CASE WHEN jsonb_typeof(b.payload->'daily'->'temperature_2m_min') = 'array' THEN b.payload->'daily'->'temperature_2m_min' ELSE '[]'::jsonb END AS mins,
      CASE WHEN jsonb_typeof(b.payload->'daily'->'apparent_temperature_max') = 'array' THEN b.payload->'daily'->'apparent_temperature_max' ELSE '[]'::jsonb END AS sens,
      CASE WHEN jsonb_typeof(b.payload->'daily'->'precipitation_sum') = 'array' THEN b.payload->'daily'->'precipitation_sum' ELSE '[]'::jsonb END AS lluvias,
      CASE WHEN jsonb_typeof(b.payload->'daily'->'wind_speed_10m_max') = 'array' THEN b.payload->'daily'->'wind_speed_10m_max' ELSE '[]'::jsonb END AS vientos
    FROM bronze.clima_raw b
),
filas AS (
    SELECT a.consulta_id, a.ciudad_id, a.ingested_at, i.n,
      a.fechas->>i.n AS fecha_txt, a.maxs->>i.n AS max_txt, a.mins->>i.n AS min_txt,
      a.sens->>i.n AS sens_txt, a.lluvias->>i.n AS lluvia_txt, a.vientos->>i.n AS viento_txt,
      jsonb_build_object('time', a.fechas->i.n, 'temperature_2m_max', a.maxs->i.n,
       'temperature_2m_min', a.mins->i.n, 'apparent_temperature_max', a.sens->i.n,
       'precipitation_sum', a.lluvias->i.n, 'wind_speed_10m_max', a.vientos->i.n) AS raw_record
    FROM arrays a
    CROSS JOIN LATERAL generate_series(0, greatest(jsonb_array_length(a.fechas),
      jsonb_array_length(a.maxs), jsonb_array_length(a.mins), jsonb_array_length(a.sens),
      jsonb_array_length(a.lluvias), jsonb_array_length(a.vientos)) - 1) AS i(n)
),
convertido AS (
    SELECT *,
      CASE WHEN fecha_txt ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND pg_input_is_valid(fecha_txt, 'date') THEN fecha_txt::date END AS fecha,
      CASE WHEN max_txt ~ '^-?[0-9]{1,3}(\.[0-9]{1,6})?$' THEN max_txt::numeric END AS maxima,
      CASE WHEN min_txt ~ '^-?[0-9]{1,3}(\.[0-9]{1,6})?$' THEN min_txt::numeric END AS minima,
      CASE WHEN sens_txt ~ '^-?[0-9]{1,3}(\.[0-9]{1,6})?$' THEN sens_txt::numeric END AS sensacion,
      CASE WHEN lluvia_txt ~ '^[0-9]{1,4}(\.[0-9]{1,6})?$' THEN lluvia_txt::numeric END AS lluvia,
      CASE WHEN viento_txt ~ '^[0-9]{1,3}(\.[0-9]{1,6})?$' THEN viento_txt::numeric END AS viento
    FROM filas
),
validado AS (
    SELECT *, concat_ws('; ',
      CASE WHEN ciudad_id NOT IN ('buenos_aires','cordoba','mendoza','bariloche','salta') OR ciudad_id IS NULL THEN 'Ciudad no autorizada' END,
      CASE WHEN fecha IS NULL THEN 'Fecha invalida' END,
      CASE WHEN maxima NOT BETWEEN current_setting('silver.temperature_min_c')::numeric AND current_setting('silver.temperature_max_c')::numeric OR maxima IS NULL THEN 'Temperatura maxima invalida' END,
      CASE WHEN minima NOT BETWEEN current_setting('silver.temperature_min_c')::numeric AND current_setting('silver.temperature_max_c')::numeric OR minima IS NULL THEN 'Temperatura minima invalida' END,
      CASE WHEN current_setting('silver.require_min_not_above_max')::boolean AND minima > maxima THEN 'Minima mayor que maxima' END,
      CASE WHEN lluvia NOT BETWEEN current_setting('silver.precipitation_min_mm')::numeric AND current_setting('silver.precipitation_max_mm')::numeric OR lluvia IS NULL THEN 'Precipitacion invalida' END,
      CASE WHEN sens_txt IS NOT NULL AND (sensacion NOT BETWEEN current_setting('silver.temperature_min_c')::numeric AND current_setting('silver.temperature_max_c')::numeric OR sensacion IS NULL) THEN 'Sensacion termica invalida' END,
      CASE WHEN viento_txt IS NOT NULL AND (viento NOT BETWEEN current_setting('silver.wind_min_kmh')::numeric AND current_setting('silver.wind_max_kmh')::numeric OR viento IS NULL) THEN 'Viento invalido' END
    ) AS motivo FROM convertido
),
validos AS (
    INSERT INTO silver.pronostico_diario
      (consulta_id, ciudad_id, fecha_pronostico, temp_max_c, temp_min_c,
       sensacion_termica_max_c, precipitacion_mm, viento_max_kmh, ingested_at)
    SELECT consulta_id, ciudad_id, fecha, maxima::numeric(6,2), minima::numeric(6,2),
           sensacion::numeric(6,2), lluvia::numeric(8,2), viento::numeric(7,2), ingested_at
    FROM validado WHERE motivo = ''
    ON CONFLICT (consulta_id, fecha_pronostico) DO NOTHING RETURNING consulta_id
),
rechazados AS (
    INSERT INTO silver.clima_quarantine
      (consulta_id, ciudad_id, tipo_registro, fecha_pronostico, motivo, raw_record)
    SELECT consulta_id, ciudad_id, 'diario', fecha, motivo, raw_record
    FROM validado WHERE motivo <> ''
    ON CONFLICT DO NOTHING RETURNING quarantine_id
)
SELECT (SELECT count(*) FROM validos) AS diarios_insertados,
       (SELECT count(*) FROM rechazados) AS diarios_rechazados;
