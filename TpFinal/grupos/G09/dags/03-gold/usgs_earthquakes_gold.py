from datetime import datetime
import os

from airflow.decorators import dag, task

SCHEDULE = "*/15 * * * *"
SOURCE_TABLE = "silver.earthquakes"
DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:"
    f"{os.getenv('SOURCE_DB_PORT', '5432')}/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)

BUILD_SQL = """
    DROP TABLE IF EXISTS gold.earthquake_risk_summary;
    DROP TABLE IF EXISTS gold.fact_region_daily;
    DROP TABLE IF EXISTS gold.fact_earthquake_events;
    DROP TABLE IF EXISTS gold.dim_time;
    DROP TABLE IF EXISTS gold.dim_region;

    CREATE TABLE gold.dim_region AS
        SELECT
            dense_rank() OVER (ORDER BY region) AS region_id,
            region,
            COUNT(*)  AS total_events,
            MAX(mag)  AS max_mag,
            AVG(mag)  AS avg_mag
        FROM silver.earthquakes
        WHERE region IS NOT NULL
        GROUP BY region;

    CREATE TABLE gold.dim_time AS
        SELECT DISTINCT
            event_time::date                            AS event_date,
            to_char(event_time::date, 'YYYYMMDD')::int  AS date_id,
            EXTRACT(year  FROM event_time)::int         AS year,
            EXTRACT(month FROM event_time)::int         AS month,
            EXTRACT(day   FROM event_time)::int         AS day,
            EXTRACT(hour  FROM event_time)::int         AS hour,
            trim(to_char(event_time, 'Day'))            AS weekday,
            CASE
                WHEN EXTRACT(hour FROM event_time) BETWEEN  6 AND 11 THEN 'manana'
                WHEN EXTRACT(hour FROM event_time) BETWEEN 12 AND 17 THEN 'tarde'
                WHEN EXTRACT(hour FROM event_time) BETWEEN 18 AND 22 THEN 'noche'
                ELSE 'madrugada'
            END AS franja_horaria
        FROM silver.earthquakes
        WHERE event_time IS NOT NULL;

    CREATE TABLE gold.fact_earthquake_events AS
        SELECT
            e.event_id,
            r.region_id,
            to_char(e.event_time::date, 'YYYYMMDD')::int AS date_id,
            e.place,
            e.mag,
            e.mag_type,
            e.depth_km,
            e.latitude,
            e.longitude,
            e.felt,
            e.cdi,
            e.mmi,
            e.alert,
            e.tsunami,
            e.sig,
            e.severity_class,
            e.latency_update_minutes,
            e.latency_ingestion_minutes,
            e.event_time,
            e.updated_time,
            now()                AS _processed_at,
            'silver.earthquakes' AS _source_table
        FROM silver.earthquakes e
        LEFT JOIN gold.dim_region r ON e.region = r.region;

    CREATE TABLE gold.fact_region_daily AS
        SELECT
            r.region_id,
            to_char(e.event_time::date, 'YYYYMMDD')::int                              AS date_id,
            e.event_time::date                                                         AS event_date,
            COUNT(*)                                                                   AS events_count,
            MAX(e.mag)                                                                 AS max_mag,
            AVG(e.mag)                                                                 AS avg_mag,
            AVG(e.depth_km)                                                            AS avg_depth_km,
            AVG(e.cdi)                                                                 AS avg_cdi,
            AVG(e.mmi)                                                                 AS avg_mmi,
            SUM(CASE WHEN e.tsunami = 1 THEN 1 ELSE 0 END)                            AS tsunami_events,
            SUM(CASE WHEN e.severity_class IN ('fuerte', 'mayor') THEN 1 ELSE 0 END)  AS severe_events
        FROM silver.earthquakes e
        LEFT JOIN gold.dim_region r ON e.region = r.region
        WHERE e.event_time IS NOT NULL
        GROUP BY r.region_id, e.event_time::date;

    CREATE TABLE gold.earthquake_risk_summary AS
        SELECT
            e.region,
            COUNT(*)                                                                   AS events_count,
            MAX(e.mag)                                                                 AS max_mag,
            AVG(e.mag)                                                                 AS avg_mag,
            AVG(e.depth_km)                                                            AS avg_depth_km,
            AVG(e.latency_ingestion_minutes)                                           AS avg_ingestion_latency_minutes,
            SUM(CASE WHEN e.severity_class IN ('fuerte', 'mayor') THEN 1 ELSE 0 END)  AS severe_events,
            SUM(CASE WHEN e.tsunami = 1 THEN 1 ELSE 0 END)                            AS tsunami_events,
            MAX(e.sig)                                                                 AS max_significance,
            MAX(e.event_time)                                                          AS last_event_time
        FROM silver.earthquakes e
        GROUP BY e.region
        ORDER BY severe_events DESC, max_mag DESC, events_count DESC;
"""


@dag(
    dag_id="usgs_earthquakes_gold",
    start_date=datetime(2026, 1, 1),
    schedule=SCHEDULE,
    catchup=False,
    tags=["g09", "gold", "usgs", "earthquakes"],
    is_paused_upon_creation=False,
)
def usgs_earthquakes_gold():
    @task
    def build_gold_tables() -> None:
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.connect() as conn:
            if not conn.execute(
                sqlalchemy.text(f"SELECT to_regclass('{SOURCE_TABLE}')")
            ).scalar():
                print(f"{SOURCE_TABLE} no existe todavia. Se saltea Gold.")
                return

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS gold"))
            conn.exec_driver_sql(BUILD_SQL)
        print("Tablas Gold reconstruidas.")

    build_gold_tables()


usgs_earthquakes_gold()
