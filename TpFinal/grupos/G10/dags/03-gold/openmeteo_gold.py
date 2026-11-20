"""
LogiWeather - DAG Gold
TP Final - Grupo 10

Modelo dimensional con transformaciones SQL.
Calcula alertas meteorológicas e incentivos
recomendados por lluvia y calor mediante
reglas de negocio configurables.
"""

import logging
import os
from datetime import timedelta

import pendulum
import psycopg2
from airflow.sdk import dag, task

import json
from pathlib import Path

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

            -- Alertas meteorológicas e incentivos recomendados
            nivel_alerta_lluvia VARCHAR(30),
            incentivo_lluvia NUMERIC(10,2),

            nivel_alerta_calor VARCHAR(30),
            incentivo_calor NUMERIC(10,2),

            nivel_alerta VARCHAR(30),
            incentivo_recomendado NUMERIC(10,2),

            PRIMARY KEY (ciudad_id, fecha_pronostico)
        );


        ALTER TABLE gold.fact_alertas_incentivos
            ADD COLUMN IF NOT EXISTS nivel_alerta_lluvia VARCHAR(30),
            ADD COLUMN IF NOT EXISTS incentivo_lluvia NUMERIC(10,2),
            ADD COLUMN IF NOT EXISTS nivel_alerta_calor VARCHAR(30),
            ADD COLUMN IF NOT EXISTS incentivo_calor NUMERIC(10,2);

        """

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql)

        logging.info("Modelo dimensional Gold preparado.")

    @task
    def actualizar_modelo_gold():

        ruta_config = Path(
            "/opt/airflow/config/reglas_negocio.json"
        )

        with ruta_config.open(
            "r", encoding="utf-8"
        ) as archivo:
            reglas = json.load(archivo)

        lluvia = reglas["lluvia"]
        calor = reglas["calor"]

        parametros = {
            # Umbrales de lluvia
            "lluvia_baja_prob": lluvia["baja"]["probabilidad_min"],
            "lluvia_baja_mm": lluvia["baja"]["precipitacion_mm_min"],
            "lluvia_media_prob": lluvia["media"]["probabilidad_min"],
            "lluvia_media_mm": lluvia["media"]["precipitacion_mm_min"],
            "lluvia_alta_prob": lluvia["alta"]["probabilidad_min"],
            "lluvia_alta_mm": lluvia["alta"]["precipitacion_mm_min"],

            # Incentivos por lluvia
            "lluvia_sin_alerta_pct": lluvia["sin_alerta"]["incentivo_pct"],
            "lluvia_baja_pct": lluvia["baja"]["incentivo_pct"],
            "lluvia_media_pct": lluvia["media"]["incentivo_pct"],
            "lluvia_alta_pct": lluvia["alta"]["incentivo_pct"],

            # Umbrales de calor
            "calor_baja_temp": calor["baja"]["temperatura_max_min"],
            "calor_media_temp": calor["media"]["temperatura_max_min"],
            "calor_alta_temp": calor["alta"]["temperatura_max_min"],

            # Incentivos por calor
            "calor_sin_alerta_pct": calor["sin_alerta"]["incentivo_pct"],
            "calor_baja_pct": calor["baja"]["incentivo_pct"],
            "calor_media_pct": calor["media"]["incentivo_pct"],
            "calor_alta_pct": calor["alta"]["incentivo_pct"],
        }

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

        sql_alertas = """
        WITH clasificacion AS (
            SELECT
                ciudad_id,
                fecha_pronostico,

                CASE
                    WHEN probabilidad_lluvia >= %(lluvia_alta_prob)s
                         AND precipitacion_mm >= %(lluvia_alta_mm)s
                    THEN 3

                    WHEN probabilidad_lluvia >= %(lluvia_media_prob)s
                         AND precipitacion_mm >= %(lluvia_media_mm)s
                    THEN 2

                    WHEN probabilidad_lluvia >= %(lluvia_baja_prob)s
                         AND precipitacion_mm >= %(lluvia_baja_mm)s
                    THEN 1

                    ELSE 0
                END AS riesgo_lluvia,

                CASE
                    WHEN temperatura_max >= %(calor_alta_temp)s
                    THEN 3

                    WHEN temperatura_max >= %(calor_media_temp)s
                    THEN 2

                    WHEN temperatura_max >= %(calor_baja_temp)s
                    THEN 1

                    ELSE 0
                END AS riesgo_calor

            FROM gold.fact_alertas_incentivos
        ),

        incentivos AS (
            SELECT
                ciudad_id,
                fecha_pronostico,
                riesgo_lluvia,
                riesgo_calor,

                CASE riesgo_lluvia
                    WHEN 3 THEN 'ALTA'
                    WHEN 2 THEN 'MEDIA'
                    WHEN 1 THEN 'BAJA'
                    ELSE 'SIN_ALERTA'
                END AS nivel_lluvia,

                CASE riesgo_calor
                    WHEN 3 THEN 'ALTA'
                    WHEN 2 THEN 'MEDIA'
                    WHEN 1 THEN 'BAJA'
                    ELSE 'SIN_ALERTA'
                END AS nivel_calor,

                CASE riesgo_lluvia
                    WHEN 3 THEN %(lluvia_alta_pct)s
                    WHEN 2 THEN %(lluvia_media_pct)s
                    WHEN 1 THEN %(lluvia_baja_pct)s
                    ELSE %(lluvia_sin_alerta_pct)s
                END AS incentivo_lluvia_pct,

                CASE riesgo_calor
                    WHEN 3 THEN %(calor_alta_pct)s
                    WHEN 2 THEN %(calor_media_pct)s
                    WHEN 1 THEN %(calor_baja_pct)s
                    ELSE %(calor_sin_alerta_pct)s
                END AS incentivo_calor_pct

            FROM clasificacion
        )

        UPDATE gold.fact_alertas_incentivos AS f
        SET
            nivel_alerta_lluvia = i.nivel_lluvia,
            incentivo_lluvia = i.incentivo_lluvia_pct,

            nivel_alerta_calor = i.nivel_calor,
            incentivo_calor = i.incentivo_calor_pct,

            nivel_alerta = CASE
                GREATEST(i.riesgo_lluvia, i.riesgo_calor)
                WHEN 3 THEN 'ALTA'
                WHEN 2 THEN 'MEDIA'
                WHEN 1 THEN 'BAJA'
                ELSE 'SIN_ALERTA'
            END,

            incentivo_recomendado = GREATEST(
                i.incentivo_lluvia_pct,
                i.incentivo_calor_pct
            )

        FROM incentivos AS i

        WHERE f.ciudad_id = i.ciudad_id
          AND f.fecha_pronostico = i.fecha_pronostico;
        """


        
        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:

                cursor.execute(sql_ciudades)
                cursor.execute(sql_fechas)
                cursor.execute(sql_hechos)

                hechos_actualizados = cursor.rowcount

                cursor.execute(sql_alertas, parametros)

                alertas_calculadas = cursor.rowcount

        logging.info(
            "Gold: %s pronosticos insertados o actualizados.",
            hechos_actualizados,
        )

        logging.info(
            "Gold: %s alertas e incentivos calculados.",
            alertas_calculadas,
        )


    creacion = crear_modelo_gold()
    actualizacion = actualizar_modelo_gold()

    creacion >> actualizacion


logiweather_gold()