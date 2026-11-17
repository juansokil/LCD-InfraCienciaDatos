"""
DAG Gold G09: modelo estrella para el dashboard de clima.

  fact_clima_horario  (grano: una ciudad en una hora)
    -> dim_ciudad, dim_tiempo (calendario denso), dim_condicion (códigos WMO)
  + capa semántica: vistas gold.v_* (las métricas se definen UNA vez, acá)

Qué cambió respecto de la versión anterior y por qué:
  - Claves estables: dim_ciudad ya no se renumera con ROW_NUMBER() en cada corrida;
    se inserta solo lo nuevo (una SK real tiene que ser estable).
  - El hecho se actualiza incrementalmente (upsert por watermark), no con DROP.
  - verify_integrity() corre ANTES de publicar: si el modelo está roto, el DAG
    falla ahí, las vistas no se rehacen y no se emite el asset.
  - Las métricas agregadas viven en vistas, no en pandas dentro del dashboard.
"""

from datetime import datetime, timezone
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

SILVER_ASSET = Asset(
    name="g09_silver_open_meteo_clean",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/silver/clima_horario",
)
GOLD_ASSET = Asset(
    name="g09_gold_open_meteo_star",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/gold/fact_clima_horario",
)


def get_database_engine():
    return create_engine(
        URL.create(
            drivername="postgresql+psycopg2",
            username=os.environ.get("SOURCE_DB_USER", "admin"),
            password=os.environ.get("SOURCE_DB_PASS", "admin"),
            host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
            port=int(os.getenv("SOURCE_DB_PORT", "5432")),
            database=os.environ.get("SOURCE_DB_NAME", "InfraCienciaDatos"),
        ),
        pool_pre_ping=True,
    )


DIMS_SQL = """
CREATE SCHEMA IF NOT EXISTS gold;

-- Dimensión ciudad: clave sustituta ESTABLE (solo se insertan ciudades nuevas)
CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
    ciudad_id SERIAL PRIMARY KEY,
    ciudad    TEXT NOT NULL UNIQUE,
    region    TEXT NOT NULL
);
INSERT INTO gold.dim_ciudad (ciudad, region)
SELECT DISTINCT ciudad, region FROM silver.clima_horario
ON CONFLICT (ciudad) DO UPDATE SET region = EXCLUDED.region;

-- Dimensión tiempo DENSA: un día por fila, haya o no datos
CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    tiempo_id  DATE PRIMARY KEY,
    anio       INT NOT NULL,
    mes        INT NOT NULL,
    dia        INT NOT NULL,
    nombre_mes TEXT NOT NULL,
    dia_semana TEXT NOT NULL
);
INSERT INTO gold.dim_tiempo
SELECT d::date,
       EXTRACT(YEAR  FROM d)::int,
       EXTRACT(MONTH FROM d)::int,
       EXTRACT(DAY   FROM d)::int,
       TRIM(TO_CHAR(d, 'Month')),
       TRIM(TO_CHAR(d, 'Day'))
FROM generate_series(
    (SELECT MIN(fecha_hora)::date FROM silver.clima_horario),
    (SELECT MAX(fecha_hora)::date FROM silver.clima_horario),
    INTERVAL '1 day'
) AS d
ON CONFLICT (tiempo_id) DO NOTHING;

-- Dimensión condición: códigos WMO de Open-Meteo (la decisión de negocio vive acá)
CREATE TABLE IF NOT EXISTS gold.dim_condicion (
    condicion_id INT PRIMARY KEY,
    descripcion  TEXT NOT NULL,
    categoria    TEXT NOT NULL
);
INSERT INTO gold.dim_condicion (condicion_id, descripcion, categoria) VALUES
    (-1, 'Sin dato', 'Sin dato'),
    (0,  'Despejado', 'Despejado'),
    (1,  'Mayormente despejado', 'Despejado'),
    (2,  'Parcialmente nublado', 'Nublado'),
    (3,  'Nublado', 'Nublado'),
    (45, 'Niebla', 'Niebla'),
    (48, 'Niebla con escarcha', 'Niebla'),
    (51, 'Llovizna leve', 'Llovizna'),
    (53, 'Llovizna moderada', 'Llovizna'),
    (55, 'Llovizna intensa', 'Llovizna'),
    (56, 'Llovizna helada leve', 'Llovizna'),
    (57, 'Llovizna helada intensa', 'Llovizna'),
    (61, 'Lluvia leve', 'Lluvia'),
    (63, 'Lluvia moderada', 'Lluvia'),
    (65, 'Lluvia intensa', 'Lluvia'),
    (66, 'Lluvia helada leve', 'Lluvia'),
    (67, 'Lluvia helada intensa', 'Lluvia'),
    (71, 'Nevada leve', 'Nieve'),
    (73, 'Nevada moderada', 'Nieve'),
    (75, 'Nevada intensa', 'Nieve'),
    (77, 'Granizo fino', 'Nieve'),
    (80, 'Chubascos leves', 'Lluvia'),
    (81, 'Chubascos moderados', 'Lluvia'),
    (82, 'Chubascos violentos', 'Lluvia'),
    (85, 'Chubascos de nieve leves', 'Nieve'),
    (86, 'Chubascos de nieve intensos', 'Nieve'),
    (95, 'Tormenta', 'Tormenta'),
    (96, 'Tormenta con granizo leve', 'Tormenta'),
    (99, 'Tormenta con granizo fuerte', 'Tormenta')
ON CONFLICT (condicion_id) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    categoria   = EXCLUDED.categoria;
"""

FACT_SQL = """
CREATE TABLE IF NOT EXISTS gold.fact_clima_horario (
    ciudad_id          INT          NOT NULL REFERENCES gold.dim_ciudad (ciudad_id),
    tiempo_id          DATE         NOT NULL REFERENCES gold.dim_tiempo (tiempo_id),
    condicion_id       INT          NOT NULL REFERENCES gold.dim_condicion (condicion_id),
    fecha_hora         TIMESTAMP    NOT NULL,
    hora               SMALLINT     NOT NULL,
    temp_c             NUMERIC(5,2),
    sensacion_c        NUMERIC(5,2),
    humedad_pct        NUMERIC(5,2),
    lluvia_mm          NUMERIC(6,2),
    viento_kmh         NUMERIC(6,2),
    nubosidad_pct      NUMERIC(5,2),
    es_pronostico      BOOLEAN      NOT NULL,
    snapshot_ts        TIMESTAMPTZ  NOT NULL,
    _source_updated_at TIMESTAMPTZ  NOT NULL,
    _processed_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ciudad_id, fecha_hora)
);

-- Incremental: solo lo que Silver actualizó desde la última carga del hecho
INSERT INTO gold.fact_clima_horario (
    ciudad_id, tiempo_id, condicion_id, fecha_hora, hora,
    temp_c, sensacion_c, humedad_pct, lluvia_mm, viento_kmh, nubosidad_pct,
    es_pronostico, snapshot_ts, _source_updated_at
)
SELECT
    c.ciudad_id,
    s.fecha_hora::date,
    COALESCE(s.weather_code, -1),
    s.fecha_hora,
    EXTRACT(HOUR FROM s.fecha_hora)::smallint,
    s.temp_c, s.sensacion_c, s.humedad_pct, s.lluvia_mm, s.viento_kmh, s.nubosidad_pct,
    s.es_pronostico, s.source_snapshot_ts, s.silver_updated_at
FROM silver.clima_horario s
JOIN gold.dim_ciudad c ON c.ciudad = s.ciudad
WHERE s.silver_updated_at > COALESCE(
    (SELECT MAX(_source_updated_at) FROM gold.fact_clima_horario),
    '-infinity'::timestamptz
)
ON CONFLICT (ciudad_id, fecha_hora) DO UPDATE SET
    tiempo_id          = EXCLUDED.tiempo_id,
    condicion_id       = EXCLUDED.condicion_id,
    hora               = EXCLUDED.hora,
    temp_c             = EXCLUDED.temp_c,
    sensacion_c        = EXCLUDED.sensacion_c,
    humedad_pct        = EXCLUDED.humedad_pct,
    lluvia_mm          = EXCLUDED.lluvia_mm,
    viento_kmh         = EXCLUDED.viento_kmh,
    nubosidad_pct      = EXCLUDED.nubosidad_pct,
    es_pronostico      = EXCLUDED.es_pronostico,
    snapshot_ts        = EXCLUDED.snapshot_ts,
    _source_updated_at = EXCLUDED._source_updated_at,
    _processed_at      = NOW();
"""

VIEWS_SQL = """
DROP VIEW IF EXISTS gold.v_ultimo_estado CASCADE;
DROP VIEW IF EXISTS gold.v_clima_diario  CASCADE;
DROP VIEW IF EXISTS gold.v_clima_horario CASCADE;

-- Hecho + dimensiones ya unidos: la API pública de Gold para el consumo
CREATE VIEW gold.v_clima_horario AS
SELECT
    f.fecha_hora,
    f.tiempo_id AS fecha,
    f.hora,
    c.ciudad,
    c.region,
    f.temp_c,
    f.sensacion_c,
    f.humedad_pct,
    f.lluvia_mm,
    f.viento_kmh,
    f.nubosidad_pct,
    d.descripcion AS condicion,
    d.categoria   AS condicion_categoria,
    f.es_pronostico,
    f.snapshot_ts
FROM gold.fact_clima_horario f
JOIN gold.dim_ciudad    c ON c.ciudad_id    = f.ciudad_id
JOIN gold.dim_condicion d ON d.condicion_id = f.condicion_id;

-- Última medición (no pronóstico) de cada ciudad
CREATE VIEW gold.v_ultimo_estado AS
SELECT DISTINCT ON (ciudad)
    ciudad, region, fecha_hora, temp_c, sensacion_c, humedad_pct,
    lluvia_mm, viento_kmh, nubosidad_pct, condicion
FROM gold.v_clima_horario
WHERE NOT es_pronostico
ORDER BY ciudad, fecha_hora DESC;

-- KPIs diarios por ciudad: se definen una sola vez, acá
CREATE VIEW gold.v_clima_diario AS
SELECT
    ciudad,
    region,
    fecha,
    ROUND(AVG(temp_c), 1)        AS temp_media_c,
    MAX(temp_c)                  AS temp_max_c,
    MIN(temp_c)                  AS temp_min_c,
    ROUND(SUM(lluvia_mm), 1)     AS lluvia_mm,
    ROUND(AVG(viento_kmh), 1)    AS viento_medio_kmh,
    MAX(viento_kmh)              AS viento_max_kmh,
    COUNT(*) FILTER (WHERE NOT es_pronostico) AS horas_medidas,
    COUNT(*) FILTER (WHERE es_pronostico)     AS horas_pronostico,
    CASE
        WHEN COUNT(*) FILTER (WHERE NOT es_pronostico) = 0 THEN 'pronóstico'
        WHEN COUNT(*) FILTER (WHERE es_pronostico) = 0     THEN 'medido'
        ELSE 'parcial (hoy)'
    END AS tipo_dia
FROM gold.v_clima_horario
GROUP BY ciudad, region, fecha;
"""

CHECKS = {
    "filas_fact": "SELECT COUNT(*) FROM gold.fact_clima_horario",
    "grano_duplicado": (
        "SELECT COUNT(*) - COUNT(DISTINCT (ciudad_id, fecha_hora)) "
        "FROM gold.fact_clima_horario"
    ),
    "huerfanos_ciudad": (
        "SELECT COUNT(*) FROM gold.fact_clima_horario f "
        "LEFT JOIN gold.dim_ciudad d ON d.ciudad_id = f.ciudad_id "
        "WHERE d.ciudad_id IS NULL"
    ),
    "huerfanos_tiempo": (
        "SELECT COUNT(*) FROM gold.fact_clima_horario f "
        "LEFT JOIN gold.dim_tiempo d ON d.tiempo_id = f.tiempo_id "
        "WHERE d.tiempo_id IS NULL"
    ),
    "huerfanos_condicion": (
        "SELECT COUNT(*) FROM gold.fact_clima_horario f "
        "LEFT JOIN gold.dim_condicion d ON d.condicion_id = f.condicion_id "
        "WHERE d.condicion_id IS NULL"
    ),
}


@dag(
    dag_id="g09_gold_open_meteo",
    description="Modelo estrella (incremental) + vistas semánticas para el dashboard",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[SILVER_ASSET],
    catchup=False,
    max_active_runs=1,
    tags=["g09", "gold"],
)
def g09_gold_open_meteo():

    @task
    def build_dimensions():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(DIMS_SQL)
        finally:
            engine.dispose()

    @task
    def build_fact():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(FACT_SQL)
                total = conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM gold.fact_clima_horario"
                ).scalar()
            print(f"gold.fact_clima_horario: {total} filas.")
        finally:
            engine.dispose()

    @task
    def verify_integrity():
        """Si el modelo está roto, falla ACÁ: no se publican vistas ni se emite el asset."""
        engine = get_database_engine()
        try:
            with engine.connect() as conn:
                res = {k: conn.exec_driver_sql(q).scalar() for k, q in CHECKS.items()}
                horas = conn.exec_driver_sql(
                    "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(snapshot_ts))) / 3600 "
                    "FROM gold.fact_clima_horario"
                ).scalar()
        finally:
            engine.dispose()

        print(f"Checks: {res}")
        if res["filas_fact"] == 0:
            raise ValueError("fact_clima_horario está vacía.")
        problemas = {k: v for k, v in res.items() if k != "filas_fact" and v}
        if problemas:
            raise ValueError(f"Integridad rota: {problemas}")
        if horas is not None and horas > 3:
            print(f"ATENCIÓN: el último snapshot tiene {horas:.1f} h de antigüedad.")
        print("OK integridad: grano único y sin huérfanos.")

    @task(outlets=[GOLD_ASSET])
    def build_views():
        engine = get_database_engine()
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(VIEWS_SQL)
        finally:
            engine.dispose()
        print("Vistas gold.v_* publicadas.")

    build_dimensions() >> build_fact() >> verify_integrity() >> build_views()


g09_gold_open_meteo()