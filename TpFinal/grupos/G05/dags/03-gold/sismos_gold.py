import logging
import os
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
        password=os.getenv("SOURCE_DB_PASS", "admin"),
    )


def reconstruir_gold():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS gold;

                CREATE TABLE IF NOT EXISTS gold.dim_fecha (
                    fecha DATE PRIMARY KEY,
                    anio SMALLINT NOT NULL,
                    mes SMALLINT NOT NULL,
                    dia SMALLINT NOT NULL,
                    dia_semana SMALLINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gold.dim_zona (
                    zona_id BIGSERIAL PRIMARY KEY,
                    zona_reportada TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS gold.fact_sismo (
                    sismo_id VARCHAR(50) PRIMARY KEY,
                    fecha DATE NOT NULL REFERENCES gold.dim_fecha(fecha),
                    zona_id BIGINT NOT NULL REFERENCES gold.dim_zona(zona_id),
                    fecha_evento TIMESTAMPTZ NOT NULL,
                    magnitud DOUBLE PRECISION NOT NULL,
                    escala_magnitud VARCHAR(30) NOT NULL,
                    profundidad_km DOUBLE PRECISION,
                    latitud DOUBLE PRECISION NOT NULL,
                    longitud DOUBLE PRECISION NOT NULL,
                    tsunami SMALLINT,
                    significancia INTEGER
                );

                CREATE OR REPLACE VIEW gold.v_mapa_sismos AS
                SELECT f.sismo_id, f.fecha_evento, f.magnitud,
                       f.profundidad_km, f.latitud, f.longitud, f.tsunami,
                       z.zona_reportada
                FROM gold.fact_sismo f
                JOIN gold.dim_zona z USING (zona_id);

                CREATE OR REPLACE VIEW gold.v_actividad_mensual AS
                SELECT date_trunc('month', f.fecha_evento)::date AS mes,
                       z.zona_reportada,
                       COUNT(*) AS cantidad_sismos,
                       ROUND(AVG(f.magnitud)::numeric, 2) AS magnitud_promedio,
                       MAX(f.magnitud) AS magnitud_maxima,
                       COUNT(*) FILTER (WHERE f.tsunami = 1) AS marcados_tsunami
                FROM gold.fact_sismo f
                JOIN gold.dim_zona z USING (zona_id)
                GROUP BY 1, 2;

                CREATE OR REPLACE VIEW gold.v_actividad_zona AS
                SELECT z.zona_reportada,
                       COUNT(*) AS cantidad_sismos,
                       ROUND(AVG(f.magnitud)::numeric, 2) AS magnitud_promedio,
                       MAX(f.magnitud) AS magnitud_maxima,
                       COUNT(*) FILTER (WHERE f.tsunami = 1) AS marcados_tsunami
                FROM gold.fact_sismo f
                JOIN gold.dim_zona z USING (zona_id)
                GROUP BY z.zona_reportada;

                CREATE OR REPLACE VIEW gold.v_sismos_tsunami AS
                SELECT f.sismo_id, f.fecha_evento, f.magnitud,
                       f.profundidad_km, f.latitud, f.longitud,
                       z.zona_reportada
                FROM gold.fact_sismo f
                JOIN gold.dim_zona z USING (zona_id)
                WHERE f.tsunami = 1;
            """)

            cur.execute("""
                TRUNCATE TABLE gold.fact_sismo, gold.dim_zona, gold.dim_fecha
                RESTART IDENTITY CASCADE;

                INSERT INTO gold.dim_fecha (fecha, anio, mes, dia, dia_semana)
                SELECT DISTINCT fecha_evento::date,
                       EXTRACT(YEAR FROM fecha_evento)::smallint,
                       EXTRACT(MONTH FROM fecha_evento)::smallint,
                       EXTRACT(DAY FROM fecha_evento)::smallint,
                       EXTRACT(ISODOW FROM fecha_evento)::smallint
                FROM silver.sismos_limpio;

                INSERT INTO gold.dim_zona (zona_reportada)
                SELECT DISTINCT COALESCE(NULLIF(BTRIM(region), ''), 'Sin zona informada')
                FROM silver.sismos_limpio;

                INSERT INTO gold.fact_sismo (
                    sismo_id, fecha, zona_id, fecha_evento, magnitud,
                    escala_magnitud, profundidad_km, latitud, longitud,
                    tsunami, significancia
                )
                SELECT s.sismo_id,
                       s.fecha_evento::date,
                       z.zona_id,
                       s.fecha_evento,
                       s.magnitud,
                       s.escala_magnitud,
                       s.profundidad_km,
                       s.latitud,
                       s.longitud,
                       s.alerta_tsunami,
                       s.significancia
                FROM silver.sismos_limpio s
                JOIN gold.dim_zona z
                  ON z.zona_reportada = COALESCE(
                      NULLIF(BTRIM(s.region), ''),
                      'Sin zona informada'
                  );
            """)

            cur.execute("""
                SELECT COUNT(*)
                FROM gold.fact_sismo f
                LEFT JOIN gold.dim_fecha d USING (fecha)
                LEFT JOIN gold.dim_zona z USING (zona_id)
                WHERE d.fecha IS NULL OR z.zona_id IS NULL;
            """)
            orphan_count = cur.fetchone()[0]
            if orphan_count:
                raise RuntimeError(
                    f"Gold contiene {orphan_count} hechos sin dimensión asociada."
                )

            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM silver.sismos_limpio),
                    (SELECT COUNT(*) FROM gold.fact_sismo);
            """)
            silver_count, fact_count = cur.fetchone()
            if silver_count != fact_count:
                raise RuntimeError(
                    f"Conteo Gold no coincide con Silver: "
                    f"{fact_count} hechos vs {silver_count} eventos."
                )

        conn.commit()
        logger.info(
            "Gold reconstruido: %d hechos, integridad dimensional verificada.",
            fact_count,
        )
    except Exception:
        conn.rollback()
        logger.exception("Falló la reconstrucción de Gold.")
        raise
    finally:
        conn.close()


with DAG(
    dag_id="03_gold_sismos",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=False,
    tags=["gold", "modelo-dimensional", "sismos"],
) as dag:

    reconstruir_tablas_gold = PythonOperator(
        task_id="reconstruir_gold",
        python_callable=reconstruir_gold,
    )
