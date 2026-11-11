
"""
LogiWeather - DAG Gold
TP Final - Grupo 10

Modelo dimensional con transformaciones SQL.
Las reglas de incentivos se incorporarán
cuando estén acordadas por el grupo.
"""

import logging
import os
from datetime import timedelta

import pendulum
import psycopg2
from airflow.sdk import dag, task


def conectar_warehouse():
    return psycopg2.connect(
        host=os.environ["WAREHOUSE_HOST"],
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
        port=5432,
        connect_timeout=10,
    )


@dag(
    dag_id="logiweather_gold",
    description="Construye el modelo estrella de LogiWeather",
    start_date=pendulum.datetime(2026, 11, 8, tz="UTC"),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["G10", "LogiWeather", "Gold", "SQL"],
)
def logiweather_gold():

    @task
    def crear_modelo_gold():

        sql = """
        CREATE SCHEMA IF NOT EXISTS gold;

        CREATE TABLE IF NOT EXISTS gold.dim_ciudad (
            ciudad_id VARCHAR(50) PRIMARY KEY,
            ciudad VARCHAR(100) NOT NULL,
            latitud DOUBLE PRECISION,
            longitud DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS gold.dim_fecha (
            fecha DATE PRIMARY KEY,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            dia INTEGER NOT NULL,
            dia_semana INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gold.fact_alertas_incentivos (
            ciudad_id VARCHAR(50) NOT NULL
                REFERENCES gold.dim_ciudad(ciudad_id),

            fecha_pronostico DATE NOT NULL
                REFERENCES gold.dim_fecha(fecha),

            temperatura_max NUMERIC(6,2) NOT NULL,
            temperatura_min NUMERIC(6,2) NOT NULL,

            probabilidad_lluvia INTEGER NOT NULL,
            precipitacion_mm NUMERIC(10,2) NOT NULL,
            weather_code INTEGER NOT NULL,

            -- Trazabilidad del pronóstico
            bronze_id BIGINT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,

            -- Reglas de negocio pendientes de definir
            nivel_alerta VARCHAR(30),
            incentivo_recomendado NUMERIC(10,2),

            PRIMARY KEY (ciudad_id, fecha_pronostico)
        );
        """

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql)

        logging.info("Modelo dimensional Gold preparado.")

    @task
    def actualizar_modelo_gold():

        sql_ciudades = """
        INSERT INTO gold.dim_ciudad (
            ciudad_id, ciudad, latitud, longitud
        )
        SELECT DISTINCT ON (s.ciudad_id)
            s.ciudad_id,
            s.ciudad,
            (b.payload->>'latitude')::DOUBLE PRECISION,
            (b.payload->>'longitude')::DOUBLE PRECISION
        FROM silver.pronosticos_diarios s
        JOIN bronze.pronosticos_raw b
            ON s.bronze_id = b.id
        ORDER BY
            s.ciudad_id,
            s.ingested_at DESC,
            s.bronze_id DESC
        ON CONFLICT (ciudad_id)
        DO UPDATE SET
            ciudad = EXCLUDED.ciudad,
            latitud = EXCLUDED.latitud,
            longitud = EXCLUDED.longitud;
        """

        sql_fechas = """
        INSERT INTO gold.dim_fecha (
            fecha, anio, mes, dia, dia_semana
        )
        SELECT DISTINCT
            fecha_pronostico,
            EXTRACT(YEAR FROM fecha_pronostico)::INTEGER,
            EXTRACT(MONTH FROM fecha_pronostico)::INTEGER,
            EXTRACT(DAY FROM fecha_pronostico)::INTEGER,
            EXTRACT(ISODOW FROM fecha_pronostico)::INTEGER
        FROM silver.pronosticos_diarios
        ON CONFLICT (fecha) DO NOTHING;
        """

        sql_hechos = """
        WITH ultimo_pronostico AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        s.ciudad_id,
                        s.fecha_pronostico
                    ORDER BY
                        s.ingested_at DESC,
                        s.bronze_id DESC
                ) AS numero_version
            FROM silver.pronosticos_diarios s
        )
        INSERT INTO gold.fact_alertas_incentivos (
            ciudad_id,
            fecha_pronostico,
            temperatura_max,
            temperatura_min,
            probabilidad_lluvia,
            precipitacion_mm,
            weather_code,
            bronze_id,
            ingested_at
        )
        SELECT
            ciudad_id,
            fecha_pronostico,
            temperatura_max,
            temperatura_min,
            probabilidad_lluvia,
            precipitacion_mm,
            weather_code,
            bronze_id,
            ingested_at
        FROM ultimo_pronostico
        WHERE numero_version = 1

        ON CONFLICT (ciudad_id, fecha_pronostico)
        DO UPDATE SET
            temperatura_max = EXCLUDED.temperatura_max,
            temperatura_min = EXCLUDED.temperatura_min,
            probabilidad_lluvia = EXCLUDED.probabilidad_lluvia,
            precipitacion_mm = EXCLUDED.precipitacion_mm,
            weather_code = EXCLUDED.weather_code,
            bronze_id = EXCLUDED.bronze_id,
            ingested_at = EXCLUDED.ingested_at

        WHERE
            EXCLUDED.ingested_at >
                gold.fact_alertas_incentivos.ingested_at
            OR (
                EXCLUDED.ingested_at =
                    gold.fact_alertas_incentivos.ingested_at
                AND EXCLUDED.bronze_id >
                    gold.fact_alertas_incentivos.bronze_id
            );
        """

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql_ciudades)
                cursor.execute(sql_fechas)
                cursor.execute(sql_hechos)
                hechos_actualizados = cursor.rowcount

        logging.info(
            "Gold actualizado. Hechos insertados "
            "o actualizados: %s",
            hechos_actualizados,
        )

    creacion = crear_modelo_gold()
    actualizacion = actualizar_modelo_gold()

    creacion >> actualizacion


logiweather_gold()