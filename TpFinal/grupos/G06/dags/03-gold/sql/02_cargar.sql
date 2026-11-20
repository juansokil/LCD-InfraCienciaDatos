-- Dimensiones y hechos. Fuente: silver.clima_diario (contrato Silver).

-- dim_ciudad: 3 destinos. Coordenadas aproximadas del centro urbano.
INSERT INTO gold.dim_ciudad
    (ciudad_id, destino, nombre_completo, provincia, region, categoria_destino, latitud, longitud)
VALUES
    (1, 'Purmamarca', 'Purmamarca (Cerro de los Siete Colores)', 'Jujuy',     'Noroeste', 'Montaña', -23.7500, -65.5000),
    (2, 'Bariloche',  'San Carlos de Bariloche',                 'Río Negro', 'Patagonia', 'Montaña y lagos', -41.1335, -71.3103),
    (3,U&'Puerto Iguaz\00FA', U&'Puerto Iguaz\00FA (Cataratas)',            'Misiones',  'Noreste',   'Selva',           -25.5991, -54.5736)
ON CONFLICT (ciudad_id) DO UPDATE SET
    destino = EXCLUDED.destino, nombre_completo = EXCLUDED.nombre_completo,
    provincia = EXCLUDED.provincia, region = EXCLUDED.region,
    categoria_destino = EXCLUDED.categoria_destino,
    latitud = EXCLUDED.latitud, longitud = EXCLUDED.longitud;

-- dim_tiempo: todas las fechas entre el minimo y el maximo de Silver.
INSERT INTO gold.dim_tiempo
SELECT d::date,
       EXTRACT(YEAR    FROM d)::smallint,
       EXTRACT(MONTH   FROM d)::smallint,
       (ARRAY['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto',
              'Septiembre','Octubre','Noviembre','Diciembre'])[EXTRACT(MONTH FROM d)::int],
       EXTRACT(QUARTER FROM d)::smallint,
       CASE WHEN EXTRACT(MONTH FROM d) IN (12,1,2)  THEN 'Verano'
            WHEN EXTRACT(MONTH FROM d) IN (3,4,5)   THEN 'Otoño'
            WHEN EXTRACT(MONTH FROM d) IN (6,7,8)   THEN 'Invierno'
            ELSE 'Primavera' END,
       EXTRACT(ISODOW  FROM d)::smallint,
       EXTRACT(ISODOW  FROM d) IN (6,7)
FROM generate_series((SELECT min(fecha) FROM silver.clima_diario),
                     (SELECT max(fecha) FROM silver.clima_diario),
                     interval '1 day') AS d
ON CONFLICT (fecha) DO NOTHING;

-- fact: se recarga completa (son ~5.5 mil filas) para que sea idempotente.
TRUNCATE gold.fact_clima_diario;

INSERT INTO gold.fact_clima_diario(
    ciudad_id,
    fecha,
    temperatura_minima,
    temperatura_media,
    temperatura_maxima,
    precipitacion_mm,
    horas_luz,
    rafagas_viento_max_kmh,
    es_calor_extremo,
    es_frio_extremo,
    es_temp_extrema,
    es_dia_lluvioso,
    es_dia_agradable,
    estado_climatico
)
SELECT c.ciudad_id,
       s.fecha,
       s.temperatura_minima,
       s.temperatura_media,
       s.temperatura_maxima,
       s.precipitacion_mm,
       ROUND(s.duracion_luz_segundos / 3600.0, 2),
       s.rafagas_viento_max_kmh,
       -- Banderas: si falta un dato y no alcanza para decidir, queda NULL (desconocido).
       -- Si un dato conocido ya alcanza (ej. tmax = 40), la bandera es false aunque falte otro.
       s.temperatura_maxima >= u.calor,
       s.temperatura_minima <= u.frio,
       (s.temperatura_maxima >= u.calor OR s.temperatura_minima <= u.frio),
       s.precipitacion_mm   >= u.lluvia,
       (s.temperatura_maxima BETWEEN u.ag_tmax_min AND u.ag_tmax_max
        AND s.temperatura_minima >= u.ag_tmin_min
        AND s.precipitacion_mm   <  u.lluvia
        AND s.rafagas_viento_max_kmh < u.ag_rafaga),


    CASE
        WHEN s.temperatura_maxima >= u.calor OR s.temperatura_minima <=u.frio
            OR s.precipitacion_mm >= 10 OR s.rafagas_viento_max_kmh >= 70
        THEN 'DESFAVORABLE'

        WHEN s.temperatura_maxima IS NULL OR s.temperatura_minima IS NULL
          OR s.precipitacion_mm IS NULL OR s.rafagas_viento_max_kmh IS NULL
          OR u.calor IS NULL OR u.frio IS NULL
        THEN NULL

        WHEN (
            (c.destino = 'Bariloche'
                AND s.temperatura_maxima BETWEEN 10 AND 27
            )
            OR (c.destino = 'Purmamarca'
                AND s.temperatura_maxima BETWEEN 14 AND 30
            )
            OR (c.destino =  U&'Puerto Iguaz\00FA'
                AND s.temperatura_maxima BETWEEN 20 AND 34
            )
        )
        AND s.precipitacion_mm < 3
        AND s.rafagas_viento_max_kmh < 50
        THEN 'FAVORABLE'

        ELSE 'PRECAUCION'
    END
FROM silver.clima_diario s
JOIN gold.dim_ciudad c ON c.destino = s.destino
CROSS JOIN (
    SELECT
        max(valor) FILTER (WHERE nombre = 'temp_calor_extremo')   AS calor,
        max(valor) FILTER (WHERE nombre = 'temp_frio_extremo')    AS frio,
        max(valor) FILTER (WHERE nombre = 'lluvia_dia_mm')        AS lluvia,
        max(valor) FILTER (WHERE nombre = 'agradable_tmax_min')   AS ag_tmax_min,
        max(valor) FILTER (WHERE nombre = 'agradable_tmax_max')   AS ag_tmax_max,
        max(valor) FILTER (WHERE nombre = 'agradable_tmin_min')   AS ag_tmin_min,
        max(valor) FILTER (WHERE nombre = 'agradable_rafaga_max') AS ag_rafaga
    FROM gold.umbrales
) u;


-- Carga de datos meteorologicos horarios en Gold.
-- Fuente: silver.clima_horario.
-- Grano: una ciudad por hora.

INSERT INTO gold.fact_clima_horario (
    ciudad_id,
    fecha_hora,
    temperatura_2m,
    precipitacion_mm,
    rafagas_viento_kmh
)
SELECT
    c.ciudad_id,
    s.fecha_hora,
    s.temperatura_2m,
    s.precipitacion_mm,
    s.rafagas_viento_kmh
FROM silver.clima_horario s
JOIN gold.dim_ciudad c
    ON c.destino = s.destino

ON CONFLICT (ciudad_id, fecha_hora)
DO UPDATE SET
    temperatura_2m = EXCLUDED.temperatura_2m,
    precipitacion_mm = EXCLUDED.precipitacion_mm,
    rafagas_viento_kmh = EXCLUDED.rafagas_viento_kmh;