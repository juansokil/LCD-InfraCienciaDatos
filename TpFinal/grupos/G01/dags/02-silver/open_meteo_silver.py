import logging
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from sqlalchemy import create_engine, text

def get_engine():
    host     = os.environ.get("SOURCE_DB_HOST", "data_warehouse")
    user     = os.environ.get("SOURCE_DB_USER", "weather_user")
    password = os.environ.get("SOURCE_DB_PASS", "weather_pass")
    db       = os.environ.get("SOURCE_DB_NAME", "weather_dwh")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db}"
    )

default_args = {
    "owner": "G01",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

@dag(
    dag_id="open_meteo_silver",
    default_args=default_args,
    start_date=datetime(2026, 5, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["prod", "silver", "weather"],
    is_paused_upon_creation=False,
)
def open_meteo_pipeline_silver():

    @task()
    def load_clima_actual():

        engine = get_engine()

        query_bronze = text("""
            SELECT id_provincia, payload, ingested_at
            FROM bronze.open_meteo_raw
            ORDER BY ingested_at
        """)

        query_insert = text("""
            INSERT INTO silver.clima_actual (
                id_provincia, fecha_hora, temperatura_c, sensacion_termica_c,
                humedad_relativa, lluvia_mm, viento_kmh, weather_code, actualizado_at
            ) VALUES (
                :id_provincia, :fecha_hora, :temperatura_c, :sensacion_termica_c,
                :humedad_relativa, :lluvia_mm, :viento_kmh, :weather_code, :actualizado_at
            )
            ON CONFLICT (id_provincia, fecha_hora) DO NOTHING
        """)

        loaded = 0
        skipped = 0

        with engine.begin() as conn:
            rows = conn.execute(query_bronze).fetchall()

            for row in rows:
                prov       = row[0]
                current    = row[1].get("current", {})
                fecha_hora = current.get("time")

                if not fecha_hora:
                    logging.warning(f"Sin timestamp en current para {prov}, saltando.")
                    skipped += 1
                    continue

                result = conn.execute(query_insert, {
                    "id_provincia":        prov,
                    "fecha_hora":          fecha_hora,
                    "temperatura_c":       current.get("temperature_2m"),
                    "sensacion_termica_c": current.get("apparent_temperature"),
                    "humedad_relativa":    current.get("relative_humidity_2m"),
                    "lluvia_mm":           current.get("precipitation"),
                    "viento_kmh":          current.get("wind_speed_10m"),
                    "weather_code":        current.get("weather_code"),
                    "actualizado_at":      datetime.now(),
                })

                if result.rowcount == 0:
                    skipped += 1
                else:
                    loaded += 1

        logging.info(f"clima_actual → insertados: {loaded}, ya existían: {skipped}")

    @task()
    def load_clima_pronostico():
   
        engine = get_engine()

        query_bronze = text("""
            SELECT id_provincia, payload, ingested_at
            FROM bronze.open_meteo_raw
            ORDER BY ingested_at
        """)

        query_insert = text("""
            INSERT INTO silver.clima_pronostico (
                id_provincia, fecha_pronostico, snapshot_ts,
                temp_max_c, temp_min_c, sensacion_max_c, sensacion_min_c,
                lluvia_acumulada_mm, precipitacion_prob_pct, viento_max_kmh,
                weather_code, calculado_at
            ) VALUES (
                :id_provincia, :fecha_pronostico, :snapshot_ts,
                :temp_max_c, :temp_min_c, :sensacion_max_c, :sensacion_min_c,
                :lluvia_acumulada_mm, :precipitacion_prob_pct, :viento_max_kmh,
                :weather_code, :calculado_at
            )
            ON CONFLICT (id_provincia, fecha_pronostico) DO UPDATE SET
                snapshot_ts            = EXCLUDED.snapshot_ts,
                temp_max_c             = EXCLUDED.temp_max_c,
                temp_min_c             = EXCLUDED.temp_min_c,
                sensacion_max_c        = EXCLUDED.sensacion_max_c,
                sensacion_min_c        = EXCLUDED.sensacion_min_c,
                lluvia_acumulada_mm    = EXCLUDED.lluvia_acumulada_mm,
                precipitacion_prob_pct = EXCLUDED.precipitacion_prob_pct,
                viento_max_kmh         = EXCLUDED.viento_max_kmh,
                weather_code           = EXCLUDED.weather_code,
                calculado_at           = EXCLUDED.calculado_at
        """)

        loaded = 0

        with engine.begin() as conn:
            rows = conn.execute(query_bronze).fetchall()

            for row in rows:
                prov        = row[0]
                daily       = row[1].get("daily", {})
                snapshot_ts = row[2]
                
                for fecha, t_max, t_min, s_max, s_min, lluvia, prob, viento, wcode in zip(
                    daily.get("time", []),
                    daily.get("temperature_2m_max", []),
                    daily.get("temperature_2m_min", []),
                    daily.get("apparent_temperature_max", []),
                    daily.get("apparent_temperature_min", []),
                    daily.get("precipitation_sum", []),
                    daily.get("precipitation_probability_max", []),
                    daily.get("wind_speed_10m_max", []),
                    daily.get("weather_code", []),
                ):
                    conn.execute(query_insert, {
                        "id_provincia":         prov,
                        "fecha_pronostico":     fecha,
                        "snapshot_ts":          snapshot_ts,
                        "temp_max_c":           t_max,
                        "temp_min_c":           t_min,
                        "sensacion_max_c":      s_max,
                        "sensacion_min_c":      s_min,
                        "lluvia_acumulada_mm":  lluvia,
                        "precipitacion_prob_pct": prob,
                        "viento_max_kmh":       viento,
                        "weather_code":         wcode,
                        "calculado_at":         datetime.now(),
                    })
                    loaded += 1

        logging.info(f"clima_pronostico → filas cargadas/actualizadas: {loaded}")

    load_clima_actual()
    load_clima_pronostico()


open_meteo_silver_dag = open_meteo_pipeline_silver()