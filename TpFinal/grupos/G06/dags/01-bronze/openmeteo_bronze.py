"""g06_bronze — ingesta incremental del histórico diario de Open-Meteo.

Guarda la respuesta cruda de la API histórica (archive-api) en
bronze.openmeteo: una fila por destino y corrida, con el JSON tal cual llega.

Carga incremental:
- Primer arranque (tabla vacía): trae desde FECHA_INICIO hasta hoy - DEMORA_DIAS.
- Corridas siguientes: solo los días que faltan desde la última fecha cargada.
- Si no hay días nuevos, no llama a la API.

Al terminar emite BRONZE_OPENMETEO, que dispara g06_silver.
"""
import json
import sys
from datetime import date, datetime, timedelta

import requests
from airflow.sdk import dag, task
from sqlalchemy import text

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_OPENMETEO  # noqa: E402
from common.db import get_engine  # noqa: E402

URL = "https://archive-api.open-meteo.com/v1/archive"
FECHA_INICIO = date(2021, 1, 1)   # años completos 2021-2025 para comparar meses
DEMORA_DIAS = 5                   # la API histórica tiene ~5 días de demora

# Los nombres tienen que coincidir con gold.dim_ciudad y el dashboard.
DESTINOS = {
    "Purmamarca": (-23.7500, -65.5000),
    "Bariloche": (-41.1335, -71.3103),
    "Puerto Iguazú": (-25.5991, -54.5736),
}

VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "daylight_duration",
    "wind_gusts_10m_max",
]


def calcular_rango(ultima_fecha, hoy):
    """Devuelve (inicio, fin) a pedir, o None si ya está al día."""
    fin = hoy - timedelta(days=DEMORA_DIAS)
    if ultima_fecha is None:                  # primer arranque
        inicio = FECHA_INICIO
    else:                                     # incremental
        inicio = ultima_fecha + timedelta(days=1)
    if inicio > fin:                          # no hay días nuevos
        return None
    return inicio, fin


@dag(
    dag_id="g06_bronze",
    start_date=datetime(2026, 1, 1),
    schedule="0 * * * *",          # cada hora; si no hay días nuevos, no pide nada
    catchup=False,                 # no correr la historia desde start_date
    is_paused_upon_creation=False, # nace activo: nadie tiene que despausarlo
    tags=["g06", "bronze"],
)
def g06_bronze():

    @task
    def crear_tabla():
        with get_engine().begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bronze.openmeteo (
                    id             BIGSERIAL PRIMARY KEY,
                    destino        TEXT        NOT NULL,
                    latitud        NUMERIC     NOT NULL,
                    longitud       NUMERIC     NOT NULL,
                    fecha_desde    DATE        NOT NULL,
                    fecha_hasta    DATE        NOT NULL,
                    respuesta_json JSONB       NOT NULL,
                    source         TEXT        NOT NULL,
                    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))

    @task
    def calcular_rangos():
        with get_engine().connect() as conn:
            filas = conn.execute(text("""
                SELECT destino, MAX(fecha_hasta) AS ultima
                FROM bronze.openmeteo
                GROUP BY destino
            """)).fetchall()
        ultimas = {fila.destino: fila.ultima for fila in filas}

        rangos = {}
        for destino in DESTINOS:
            rango = calcular_rango(ultimas.get(destino), date.today())
            if rango:
                rangos[destino] = [rango[0].isoformat(), rango[1].isoformat()]
        print("Rangos a pedir:", rangos or "ninguno, ya está al día")
        return rangos

    # Pide y guarda en la misma tarea: el JSON de 5 años no debe viajar por XCom.
    @task(outlets=[BRONZE_OPENMETEO])
    def extraer_y_cargar(rangos):
        for destino, (inicio, fin) in rangos.items():
            lat, lon = DESTINOS[destino]
            respuesta = requests.get(URL, timeout=120, params={
                "latitude": lat,
                "longitude": lon,
                "start_date": inicio,
                "end_date": fin,
                "daily": ",".join(VARIABLES),
                "timezone": "auto",   # zona horaria de cada destino (contrato Silver)
            })
            respuesta.raise_for_status()

            with get_engine().begin() as conn:
                conn.execute(text("""
                    INSERT INTO bronze.openmeteo
                        (destino, latitud, longitud, fecha_desde, fecha_hasta, respuesta_json, source)
                    VALUES
                        (:destino, :lat, :lon, :inicio, :fin, CAST(:respuesta AS JSONB), :source)
                """), {
                    "destino": destino, "lat": lat, "lon": lon,
                    "inicio": inicio, "fin": fin,
                    "respuesta": json.dumps(respuesta.json()),
                    "source": URL,
                })
            print(f"{destino}: cargado {inicio} a {fin}")

    tabla = crear_tabla()
    rangos = calcular_rangos()
    tabla >> rangos
    extraer_y_cargar(rangos)


g06_bronze()