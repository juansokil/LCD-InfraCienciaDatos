"""
DAG usgs_silver - Capa Silver: un sismo = una fila, limpia y validada.

    bronze.usgs_sismos  --(SQL)-->  silver.sismos             (validos)
                                    silver.sismos_cuarentena  (invalidos + motivo)
                                    silver.calidad_corridas   (una fila por corrida)

Arranca solo cuando Bronze publica el asset BRONZE_SISMOS.

DECISIONES
----------
1. ULTIMA VERSION DE CADA EVENTO. En Bronze un mismo sismo aparece muchas
   veces: cada corrida vuelve a bajar las ultimas 24 h, y USGS lo va
   corrigiendo (estado automatic -> reviewed, magnitud ajustada). Silver se
   queda con la version de `updated_ms` mas reciente:
       SELECT DISTINCT ON (event_id) ... ORDER BY event_id, updated_ms DESC
2. IDEMPOTENTE. Se carga con un UPSERT:
       INSERT ... ON CONFLICT (event_id) DO UPDATE ... WHERE la version es mas nueva
   Correr Silver 1 o 10 veces sobre el mismo Bronze deja exactamente lo mismo.
3. TODO EN SQL, adentro de Postgres. Python solo manda las sentencias.
4. CUARENTENA = DATO ROTO, no "dato que no me interesa". Coordenadas
   imposibles, profundidad absurda, magnitud fuera de escala o sin fecha van a
   cuarentena con el motivo. Las voladuras de cantera o explosiones NO son
   errores: son eventos reales y quedan en Silver, marcados con es_sismo=false.
   Gold decide que hacer con ellos.
5. ENRIQUECIMIENTO: tipos correctos (epoch ms -> timestamptz), region a partir
   del texto de `place`, y una macrozona geografica por coordenadas.
6. Todo en UNA transaccion: el dashboard nunca ve Silver a medio escribir.
"""

import sys
from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_SISMOS, SILVER_SISMOS  # noqa: E402
from common.db import transaccion  # noqa: E402

DDL_SILVER = """
CREATE TABLE IF NOT EXISTS silver.sismos (
    event_id        TEXT PRIMARY KEY,
    ocurrido_at     TIMESTAMPTZ NOT NULL,
    actualizado_at  TIMESTAMPTZ NOT NULL,
    magnitud        NUMERIC(4,2) NOT NULL,
    tipo_magnitud   TEXT,
    profundidad_km  NUMERIC(7,2) NOT NULL,
    latitud         NUMERIC(8,4) NOT NULL,
    longitud        NUMERIC(9,4) NOT NULL,
    lugar           TEXT,
    region          TEXT NOT NULL,
    macrozona       TEXT NOT NULL,
    tipo_evento     TEXT NOT NULL,
    es_sismo        BOOLEAN NOT NULL,
    estado          TEXT,
    alerta          TEXT,
    tsunami         BOOLEAN NOT NULL,
    significancia   INTEGER,
    sentido_por     INTEGER,
    red             TEXT,
    url             TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL,
    procesado_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS silver.sismos_cuarentena (
    event_id      TEXT,
    motivo        TEXT NOT NULL,
    mag           DOUBLE PRECISION,
    place         TEXT,
    time_ms       BIGINT,
    latitude      DOUBLE PRECISION,
    longitude     DOUBLE PRECISION,
    depth         DOUBLE PRECISION,
    event_type    TEXT,
    archivo_raw   TEXT,
    ingested_at   TIMESTAMPTZ,
    detectado_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS silver.calidad_corridas (
    corrida_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    filas_bronze      INTEGER,
    eventos_distintos INTEGER,
    insertados        INTEGER,   -- sismos nuevos
    corregidos_usgs   INTEGER,   -- ya conocidos, con version nueva de USGS
    actualizados      INTEGER,   -- filas pisadas (corregidos + cambios de regla)
    en_cuarentena     INTEGER,
    total_silver      INTEGER
);
"""

# -----------------------------------------------------------------------------
# Paso 1: la ULTIMA version de cada evento, tipada y con el motivo de rechazo
# -----------------------------------------------------------------------------
SQL_CANDIDATOS = """
CREATE TEMP TABLE candidatos ON COMMIT DROP AS
WITH ultima AS (
    SELECT DISTINCT ON (event_id) b.*
    FROM bronze.usgs_sismos b
    WHERE event_id IS NOT NULL
    ORDER BY event_id, updated_ms DESC NULLS LAST, ingested_at DESC
),
tipada AS (
    SELECT
        u.*,
        NULLIF(btrim(place), '') AS lugar_limpio,
        -- Region: lo que viene despues de la ultima coma de `place`
        --   "19 km ESE of Joseph, Oregon"  -> "Oregon"
        -- y si no hay coma, el texto sin el "N km DIR of":
        --   "south of the Fiji Islands"    -> "south of the Fiji Islands"
        btrim(regexp_replace(
            CASE WHEN position(',' IN coalesce(place, '')) > 0
                 THEN regexp_replace(place, '^.*,', '')
                 ELSE regexp_replace(coalesce(place, ''),
                                     '^[0-9.]+ ?km [NSEW]{1,3} of ', '', 'i')
            END,
            ' region$', '', 'i')) AS region_texto
    FROM ultima u
)
SELECT
    event_id,
    to_timestamp(time_ms / 1000.0)                  AS ocurrido_at,
    to_timestamp(coalesce(updated_ms, time_ms) / 1000.0) AS actualizado_at,
    round(mag::numeric, 2)                          AS magnitud,
    lower(NULLIF(btrim(mag_type), ''))              AS tipo_magnitud,
    round(depth::numeric, 2)                        AS profundidad_km,
    round(latitude::numeric, 4)                     AS latitud,
    round(longitude::numeric, 4)                    AS longitud,
    lugar_limpio                                    AS lugar,
    -- USGS abrevia algunos lugares: los expandimos
    CASE region_texto
        WHEN 'CA' THEN 'California'
        WHEN 'MX' THEN 'Mexico'
        WHEN ''   THEN 'Sin dato'
        ELSE region_texto
    END                                             AS region,
    -- Macrozona por coordenadas: cajas aproximadas, se evaluan en orden
    CASE
        -- (el recorte "lat > 5 y lon < -77.2" deja a Panama fuera de Sudamerica)
        WHEN latitude BETWEEN -60 AND 13 AND longitude BETWEEN -82 AND -34
             AND NOT (latitude > 5 AND longitude < -77.2)
            THEN 'Sudamerica'
        WHEN latitude BETWEEN 5 AND 23.5 AND longitude BETWEEN -118 AND -59
            THEN 'Centroamerica y Caribe'
        WHEN latitude BETWEEN 15 AND 30 AND longitude BETWEEN -162 AND -150
            THEN 'Pacifico (Hawaii)'
        WHEN latitude BETWEEN 23.5 AND 85
             AND (longitude BETWEEN -170 AND -50 OR longitude BETWEEN -180 AND -170)
            THEN 'Norteamerica'
        WHEN latitude BETWEEN 35 AND 72 AND longitude BETWEEN -25 AND 45
            THEN 'Europa'
        WHEN (latitude BETWEEN -36 AND 37 AND longitude BETWEEN -20 AND 35)
          OR (latitude BETWEEN -36 AND 12 AND longitude BETWEEN 35 AND 52)
            THEN 'Africa'
        WHEN (latitude BETWEEN -50 AND -10 AND longitude BETWEEN 110 AND 180)
          OR (latitude BETWEEN -50 AND 0 AND longitude BETWEEN 141 AND 180)
          OR (latitude BETWEEN -50 AND 0 AND longitude BETWEEN -180 AND -165)
            THEN 'Oceania'
        WHEN latitude BETWEEN -11 AND 80 AND longitude BETWEEN 25 AND 180
            THEN 'Asia'
        ELSE 'Oceanos y otras'
    END                                             AS macrozona,
    coalesce(lower(NULLIF(btrim(event_type), '')), 'desconocido') AS tipo_evento,
    coalesce(lower(btrim(event_type)) = 'earthquake', false)     AS es_sismo,
    lower(NULLIF(btrim(status), ''))                AS estado,
    lower(NULLIF(btrim(alert), ''))                 AS alerta,
    coalesce(tsunami, 0) = 1                        AS tsunami,
    sig                                             AS significancia,
    felt                                            AS sentido_por,
    lower(net)                                      AS red,
    url,
    ingested_at,
    -- columnas crudas para la cuarentena
    mag, place, time_ms, latitude, longitude, depth, event_type, archivo_raw,
    -- MOTIVO: todas las reglas que falla, separadas por "; " (NULL = valido)
    NULLIF(concat_ws('; ',
        CASE WHEN time_ms IS NULL THEN 'sin fecha'
             WHEN time_ms > (extract(epoch FROM now()) + 3600) * 1000
                 THEN 'fecha en el futuro' END,
        CASE WHEN latitude IS NULL OR longitude IS NULL THEN 'sin coordenadas'
             WHEN latitude NOT BETWEEN -90 AND 90
               OR longitude NOT BETWEEN -180 AND 180
                 THEN 'coordenadas fuera de rango' END,
        CASE WHEN depth IS NULL THEN 'sin profundidad'
             WHEN depth NOT BETWEEN -10 AND 800
                 THEN 'profundidad fuera de rango (-10 a 800 km)' END,
        CASE WHEN mag IS NULL THEN 'sin magnitud'
             WHEN mag NOT BETWEEN -2 AND 10
                 THEN 'magnitud fuera de rango (-2 a 10)' END
    ), '')                                          AS motivo
FROM tipada;
"""

# -----------------------------------------------------------------------------
# Paso 2: UPSERT de los validos (solo pisa si la version que llega es mas nueva)
# -----------------------------------------------------------------------------
SQL_UPSERT = """
INSERT INTO silver.sismos AS s (
    event_id, ocurrido_at, actualizado_at, magnitud, tipo_magnitud,
    profundidad_km, latitud, longitud, lugar, region, macrozona, tipo_evento,
    es_sismo, estado, alerta, tsunami, significancia, sentido_por, red, url,
    ingested_at, procesado_at)
SELECT
    event_id, ocurrido_at, actualizado_at, magnitud, tipo_magnitud,
    profundidad_km, latitud, longitud, lugar, region, macrozona, tipo_evento,
    es_sismo, estado, alerta, tsunami, significancia, sentido_por, red, url,
    ingested_at, now()
FROM candidatos
WHERE motivo IS NULL
ON CONFLICT (event_id) DO UPDATE SET
    ocurrido_at = EXCLUDED.ocurrido_at,
    actualizado_at = EXCLUDED.actualizado_at,
    magnitud = EXCLUDED.magnitud,
    tipo_magnitud = EXCLUDED.tipo_magnitud,
    profundidad_km = EXCLUDED.profundidad_km,
    latitud = EXCLUDED.latitud,
    longitud = EXCLUDED.longitud,
    lugar = EXCLUDED.lugar,
    region = EXCLUDED.region,
    macrozona = EXCLUDED.macrozona,
    tipo_evento = EXCLUDED.tipo_evento,
    es_sismo = EXCLUDED.es_sismo,
    estado = EXCLUDED.estado,
    alerta = EXCLUDED.alerta,
    tsunami = EXCLUDED.tsunami,
    significancia = EXCLUDED.significancia,
    sentido_por = EXCLUDED.sentido_por,
    red = EXCLUDED.red,
    url = EXCLUDED.url,
    ingested_at = EXCLUDED.ingested_at,
    procesado_at = now()
-- Solo se pisa una fila si cambio algo:
--   a) USGS publico una version mas nueva del sismo, o
--   b) cambiamos NOSOTROS una regla de enriquecimiento (region, macrozona):
--      sin esta condicion, arreglar una regla no corregiria los sismos viejos.
WHERE s.actualizado_at < EXCLUDED.actualizado_at
   OR (s.region, s.macrozona, s.tipo_evento, s.es_sismo)
      IS DISTINCT FROM
      (EXCLUDED.region, EXCLUDED.macrozona, EXCLUDED.tipo_evento, EXCLUDED.es_sismo)
RETURNING (xmax = 0) AS insertado;   -- truco de Postgres: xmax=0 -> fila nueva
"""

# Cuantos sismos ya conocidos llegaron con una version corregida por USGS
# (se mide ANTES del upsert, comparando contra lo que habia en Silver)
SQL_CORREGIDOS = """
SELECT count(*)
FROM candidatos c
JOIN silver.sismos s USING (event_id)
WHERE c.motivo IS NULL AND c.actualizado_at > s.actualizado_at;
"""

# Si la ultima version de un evento quedo invalida, sale de Silver
SQL_SACAR_INVALIDOS = """
DELETE FROM silver.sismos s
USING candidatos c
WHERE s.event_id = c.event_id AND c.motivo IS NOT NULL;
"""

# La cuarentena refleja el estado ACTUAL de Bronze: se reconstruye entera
SQL_CUARENTENA = """
TRUNCATE silver.sismos_cuarentena;
INSERT INTO silver.sismos_cuarentena
    (event_id, motivo, mag, place, time_ms, latitude, longitude, depth,
     event_type, archivo_raw, ingested_at)
SELECT event_id, motivo, mag, place, time_ms, latitude, longitude, depth,
       event_type, archivo_raw, ingested_at
FROM candidatos
WHERE motivo IS NOT NULL
UNION ALL
SELECT event_id, 'sin event_id', mag, place, time_ms, latitude, longitude,
       depth, event_type, archivo_raw, ingested_at
FROM bronze.usgs_sismos
WHERE event_id IS NULL;
"""


@dag(
    dag_id="usgs_silver",
    schedule=[BRONZE_SISMOS],
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["g11", "silver", "usgs"],
    doc_md=__doc__,
)
def usgs_silver():

    @task(outlets=[SILVER_SISMOS])
    def transformar_silver() -> dict:
        """Bronze -> Silver en una sola transaccion (o todo, o nada)."""
        with transaccion() as cur:
            cur.execute(DDL_SILVER)
            cur.execute(SQL_CANDIDATOS)
            cur.execute("SELECT count(*), count(*) FILTER (WHERE motivo IS NOT NULL) FROM candidatos")
            distintos, invalidos = cur.fetchone()

            cur.execute(SQL_CORREGIDOS)
            corregidos = cur.fetchone()[0]

            cur.execute(SQL_UPSERT)
            marcas = [r[0] for r in cur.fetchall()]
            insertados = sum(marcas)
            actualizados = len(marcas) - insertados   # corregidos + regla nueva

            cur.execute(SQL_SACAR_INVALIDOS)
            cur.execute(SQL_CUARENTENA)

            cur.execute("SELECT count(*) FROM bronze.usgs_sismos")
            filas_bronze = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM silver.sismos")
            total_silver = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM silver.sismos_cuarentena")
            en_cuarentena = cur.fetchone()[0]

            cur.execute(
                """INSERT INTO silver.calidad_corridas
                   (filas_bronze, eventos_distintos, insertados, corregidos_usgs,
                    actualizados, en_cuarentena, total_silver)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (filas_bronze, distintos, insertados, corregidos, actualizados,
                 en_cuarentena, total_silver),
            )

        resumen = {
            "filas_bronze": filas_bronze, "eventos_distintos": distintos,
            "insertados": insertados, "corregidos_usgs": corregidos,
            "actualizados": actualizados,
            "invalidos": invalidos, "en_cuarentena": en_cuarentena,
            "total_silver": total_silver,
        }
        print("Resumen Silver:", resumen)
        return resumen

    transformar_silver()


usgs_silver()
