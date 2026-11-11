
"""
LogiWeather - DAG Bronze
TP Final Infraestructura para Ciencia de Datos - Grupo 10

Extrae pronósticos diarios de Open-Meteo y guarda
las respuestas originales en PostgreSQL.
"""

import json
import logging
import os
from datetime import timedelta
from pathlib import Path

import pendulum
import psycopg2
import requests

from airflow.sdk import dag, task, get_current_context
from psycopg2.extras import Json
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

API_URL = "https://api.open-meteo.com/v1/forecast"

CONFIG_CIUDADES = Path("/opt/airflow/config/ciudades.json")

VARIABLES_DIARIAS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "weather_code",
]


def conectar_warehouse():
    """Abre una conexión a la base PostgreSQL del proyecto."""
    return psycopg2.connect(
        host=os.environ["WAREHOUSE_HOST"],
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
        port=5432,
        connect_timeout=10,
    )


@dag(
    dag_id="logiweather_bronze",
    description="Extrae pronósticos de Open-Meteo hacia Bronze",
    start_date=pendulum.datetime(2026, 11, 8, tz="UTC"),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["G10", "LogiWeather", "Bronze", "Open-Meteo"],
)
def logiweather_bronze():

    @task
    def crear_tabla_bronze():
        """Crea la tabla de destino si todavía no existe."""

        sql = """
        CREATE SCHEMA IF NOT EXISTS bronze;

        CREATE TABLE IF NOT EXISTS bronze.pronosticos_raw (
            id BIGSERIAL PRIMARY KEY,
            ciudad_id VARCHAR(50) NOT NULL,
            ciudad VARCHAR(100) NOT NULL,
            latitud DOUBLE PRECISION NOT NULL,
            longitud DOUBLE PRECISION NOT NULL,
            fuente VARCHAR(50) NOT NULL,
            run_id TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL
                DEFAULT CURRENT_TIMESTAMP,
            payload JSONB NOT NULL,
            CONSTRAINT uq_bronze_ciudad_run
                UNIQUE (ciudad_id, run_id)
        );
        """

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql)

        logging.info("Tabla bronze.pronosticos_raw preparada.")

    @task
    def extraer_pronosticos():
        """Consulta Open-Meteo y almacena el JSON original."""

        with CONFIG_CIUDADES.open(
            "r", encoding="utf-8"
        ) as archivo:
            ciudades = json.load(archivo)["ciudades"]

        context = get_current_context()
        run_id = context["run_id"]

        registros = 0

        with conectar_warehouse() as conexion:
            with conexion.cursor() as cursor:

                for ciudad in ciudades:

                    parametros = {
                        "latitude": ciudad["latitud"],
                        "longitude": ciudad["longitud"],
                        "daily": ",".join(VARIABLES_DIARIAS),
                        "timezone": ciudad["timezone"],
                        "forecast_days": 7,
                    }

                    respuesta = requests.get(
                        API_URL,
                        params=parametros,
                        timeout=30,
                    )
                    respuesta.raise_for_status()

                    datos = respuesta.json()

                    if "daily" not in datos:
                        raise ValueError(
                            f"Respuesta sin datos diarios: "
                            f"{ciudad['nombre']}"
                        )

                    fechas = datos["daily"].get("time", [])

                    if len(fechas) != 7:
                        raise ValueError(
                            f"Pronóstico incompleto para "
                            f"{ciudad['nombre']}"
                        )

                    for variable in VARIABLES_DIARIAS:
                        valores = datos["daily"].get(variable)

                        if not isinstance(valores, list) or len(valores) != 7:
                            raise ValueError(
                                f"Variable incompleta: {variable} "
                                f"en {ciudad['nombre']}"
                            )

                    cursor.execute(
                        """
                        INSERT INTO bronze.pronosticos_raw (
                            ciudad_id,
                            ciudad,
                            latitud,
                            longitud,
                            fuente,
                            run_id,
                            payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ciudad_id, run_id)
                        DO NOTHING;
                        """,
                        (
                            ciudad["id"],
                            ciudad["nombre"],
                            ciudad["latitud"],
                            ciudad["longitud"],
                            "Open-Meteo",
                            run_id,
                            Json(datos),
                        ),
                    )

                    registros += cursor.rowcount

                    logging.info(
                        "Ciudad procesada: %s - %s días",
                        ciudad["nombre"],
                        len(fechas),
                    )

        logging.info(
            "Extracción finalizada. Nuevos registros: %s",
            registros,
        )

    preparacion = crear_tabla_bronze()
    extraccion = extraer_pronosticos()

    disparar_silver = TriggerDagRunOperator(
        task_id="disparar_silver",
        trigger_dag_id="logiweather_silver",
        wait_for_completion=False,
    )

    preparacion >> extraccion >> disparar_silver


logiweather_bronze()
