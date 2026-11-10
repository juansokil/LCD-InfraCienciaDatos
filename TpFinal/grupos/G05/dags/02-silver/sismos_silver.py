import os
import logging
from datetime import datetime
import psycopg2

from airflow import DAG
from airflow.operators.python import PythonOperator

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
                    motivo_rechazo TEXT,
                    mag FLOAT,
                    latitud FLOAT,
                    longitud FLOAT,
                    fecha_rechazo TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Desviar a cuarentena registros con problemas de calidad (Clases 03 y 04)
            cur.execute("""
                INSERT INTO silver.sismos_cuarentena (id, motivo_rechazo, mag, latitud, longitud)
                SELECT 
                    id,
                    CASE 
                        WHEN mag IS NULL THEN 'Magnitud nula'
                        WHEN latitude < -90 OR latitude > 90 THEN 'Latitud fuera de rango'
                        WHEN longitude < -180 OR longitude > 180 THEN 'Longitud fuera de rango'
                        ELSE 'Valor anomalo'
                    END AS motivo_rechazo,
                    mag,
                    latitude,
                    longitude
                FROM bronze.sismos_crudo
                WHERE mag IS NULL 
                   OR latitude < -90 OR latitude > 90 
                   OR longitude < -180 OR longitude > 180;
            """)

            # 3. Transformación, limpieza y deduplicación con CTE y Window Function (Clase 04)
            # Solo eventos reales (type = 'earthquake'), coordenadas y magnitud validas
            query_silver = """
                WITH ranked_sismos AS (
                    SELECT 
                        id AS sismo_id,
                        to_timestamp(time_epoch / 1000.0) AT TIME ZONE 'UTC' AS fecha_evento,
                        to_timestamp(updated_epoch / 1000.0) AT TIME ZONE 'UTC' AS fecha_actualizacion,
                        mag AS magnitud,
                        CASE 
                            WHEN mag < 3.0 THEN 'Micro / Leve'
                            WHEN mag >= 3.0 AND mag < 5.0 THEN 'Menor / Moderado'
                            WHEN mag >= 5.0 AND mag < 7.0 THEN 'Fuerte'
                            ELSE 'Mayor / Destructivo'
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
                        COALESCE(tsunami, 0) AS alerta_tsunami,
                        sig AS significancia,
                        type AS tipo_evento,
                        status AS estado_revision,
                        ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_epoch DESC) AS rn
                    FROM bronze.sismos_crudo
                    WHERE type = 'earthquake'
                      AND mag IS NOT NULL
                      AND latitude BETWEEN -90 AND 90
                      AND longitude BETWEEN -180 AND 180
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
                ON CONFLICT (sismo_id) DO UPDATE SET
                    fecha_actualizacion = EXCLUDED.fecha_actualizacion,
                    magnitud = EXCLUDED.magnitud,
                    escala_magnitud = EXCLUDED.escala_magnitud,
                    alerta_tsunami = EXCLUDED.alerta_tsunami,
                    significancia = EXCLUDED.significancia,
                    estado_revision = EXCLUDED.estado_revision,
                    procesado_at = CURRENT_TIMESTAMP;
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