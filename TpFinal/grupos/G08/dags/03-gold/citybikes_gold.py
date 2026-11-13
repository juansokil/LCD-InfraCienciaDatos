"""DAG: citybikes_gold"""

from datetime import datetime, timedelta

from airflow.decorators import dag, task

from common.assets import GOLD_CITYBIKES, SILVER_CITYBIKES


@dag(
    dag_id="citybikes_gold",
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    start_date=datetime(2026, 10, 1),
    schedule=[SILVER_CITYBIKES],
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["gold", "citybikes"],
    doc_md=__doc__,
)
def citybikes_gold():
    @task(outlets=[GOLD_CITYBIKES])
    def crear_vista_saturacion():
        import os

        import sqlalchemy

        uri = (
            "postgresql+psycopg2://"
            f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
            f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
            f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME', 'CityBikes')}"
        )
        sql = sqlalchemy.text("""
            CREATE OR REPLACE VIEW gold.vw_citybikes_saturacion AS
            SELECT
                s.network_id,
                s.station_id,
                COALESCE(s.station_name, s.name) AS station_name,
                z.ciudad,
                z.zona,
                z.zona_padre,
                z.zona_nivel,
                s.snapshot_ts,
                s.snapshot_local,
                EXTRACT(ISODOW FROM s.snapshot_local)::integer AS dia_semana,
                EXTRACT(HOUR FROM s.snapshot_local)::integer AS hora,
                s.free_bikes,
                s.empty_slots,
                (s.free_bikes = 0) AS saturada
            FROM silver.citybikes_stations s
            LEFT JOIN silver.citybikes_station_zone z
              ON z.network_id = s.network_id AND z.station_id = s.station_id
            WHERE s.renting IS TRUE
              AND COALESCE(s._quality_flags, '') = ''
        """)
        engine = sqlalchemy.create_engine(uri)
        with engine.begin() as conn:
            conn.execute(sql)

    crear_vista_saturacion()


citybikes_gold()
