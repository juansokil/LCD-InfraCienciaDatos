
"""
LogiWeather - DAG Silver
TP Final - Grupo 10

Transforma los JSON de Bronze mediante SQL en PostgreSQL.
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
    dag_id="logiweather_silver",
    description="Transformación SQL de pronósticos Bronze a Silver",
    start_date=pendulum.datetime(2026, 11, 8, tz="UTC"),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["G10", "LogiWeather", "Silver", "SQL"],
)
def logiweather_silver():

    @task
    def crear_tabla_silver():
        sql = """
        CREATE SCHEMA IF NOT EXISTS silver;

        CREATE TABLE IF NOT EXISTS silver.pronosticos_diarios (
            id BIGSERIAL PRIMARY KEY,
            bronze_id BIGINT NOT NULL,
            ciudad_id VARCHAR(50) NOT NULL,
            ciudad VARCHAR(100) NOT NULL,

            fecha_consulta DATE NOT NULL,
            fecha_pronostico DATE NOT NULL,

            temperatura_max NUMERIC(6,2) NOT NULL,
            temperatura_min NUMERIC(6,2) NOT NULL,

            probabilidad_lluvia INTEGER NOT NULL
                CHECK (probabilidad_lluvia BETWEEN 0 AND 100),

            precipitacion_mm NUMERIC(10,2) NOT NULL
                CHECK (precipitacion_mm >= 0),

            weather_code INTEGER NOT NULL
                CHECK (weather_code >= 0),

            ingested_at TIMESTAMPTZ NOT NULL,
            procesado_at TIMESTAMPTZ NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT chk_temperaturas
                CHECK (temperatura_min <= temperatura_max),

            CONSTRAINT uq_silver_bronze_fecha
                UNIQUE (bronze_id, fecha_pronostico)
        );
        """

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql)

        logging.info("Tabla Silver preparada.")

    @task
    def transformar_bronze_a_silver():

        sql = """
        WITH registros AS (
            SELECT
                b.*,
                b.payload->'daily' AS diario
            FROM bronze.pronosticos_raw b
        ),
        validacion AS (
            SELECT
                id,
                (
                    SELECT COUNT(*)
                    FROM (
                        VALUES
                            ('time'),
                            ('temperature_2m_max'),
                            ('temperature_2m_min'),
                            ('precipitation_probability_max'),
                            ('precipitation_sum'),
                            ('weather_code')
                    ) AS campos(nombre)
                    WHERE
                        jsonb_typeof(diario->campos.nombre) = 'array'
                        AND jsonb_array_length(
                            diario->campos.nombre
                        ) = 7
                ) AS campos_correctos
            FROM registros
        )
        SELECT COUNT(*)
        FROM validacion
        WHERE campos_correctos <> 6;
        """

        transformacion = """
        INSERT INTO silver.pronosticos_diarios (
            bronze_id,
            ciudad_id,
            ciudad,
            fecha_consulta,
            fecha_pronostico,
            temperatura_max,
            temperatura_min,
            probabilidad_lluvia,
            precipitacion_mm,
            weather_code,
            ingested_at
        )
        SELECT
            b.id,
            b.ciudad_id,
            b.ciudad,

            (b.ingested_at AT TIME ZONE 'UTC')::DATE,

            f.fecha_txt::DATE,

            -- Temperatura máxima
            (b.payload->'daily'->'temperature_2m_max'
                ->>((f.pos - 1)::INTEGER))::NUMERIC(6,2),

            -- Temperatura mínima
            (b.payload->'daily'->'temperature_2m_min'
                ->>((f.pos - 1)::INTEGER))::NUMERIC(6,2),

            -- Probabilidad de lluvia
            (b.payload->'daily'->'precipitation_probability_max'
                ->>((f.pos - 1)::INTEGER))::INTEGER,

            -- Precipitación acumulada
            (b.payload->'daily'->'precipitation_sum'
                ->>((f.pos - 1)::INTEGER))::NUMERIC(10,2),

            -- Código meteorológico
            (b.payload->'daily'->'weather_code'
                ->>((f.pos - 1)::INTEGER))::INTEGER,

            b.ingested_at

        FROM bronze.pronosticos_raw b

        CROSS JOIN LATERAL jsonb_array_elements_text(
            b.payload->'daily'->'time'
        ) WITH ORDINALITY AS f(fecha_txt, pos)

        ON CONFLICT (bronze_id, fecha_pronostico)
        DO NOTHING;
        """

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:

                cursor.execute(sql)
                invalidos = cursor.fetchone()[0]

                if invalidos:
                    raise ValueError(
                        f"{invalidos} registros Bronze "
                        "tienen arrays faltantes o incompletos."
                    )

                cursor.execute(transformacion)
                insertados = cursor.rowcount

        logging.info(
            "Silver: %s filas nuevas insertadas.",
            insertados,
        )

    preparacion = crear_tabla_silver()
    transformacion = transformar_bronze_a_silver()

    preparacion >> transformacion


logiweather_silver()
