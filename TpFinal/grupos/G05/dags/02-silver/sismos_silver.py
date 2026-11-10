import os
import logging
from datetime import datetime
import psycopg2

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

logger = logging.getLogger(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
        port=int(os.getenv("SOURCE_DB_PORT", 5432)),
        dbname=os.getenv("SOURCE_DB_NAME", "InfraCienciaDatos"),
        user=os.getenv("SOURCE_DB_USER", "admin"),
        password=os.getenv("SOURCE_DB_PASS", "admin")
    )

def procesar_capa_silver():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Asegurar tablas creadas
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS silver;

                CREATE TABLE IF NOT EXISTS silver.sismos_limpio (
                    sismo_id VARCHAR(50) PRIMARY KEY,
                    fecha_evento TIMESTAMP WITH TIME ZONE,
                    fecha_actualizacion TIMESTAMP WITH TIME ZONE,
                    magnitud FLOAT,
                    escala_magnitud VARCHAR(30),
                    tipo_magnitud VARCHAR(20),
                    lugar TEXT,
                    region TEXT,
                    profundidad_km FLOAT,
                    latitud FLOAT,
                    longitud FLOAT,
                    alerta_tsunami INT,
                    significancia INT,
                    tipo_evento VARCHAR(50),
                    estado_revision VARCHAR(20),
                    procesado_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS silver.sismos_cuarentena (
                    id VARCHAR(50),
                    updated_epoch BIGINT,
                    motivo_rechazo TEXT,
                    mag FLOAT,
                    latitud FLOAT,
                    longitud FLOAT,
                    fecha_rechazo TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                ALTER TABLE silver.sismos_cuarentena
                    ADD COLUMN IF NOT EXISTS updated_epoch BIGINT;

                CREATE UNIQUE INDEX IF NOT EXISTS
                    sismos_cuarentena_id_updated_epoch_uq
                ON silver.sismos_cuarentena (id, updated_epoch)
                WHERE updated_epoch IS NOT NULL;
            """)

            # La cuarentena conserva versiones rechazadas, pero no duplica
            # una misma version cuando Silver vuelve a ejecutarse.
            cur.execute("""
                INSERT INTO silver.sismos_cuarentena (
                    id, updated_epoch, motivo_rechazo, mag, latitud, longitud
                )
                SELECT 
                    id,
                    updated_epoch,
                    CASE 
                        WHEN mag IS NULL THEN 'Magnitud nula'
                        WHEN time_epoch IS NULL THEN 'Fecha del evento nula'
                        WHEN latitude IS NULL THEN 'Latitud nula'
                        WHEN latitude < -90 OR latitude > 90 THEN 'Latitud fuera de rango'
                        WHEN longitude IS NULL THEN 'Longitud nula'
                        WHEN longitude < -180 OR longitude > 180 THEN 'Longitud fuera de rango'
                    END AS motivo_rechazo,
                    mag,
                    latitude,
                    longitude
                FROM bronze.sismos_crudo
                WHERE type = 'earthquake'
                  AND (
                       mag IS NULL
                       OR time_epoch IS NULL
                       OR latitude IS NULL
                       OR latitude NOT BETWEEN -90 AND 90
                       OR longitude IS NULL
                       OR longitude NOT BETWEEN -180 AND 180
                  )
                ON CONFLICT (id, updated_epoch)
                    WHERE updated_epoch IS NOT NULL
                DO NOTHING;
            """)

            # Silver es una tabla derivada: reconstruirla hace que los cambios
            # de versiones y los eventos que dejan de ser válidos no queden obsoletos.
            cur.execute("TRUNCATE TABLE silver.sismos_limpio;")

            # Elegir la ultima version antes de filtrar el tipo de evento.
            query_silver = """
                WITH ranked_sismos AS (
                    SELECT 
                        id AS sismo_id,
                        to_timestamp(time_epoch / 1000.0) AS fecha_evento,
                        to_timestamp(updated_epoch / 1000.0) AS fecha_actualizacion,
                        mag AS magnitud,
                        CASE 
                            WHEN mag < 3.0 THEN 'Menor a 3'
                            WHEN mag < 5.0 THEN '3 a menor que 5'
                            WHEN mag < 7.0 THEN '5 a menor que 7'
                            ELSE '7 o mayor'
                        END AS escala_magnitud,
                        COALESCE(mag_type, 'Desconocido') AS tipo_magnitud,
                        place AS lugar,
                        CASE 
                            WHEN position(',' in place) > 0 THEN trim(substring(place from position(',' in place) + 1))
                            ELSE trim(place)
                        END AS region,
                        depth AS profundidad_km,
                        latitude AS latitud,
                        longitude AS longitud,
                        tsunami AS alerta_tsunami,
                        sig AS significancia,
                        type AS tipo_evento,
                        status AS estado_revision,
                        ROW_NUMBER() OVER (
                            PARTITION BY id
                            ORDER BY updated_epoch DESC
                        ) AS rn
                    FROM bronze.sismos_crudo
                )
                INSERT INTO silver.sismos_limpio (
                    sismo_id, fecha_evento, fecha_actualizacion, magnitud,
                    escala_magnitud, tipo_magnitud, lugar, region,
                    profundidad_km, latitud, longitud, alerta_tsunami,
                    significancia, tipo_evento, estado_revision
                )
                SELECT 
                    sismo_id, fecha_evento, fecha_actualizacion, magnitud,
                    escala_magnitud, tipo_magnitud, lugar, region,
                    profundidad_km, latitud, longitud, alerta_tsunami,
                    significancia, tipo_evento, estado_revision
                FROM ranked_sismos
                WHERE rn = 1
                  AND tipo_evento = 'earthquake'
                  AND magnitud IS NOT NULL
                  AND fecha_evento IS NOT NULL
                  AND latitud BETWEEN -90 AND 90
                  AND longitud BETWEEN -180 AND 180;
            """
            cur.execute(query_silver)

        conn.commit()
        logger.info("Capa Silver procesada exitosamente.")
    finally:
        conn.close()

with DAG(
    dag_id="02_silver_sismos",
    start_date=datetime(2026, 1, 1),
    schedule=None,  # Disparado en cadena por Bronze
    catchup=False,
    is_paused_upon_creation=False,
    tags=["silver", "transformacion", "sismos"]
) as dag:

    tarea_transformacion = PythonOperator(
        task_id="transformar_limpiar_silver",
        python_callable=procesar_capa_silver
    )

    disparar_gold = TriggerDagRunOperator(
        task_id="disparar_gold",
        trigger_dag_id="03_gold_sismos",
        wait_for_completion=False,
    )

    tarea_transformacion >> disparar_gold