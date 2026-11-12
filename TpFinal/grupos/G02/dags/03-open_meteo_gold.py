"""
DAG open_meteo_gold  ·  Capa Gold (modelo estrella)

Lo dispara open_meteo_silver (TriggerDagRunOperator) cuando termina de cargar Silver.
Lee SOLO de Silver (y de Bronze únicamente para saber cuál es el snapshot más
reciente) y construye:

    gold.dim_ciudad              una fila por ciudad
    gold.dim_fecha               una fila por día (date_id = YYYYMMDD)
    gold.fact_clima_actual       una fila por ciudad y captura (grano = respuesta Bronze)
    gold.fact_pronostico_diario  una fila por ciudad y fecha pronosticada (último snapshot)

    gold.v_pronostico            hecho + dimensiones + banderas de días destacados
    gold.v_clima_ultimo          última captura de cada ciudad

Es idempotente: se puede ejecutar todas las veces que haga falta sin duplicar filas.
"""
import logging

import pendulum
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task

log = logging.getLogger(__name__)

CONN_ID = "warehouse"
TIMEZONE = "America/Argentina/Buenos_Aires"

# Misma lista que 01-open_meteo_bronze.py. Silver solo guarda city_code, así que
# el nombre, la provincia y las coordenadas se cargan acá en dim_ciudad.
CITIES = [
    {"city_code": "BUE", "city_name": "Buenos Aires", "province": "Buenos Aires", "latitude": -34.6037, "longitude": -58.3816},
    {"city_code": "COR", "city_name": "Córdoba", "province": "Córdoba", "latitude": -31.4201, "longitude": -64.1888},
    {"city_code": "MDZ", "city_name": "Mendoza", "province": "Mendoza", "latitude": -32.8895, "longitude": -68.8458},
    {"city_code": "SLA", "city_name": "Salta", "province": "Salta", "latitude": -24.7821, "longitude": -65.4232},
    {"city_code": "BRC", "city_name": "San Carlos de Bariloche", "province": "Río Negro", "latitude": -41.1335, "longitude": -71.3103},
]

# ---------------------------------------------------------------------------
# DDL: tablas y vistas
# ---------------------------------------------------------------------------
DDL_SQL = """
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
    city_id    SERIAL PRIMARY KEY,
    city_code  VARCHAR(10) UNIQUE NOT NULL,
    city_name  TEXT NOT NULL,
    province   TEXT,
    country    TEXT,
    latitude   NUMERIC(8,4),
    longitude  NUMERIC(8,4),
    timezone   TEXT
);

CREATE TABLE IF NOT EXISTS gold.dim_fecha (
    date_id      INTEGER PRIMARY KEY,           -- formato YYYYMMDD
    full_date    DATE UNIQUE NOT NULL,
    year         SMALLINT,
    month        SMALLINT,
    month_name   TEXT,
    day          SMALLINT,
    day_of_week  TEXT,
    is_weekend   BOOLEAN
);

-- Grano: una fila por respuesta de Bronze (source_id) y ciudad.
CREATE TABLE IF NOT EXISTS gold.fact_clima_actual (
    source_id               BIGINT PRIMARY KEY,
    city_id                 INTEGER NOT NULL REFERENCES gold.dim_ciudad (city_id),
    date_id                 INTEGER NOT NULL REFERENCES gold.dim_fecha (date_id),
    captured_at             TIMESTAMPTZ NOT NULL,
    temperature_c           NUMERIC(5,2),
    apparent_temperature_c  NUMERIC(5,2),
    humidity_pct            INTEGER,
    precipitation_mm        NUMERIC(8,2),
    wind_speed_kmh          NUMERIC(8,2),
    wind_direction_deg      INTEGER,
    cloud_cover_pct         INTEGER,
    weather_code            INTEGER,
    weather_description     TEXT
);

-- Grano: una fila por ciudad y fecha pronosticada (siempre el snapshot más reciente).
CREATE TABLE IF NOT EXISTS gold.fact_pronostico_diario (
    city_id               INTEGER NOT NULL REFERENCES gold.dim_ciudad (city_id),
    date_id               INTEGER NOT NULL REFERENCES gold.dim_fecha (date_id),
    source_id             BIGINT,                -- de qué respuesta Bronze salió (trazabilidad)
    temperature_max_c     NUMERIC(5,2),
    temperature_min_c     NUMERIC(5,2),
    precipitation_sum_mm  NUMERIC(8,2),
    wind_speed_max_kmh    NUMERIC(8,2),
    weather_code          INTEGER,
    weather_description   TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (city_id, date_id)
);

CREATE OR REPLACE VIEW gold.v_pronostico AS
SELECT
    c.city_code,
    c.city_name,
    d.full_date,
    d.day_of_week,
    p.temperature_max_c,
    p.temperature_min_c,
    p.temperature_max_c - p.temperature_min_c               AS diferencia_termica_c,
    p.precipitation_sum_mm,
    p.wind_speed_max_kmh,
    p.weather_description,
    COALESCE(p.temperature_max_c >= 35, FALSE)              AS dia_caluroso,
    COALESCE(p.temperature_min_c <= 0, FALSE)               AS dia_frio,
    COALESCE(p.precipitation_sum_mm >= 10, FALSE)           AS dia_lluvioso,
    COALESCE(p.wind_speed_max_kmh >= 40, FALSE)             AS dia_ventoso,
    p.loaded_at
FROM gold.fact_pronostico_diario p
JOIN gold.dim_ciudad c ON c.city_id = p.city_id
JOIN gold.dim_fecha  d ON d.date_id = p.date_id;

CREATE OR REPLACE VIEW gold.v_clima_ultimo AS
SELECT DISTINCT ON (f.city_id)
    c.city_code,
    c.city_name,
    f.captured_at,
    f.temperature_c,
    f.apparent_temperature_c,
    f.humidity_pct,
    f.precipitation_mm,
    f.wind_speed_kmh,
    f.cloud_cover_pct,
    f.weather_description
FROM gold.fact_clima_actual f
JOIN gold.dim_ciudad c ON c.city_id = f.city_id
ORDER BY f.city_id, f.captured_at DESC;
"""

# ---------------------------------------------------------------------------
# Cargas
# ---------------------------------------------------------------------------
DIM_CIUDAD_SQL = """
INSERT INTO gold.dim_ciudad
    (city_code, city_name, province, country, latitude, longitude, timezone)
VALUES
    (%(city_code)s, %(city_name)s, %(province)s, 'Argentina',
     %(latitude)s, %(longitude)s, %(timezone)s)
ON CONFLICT (city_code) DO UPDATE SET
    city_name = EXCLUDED.city_name,
    province  = EXCLUDED.province,
    country   = EXCLUDED.country,
    latitude  = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    timezone  = EXCLUDED.timezone;
"""

# Fechas presentes en Silver: el día local de cada captura + las fechas pronosticadas.
DIM_FECHA_SQL = """
INSERT INTO gold.dim_fecha
    (date_id, full_date, year, month, month_name, day, day_of_week, is_weekend)
SELECT
    to_char(d, 'YYYYMMDD')::integer,
    d,
    EXTRACT(YEAR  FROM d)::smallint,
    EXTRACT(MONTH FROM d)::smallint,
    (ARRAY['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
           'septiembre','octubre','noviembre','diciembre'])[EXTRACT(MONTH FROM d)::int],
    EXTRACT(DAY FROM d)::smallint,
    (ARRAY['lunes','martes','miércoles','jueves','viernes','sábado','domingo'])
        [EXTRACT(ISODOW FROM d)::int],
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM (
    SELECT DISTINCT (s.valid_at AT TIME ZONE c.timezone)::date AS d
    FROM silver.clima_actual s
    JOIN gold.dim_ciudad c ON c.city_code = s.city_code
    WHERE s.valid_at IS NOT NULL
    UNION
    SELECT forecast_date FROM silver.pronostico_diario
) fechas
ON CONFLICT (date_id) DO NOTHING;
"""

# Una fila por respuesta de Bronze: si ya está, no se vuelve a insertar.
FACT_CLIMA_SQL = """
INSERT INTO gold.fact_clima_actual (
    source_id, city_id, date_id, captured_at,
    temperature_c, apparent_temperature_c, humidity_pct, precipitation_mm,
    wind_speed_kmh, wind_direction_deg, cloud_cover_pct,
    weather_code, weather_description
)
SELECT
    s.source_id,
    c.city_id,
    to_char((s.valid_at AT TIME ZONE c.timezone)::date, 'YYYYMMDD')::integer,
    s.valid_at,
    s.temperature_c, s.apparent_temperature_c, s.humidity_pct, s.precipitation_mm,
    s.wind_speed_kmh, s.wind_direction_deg, s.cloud_cover_pct,
    s.weather_code, s.weather_description
FROM silver.clima_actual s
JOIN gold.dim_ciudad c ON c.city_code = s.city_code
WHERE s.valid_at IS NOT NULL
ON CONFLICT (source_id) DO NOTHING;
"""

# DISTINCT ON se queda, por ciudad y fecha, con el snapshot de Bronze más reciente.
# El UPSERT hace que ese pronóstico reemplace al anterior sin duplicar la fila.
FACT_PRONOSTICO_SQL = """
INSERT INTO gold.fact_pronostico_diario (
    city_id, date_id, source_id,
    temperature_max_c, temperature_min_c, precipitation_sum_mm,
    wind_speed_max_kmh, weather_code, weather_description, loaded_at
)
SELECT DISTINCT ON (p.city_code, p.forecast_date)
    c.city_id,
    to_char(p.forecast_date, 'YYYYMMDD')::integer,
    p.source_id,
    p.temperature_max_c, p.temperature_min_c, p.precipitation_sum_mm,
    p.wind_speed_max_kmh, p.weather_code, p.weather_description,
    now()
FROM silver.pronostico_diario p
JOIN bronze.open_meteo_raw b ON b.id = p.source_id
JOIN gold.dim_ciudad c       ON c.city_code = p.city_code
ORDER BY p.city_code, p.forecast_date, b.ingested_at DESC, b.id DESC
ON CONFLICT (city_id, date_id) DO UPDATE SET
    source_id            = EXCLUDED.source_id,
    temperature_max_c    = EXCLUDED.temperature_max_c,
    temperature_min_c    = EXCLUDED.temperature_min_c,
    precipitation_sum_mm = EXCLUDED.precipitation_sum_mm,
    wind_speed_max_kmh   = EXCLUDED.wind_speed_max_kmh,
    weather_code         = EXCLUDED.weather_code,
    weather_description  = EXCLUDED.weather_description,
    loaded_at            = EXCLUDED.loaded_at;
"""


@task
def create_gold_tables():
    """Crea el esquema, las tablas y las vistas de Gold si no existen."""
    PostgresHook(postgres_conn_id=CONN_ID).run(DDL_SQL)
    log.info("Tablas y vistas de Gold creadas o verificadas.")


@task
def load_dimensions():
    """Carga dim_ciudad (desde la lista fija) y dim_fecha (desde las fechas de Silver)."""
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    cities = [{**city, "timezone": TIMEZONE} for city in CITIES]

    with hook.get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(DIM_CIUDAD_SQL, cities)
            cursor.execute(DIM_FECHA_SQL)
            cursor.execute("SELECT COUNT(*) FROM gold.dim_ciudad")
            n_ciudades = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM gold.dim_fecha")
            n_fechas = cursor.fetchone()[0]

    log.info("dim_ciudad: %s filas | dim_fecha: %s filas", n_ciudades, n_fechas)


@task
def load_facts():
    """Carga fact_clima_actual y fact_pronostico_diario desde Silver."""
    hook = PostgresHook(postgres_conn_id=CONN_ID)

    with hook.get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(FACT_CLIMA_SQL)
            nuevas = cursor.rowcount
            cursor.execute(FACT_PRONOSTICO_SQL)
            upserts = cursor.rowcount
            cursor.execute("SELECT COUNT(*) FROM gold.fact_clima_actual")
            total_clima = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM gold.fact_pronostico_diario")
            total_pron = cursor.fetchone()[0]

    log.info("fact_clima_actual: %s filas nuevas (total %s)", nuevas, total_clima)
    log.info("fact_pronostico_diario: %s filas insertadas/actualizadas (total %s)", upserts, total_pron)


@dag(
    dag_id="open_meteo_gold",      # Silver lo dispara por este nombre (GOLD_DAG_ID)
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={"retries": 2},
    tags=["open-meteo", "gold"],
)
def open_meteo_gold():
    create_gold_tables() >> load_dimensions() >> load_facts()


open_meteo_gold()
