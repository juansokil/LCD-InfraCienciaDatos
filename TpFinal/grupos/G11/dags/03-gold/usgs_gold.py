"""
DAG usgs_gold - Capa Gold: modelo ESTRELLA + vistas para el dashboard.

Pregunta de negocio:
    Donde se concentra la actividad sismica, como evoluciona dia a dia y que
    tan fuertes y profundos son los sismos? Con foco en Sudamerica.

                         dim_tiempo
                              |
    dim_region ---- fact_sismo (1 fila = 1 evento) ---- dim_magnitud
                         |              |
               dim_tipo_evento    dim_profundidad

Arranca solo cuando Silver publica SILVER_SISMOS.

DECISIONES
----------
* Grano de la fact: UN EVENTO. Es el grano mas fino que tenemos; cualquier
  agregado (por dia, por region, por rango de magnitud) sale de ahi con un
  GROUP BY, sin perder informacion.
* dim_magnitud y dim_profundidad son dimensiones de RANGOS (escala
  descriptiva de magnitud; profundidad superficial/intermedia/profunda). La
  fact se une por rango: desde <= valor < hasta.
* Se reconstruye todo en cada corrida (DROP + CREATE TABLE AS). Son pocos
  miles de filas y asi Gold nunca "deriva" de Silver. Y como en Postgres el
  DDL es transaccional, todo va en UNA transaccion: mientras se reconstruye,
  el dashboard sigue viendo la version anterior completa, y si algo falla
  queda la anterior intacta.
* Capa semantica: el dashboard NO lee las tablas, lee vistas gold.v_*. Los
  KPIs se definen una sola vez, en SQL.
* Controles antes de publicar el asset: si la fact no cuadra con Silver o hay
  claves huerfanas, la tarea falla y el asset GOLD no se emite.
"""

import sys
from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task

sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_SISMOS, SILVER_SISMOS  # noqa: E402
from common.db import ejecutar, valor  # noqa: E402

# =============================================================================
# 1) TABLAS DEL MODELO ESTRELLA
# =============================================================================
SQL_ESTRELLA = """
DROP TABLE IF EXISTS gold.fact_sismo CASCADE;
DROP TABLE IF EXISTS gold.dim_tiempo CASCADE;
DROP TABLE IF EXISTS gold.dim_region CASCADE;
DROP TABLE IF EXISTS gold.dim_magnitud CASCADE;
DROP TABLE IF EXISTS gold.dim_profundidad CASCADE;
DROP TABLE IF EXISTS gold.dim_tipo_evento CASCADE;

-- ---------------------------------------------------------------- dim_tiempo
-- Un dia por fila, sin huecos: los dias sin sismos tambien existen.
CREATE TABLE gold.dim_tiempo AS
SELECT
    to_char(d, 'YYYYMMDD')::int              AS fecha_key,
    d::date                                  AS fecha,
    extract(year  FROM d)::int               AS anio,
    extract(month FROM d)::int               AS mes,
    (ARRAY['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
           'septiembre','octubre','noviembre','diciembre'])[extract(month FROM d)::int]
                                             AS nombre_mes,
    extract(day FROM d)::int                 AS dia,
    extract(isodow FROM d)::int              AS dia_semana,
    (ARRAY['lunes','martes','miercoles','jueves','viernes','sabado','domingo'])
        [extract(isodow FROM d)::int]        AS nombre_dia,
    extract(week FROM d)::int                AS semana_iso,
    extract(isodow FROM d) IN (6, 7)         AS es_fin_de_semana
FROM generate_series(
        (SELECT min(ocurrido_at AT TIME ZONE 'UTC')::date FROM silver.sismos),
        (SELECT max(ocurrido_at AT TIME ZONE 'UTC')::date FROM silver.sismos),
        interval '1 day') AS d;
ALTER TABLE gold.dim_tiempo ADD PRIMARY KEY (fecha_key);

-- -------------------------------------------------------------- dim_magnitud
CREATE TABLE gold.dim_magnitud AS
SELECT * FROM (VALUES
    (1, 'Micro',      'menor a 2',  -99::numeric,  2::numeric, 'No se siente'),
    (2, 'Menor',      '2 a 3.9',      2,  4, 'Se siente poco, sin danos'),
    (3, 'Ligero',     '4 a 4.9',      4,  5, 'Se siente, danos raros'),
    (4, 'Moderado',   '5 a 5.9',      5,  6, 'Danos en construcciones debiles'),
    (5, 'Fuerte',     '6 a 6.9',      6,  7, 'Danos en zonas pobladas'),
    (6, 'Mayor',      '7 a 7.9',      7,  8, 'Danos graves en areas extensas'),
    (7, 'Gran sismo', '8 o mas',      8, 99, 'Destruccion en cientos de km')
) AS t(magnitud_key, categoria, rango, desde, hasta, efecto_tipico);
ALTER TABLE gold.dim_magnitud ADD PRIMARY KEY (magnitud_key);

-- ----------------------------------------------------------- dim_profundidad
CREATE TABLE gold.dim_profundidad AS
SELECT * FROM (VALUES
    (1, 'Superficial', '0 a 70 km',    -99::numeric,   70::numeric),
    (2, 'Intermedio',  '70 a 300 km',   70,  300),
    (3, 'Profundo',    'mas de 300 km', 300, 9999)
) AS t(profundidad_key, categoria, rango, desde, hasta);
ALTER TABLE gold.dim_profundidad ADD PRIMARY KEY (profundidad_key);

-- ----------------------------------------------------------- dim_tipo_evento
CREATE TABLE gold.dim_tipo_evento AS
SELECT
    row_number() OVER (ORDER BY tipo_evento)::int AS tipo_evento_key,
    tipo_evento,
    CASE tipo_evento
        WHEN 'earthquake'   THEN 'Sismo'
        WHEN 'quarry blast' THEN 'Voladura de cantera'
        WHEN 'explosion'    THEN 'Explosion'
        WHEN 'ice quake'    THEN 'Sismo glaciar'
        WHEN 'landslide'    THEN 'Deslizamiento'
        WHEN 'other event'  THEN 'Otro evento'
        ELSE initcap(tipo_evento)
    END                                           AS nombre,
    bool_or(es_sismo)                             AS es_sismo
FROM silver.sismos
GROUP BY tipo_evento;
ALTER TABLE gold.dim_tipo_evento ADD PRIMARY KEY (tipo_evento_key);

-- ---------------------------------------------------------------- dim_region
-- La macrozona de una region es la mas frecuente entre sus eventos (mode()).
CREATE TABLE gold.dim_region AS
SELECT
    row_number() OVER (ORDER BY region)::int     AS region_key,
    region,
    CASE WHEN region IN (
        'Alabama','Alaska','Arizona','Arkansas','California','Colorado',
        'Connecticut','Delaware','Florida','Georgia','Hawaii','Idaho',
        'Illinois','Indiana','Iowa','Kansas','Kentucky','Louisiana','Maine',
        'Maryland','Massachusetts','Michigan','Minnesota','Mississippi',
        'Missouri','Montana','Nebraska','Nevada','New Hampshire','New Jersey',
        'New Mexico','New York','North Carolina','North Dakota','Ohio',
        'Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina',
        'South Dakota','Tennessee','Texas','Utah','Vermont','Virginia',
        'Washington','West Virginia','Wisconsin','Wyoming')
         THEN 'Estados Unidos'
         ELSE region
    END                                           AS pais,
    mode() WITHIN GROUP (ORDER BY macrozona)      AS macrozona
FROM silver.sismos
GROUP BY region;
ALTER TABLE gold.dim_region ADD PRIMARY KEY (region_key);

-- ---------------------------------------------------------------- fact_sismo
CREATE TABLE gold.fact_sismo AS
SELECT
    s.event_id,
    to_char(s.ocurrido_at AT TIME ZONE 'UTC', 'YYYYMMDD')::int AS fecha_key,
    r.region_key,
    m.magnitud_key,
    p.profundidad_key,
    t.tipo_evento_key,
    s.ocurrido_at,
    extract(hour FROM s.ocurrido_at AT TIME ZONE 'UTC')::int  AS hora_utc,
    s.magnitud,
    s.profundidad_km,
    s.latitud,
    s.longitud,
    s.significancia,
    s.sentido_por,
    s.tsunami,
    s.alerta,
    s.estado,
    s.lugar,
    s.url,
    s.actualizado_at
FROM silver.sismos s
JOIN gold.dim_region      r ON r.region = s.region
JOIN gold.dim_tipo_evento t ON t.tipo_evento = s.tipo_evento
JOIN gold.dim_magnitud    m ON s.magnitud >= m.desde AND s.magnitud < m.hasta
JOIN gold.dim_profundidad p ON s.profundidad_km >= p.desde AND s.profundidad_km < p.hasta;

ALTER TABLE gold.fact_sismo
    ADD PRIMARY KEY (event_id),
    ADD FOREIGN KEY (fecha_key)       REFERENCES gold.dim_tiempo,
    ADD FOREIGN KEY (region_key)      REFERENCES gold.dim_region,
    ADD FOREIGN KEY (magnitud_key)    REFERENCES gold.dim_magnitud,
    ADD FOREIGN KEY (profundidad_key) REFERENCES gold.dim_profundidad,
    ADD FOREIGN KEY (tipo_evento_key) REFERENCES gold.dim_tipo_evento;
"""

# =============================================================================
# 2) CAPA SEMANTICA: las vistas que lee el dashboard
# =============================================================================
# Todas trabajan solo con SISMOS (es_sismo), salvo v_eventos_por_tipo.
SQL_VISTAS = """
-- Base "ancha": la fact con sus dimensiones ya unidas. Las demas vistas salen de aca.
CREATE VIEW gold.v_sismos AS
SELECT f.event_id, f.ocurrido_at, d.fecha, d.nombre_dia, f.hora_utc,
       f.magnitud, m.categoria AS categoria_magnitud, m.magnitud_key AS orden_magnitud,
       f.profundidad_km, p.categoria AS categoria_profundidad,
       f.latitud, f.longitud, f.lugar, r.region, r.pais, r.macrozona,
       f.tsunami, f.alerta, f.estado, f.significancia, f.sentido_por, f.url
FROM gold.fact_sismo f
JOIN gold.dim_tiempo      d USING (fecha_key)
JOIN gold.dim_region      r USING (region_key)
JOIN gold.dim_magnitud    m USING (magnitud_key)
JOIN gold.dim_profundidad p USING (profundidad_key)
JOIN gold.dim_tipo_evento t USING (tipo_evento_key)
WHERE t.es_sismo;

-- KPIs del encabezado (una sola fila)
CREATE VIEW gold.v_kpis AS
SELECT
    count(*)                                                    AS sismos_total,
    count(*) FILTER (WHERE ocurrido_at > now() - interval '24 hours') AS sismos_24h,
    count(*) FILTER (WHERE magnitud >= 4.5)                     AS sismos_m45,
    count(*) FILTER (WHERE magnitud >= 6)                       AS sismos_m6,
    max(magnitud)                                               AS magnitud_max,
    count(*) FILTER (WHERE tsunami)                             AS con_alerta_tsunami,
    count(*) FILTER (WHERE macrozona = 'Sudamerica')            AS sismos_sudamerica,
    min(fecha)                                                  AS desde,
    max(fecha)                                                  AS hasta,
    (SELECT max(actualizado_at) FROM gold.fact_sismo)           AS ultima_actualizacion_usgs
FROM gold.v_sismos;

-- El sismo mas fuerte del periodo (para destacar)
CREATE VIEW gold.v_sismo_mas_fuerte AS
SELECT * FROM gold.v_sismos ORDER BY magnitud DESC, ocurrido_at DESC LIMIT 1;

-- Serie diaria por categoria de magnitud
CREATE VIEW gold.v_sismos_diarios AS
SELECT fecha, categoria_magnitud, orden_magnitud,
       count(*) AS cantidad, max(magnitud) AS magnitud_max
FROM gold.v_sismos
GROUP BY fecha, categoria_magnitud, orden_magnitud;

-- Ranking de regiones
CREATE VIEW gold.v_actividad_por_region AS
SELECT region, pais, macrozona,
       count(*)                                  AS sismos,
       count(*) FILTER (WHERE magnitud >= 4.5)   AS sismos_m45,
       max(magnitud)                             AS magnitud_max,
       round(avg(magnitud), 2)                   AS magnitud_promedio,
       round(avg(profundidad_km), 1)             AS profundidad_promedio_km
FROM gold.v_sismos
GROUP BY region, pais, macrozona;

-- Resumen por macrozona
CREATE VIEW gold.v_actividad_por_macrozona AS
SELECT macrozona,
       count(*)                                  AS sismos,
       count(*) FILTER (WHERE magnitud >= 4.5)   AS sismos_m45,
       max(magnitud)                             AS magnitud_max,
       round(avg(profundidad_km), 1)             AS profundidad_promedio_km
FROM gold.v_sismos
GROUP BY macrozona;

-- Distribucion: magnitud x profundidad (cruce de dos dimensiones)
CREATE VIEW gold.v_magnitud_profundidad AS
SELECT categoria_magnitud, orden_magnitud, categoria_profundidad,
       count(*) AS cantidad
FROM gold.v_sismos
GROUP BY categoria_magnitud, orden_magnitud, categoria_profundidad;

-- Sudamerica, por pais
CREATE VIEW gold.v_sudamerica_por_pais AS
SELECT pais,
       count(*)                                  AS sismos,
       count(*) FILTER (WHERE magnitud >= 4.5)   AS sismos_m45,
       max(magnitud)                             AS magnitud_max,
       round(avg(profundidad_km), 1)             AS profundidad_promedio_km
FROM gold.v_sismos
WHERE macrozona = 'Sudamerica'
GROUP BY pais;

-- Todos los tipos de evento (sismos y no sismos)
CREATE VIEW gold.v_eventos_por_tipo AS
SELECT t.nombre AS tipo_evento, t.es_sismo, count(*) AS cantidad,
       round(avg(f.magnitud), 2) AS magnitud_promedio
FROM gold.fact_sismo f
JOIN gold.dim_tipo_evento t USING (tipo_evento_key)
GROUP BY t.nombre, t.es_sismo;
"""


@dag(
    dag_id="usgs_gold",
    schedule=[SILVER_SISMOS],
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["g11", "gold", "usgs"],
    doc_md=__doc__,
)
def usgs_gold():

    @task
    def construir_modelo() -> int:
        """Dimensiones + fact + vistas, en UNA transaccion."""
        ejecutar(SQL_ESTRELLA + SQL_VISTAS)
        filas = valor("SELECT count(*) FROM gold.fact_sismo")
        print(f"gold.fact_sismo: {filas} eventos")
        return filas

    @task(outlets=[GOLD_SISMOS])
    def verificar(filas_fact: int) -> None:
        """Controles de calidad de Gold. Si alguno falla, no se publica el asset."""
        filas_silver = valor("SELECT count(*) FROM silver.sismos")
        huerfanos = valor("""
            SELECT count(*) FROM gold.fact_sismo
            WHERE fecha_key IS NULL OR region_key IS NULL OR magnitud_key IS NULL
               OR profundidad_key IS NULL OR tipo_evento_key IS NULL""")
        filas_kpi = valor("SELECT count(*) FROM gold.v_kpis")

        problemas = []
        if filas_fact != filas_silver:
            problemas.append(f"la fact tiene {filas_fact} filas y Silver {filas_silver}: "
                             "algun evento no encontro su dimension")
        if huerfanos:
            problemas.append(f"{huerfanos} filas de la fact con claves nulas")
        if filas_kpi != 1:
            problemas.append("v_kpis no devolvio exactamente una fila")
        if problemas:
            raise ValueError("Controles de Gold fallaron: " + " | ".join(problemas))
        print(f"Controles OK: fact = silver = {filas_fact} eventos, sin huerfanos")

    verificar(construir_modelo())


usgs_gold()
