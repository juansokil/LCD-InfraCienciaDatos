-- Dimensiones y hechos. Fuente: silver.clima_diario (contrato Silver).

-- dim_ciudad: 3 destinos. Coordenadas aproximadas del centro urbano.
INSERT INTO gold.dim_ciudad
    (ciudad_id, destino, nombre_completo, provincia, region, categoria_destino, latitud, longitud)
VALUES
    (1, 'Purmamarca', 'Purmamarca (Cerro de los Siete Colores)', 'Jujuy',     'Noroeste', 'Montaña', -23.7500, -65.5000),
    (2, 'Bariloche',  'San Carlos de Bariloche',                 'Río Negro', 'Patagonia', 'Montaña y lagos', -41.1335, -71.3103),
    (3, 'Puerto Iguazú', 'Puerto Iguazú (Cataratas)',            'Misiones',  'Noreste',   'Selva',           -25.5991, -54.5736)
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

INSERT INTO gold.fact_clima_diario
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
        AND s.rafagas_viento_max_kmh < u.ag_rafaga)
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
