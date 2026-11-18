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
from datetime import date, datetime, timedelta, timezone

import requests
from airflow.sdk import dag, task
from sqlalchemy import text

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_OPENMETEO  # noqa: E402
from common.db import get_engine  # noqa: E402

URL_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
URL_FORECAST = "https://api.open-meteo.com/v1/forecast"
FECHA_INICIO = date(2021, 1, 1)   # años completos 2021-2025 para comparar meses
DEMORA_DIAS = 5                   # la API histórica tiene ~5 días de demora
DIAS_ANTERIORES_PRONOSTICO = 7    # la API de pronóstico devuelve 7 días anteriores a la fecha de hoy

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
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bronze.clima_horario (
                    id BIGSERIAL PRIMARY KEY,
                    destino TEXT NOT NULL,
                    fecha_hora TIMESTAMPTZ NOT NULL,
                    temperatura_2m NUMERIC,
                    precipitacion NUMERIC,
                    rafaga_viento_10m NUMERIC,
                    source TEXT NOT NULL,
                    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (destino, fecha_hora)
                )
        """))
        

    @task
    def calcular_rangos():
        with get_engine().connect() as conn:
            filas = conn.execute(text("""
                SELECT destino, MAX(fecha_hasta) AS ultima
                FROM bronze.openmeteo
                WHERE source = :origen
                GROUP BY destino
            """), {"origen": URL_HISTORICO}).fetchall()
        ultimas = {fila.destino: fila.ultima for fila in filas}

        rangos = {}
        for destino in DESTINOS:
            rango = calcular_rango(ultimas.get(destino), date.today())
            if rango:
                rangos[destino] = [rango[0].isoformat(), rango[1].isoformat()]
        print("Rangos a pedir:", rangos or "ninguno, ya está al día")
        return rangos

    # Pide y guarda en la misma tarea: el JSON de 5 años no debe viajar por XCom.
    #Extracción historica: solo consulta los días nuevos
    @task
    def extraer_y_cargar(rangos):
        for destino, (inicio, fin) in rangos.items():
            lat, lon = DESTINOS[destino]
            respuesta = requests.get(URL_HISTORICO, timeout=120, params={
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
                    "source": URL_HISTORICO,
                })
            print(f"{destino}: historico cargado {inicio} a {fin}")

        # 2. Extracción de Forecast: consulta los últimos días en cada corrida.
        for destino, (lat, lon) in DESTINOS.items():

            respuesta = requests.get(URL_FORECAST, timeout=120, params={
                "latitude": lat,
                "longitude": lon,
                "past_days": DIAS_ANTERIORES_PRONOSTICO,
                "forecast_days": 0,
                "daily": ",".join(VARIABLES),
                "timezone": "auto",
            })
            respuesta.raise_for_status()

            datos = respuesta.json()
            fechas = datos["daily"]["time"]

            if not fechas:
                print(f"{destino}: Forecast no devolvió fechas")
                continue

            with get_engine().begin() as conn:
                conn.execute(text("""
                    INSERT INTO bronze.openmeteo
                        (destino, latitud, longitud, fecha_desde, fecha_hasta, respuesta_json, source)
                    VALUES
                        (:destino, :lat, :lon, :inicio, :fin, CAST(:respuesta AS JSONB), :origen)
                """), {
                    "destino": destino,
                    "lat": lat,
                    "lon": lon,
                    "inicio": fechas[0],
                    "fin": fechas[-1],
                    "respuesta": json.dumps(datos),
                    "origen": URL_FORECAST,
                })

            print(f"{destino}: Forecast cargado {fechas[0]} a {fechas[-1]}")


    
    @task
    def cargar_forecast_horario():
        from datetime import timezone

        # Última hora completada en UTC.
        hora_actual_utc = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        ultima_hora_completa = hora_actual_utc - timedelta(hours=1)

        # Procesar cada destino por separado.
        for destino, (lat, lon) in DESTINOS.items():

            respuesta = requests.get(
                URL_FORECAST,
                timeout=120,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "past_days": 7,
                    "forecast_days": 1,
                    "hourly": (
                        "temperature_2m,"
                        "precipitation,"
                        "wind_gusts_10m"
                    ),
                    "timezone": "GMT",
                },
            )
            respuesta.raise_for_status()

            datos = respuesta.json()["hourly"]
            horas = datos["time"]
            registros = []

            for i, hora_texto in enumerate(horas):
                fecha_hora = datetime.strptime(
                    hora_texto, "%Y-%m-%dT%H:%M"
                ).replace(tzinfo=timezone.utc)

                # No guardar horas futuras ni la hora en curso.
                if fecha_hora > ultima_hora_completa:
                    continue

                # Recuperar los últimos 7 días para cubrir
                # el retraso de la API histórica.
                if fecha_hora < hora_actual_utc - timedelta(days=7):
                    continue

                registros.append({
                    "destino": destino,
                    "fecha_hora": fecha_hora,
                    "temperatura": datos["temperature_2m"][i],
                    "precipitacion": datos["precipitation"][i],
                    "rafaga": datos["wind_gusts_10m"][i],
                    "source": URL_FORECAST,
                })

            # Guardar los registros de ESTE destino.
            if registros:
                with get_engine().begin() as conn:
                    conn.execute(text("""
                        INSERT INTO bronze.clima_horario (
                            destino,
                            fecha_hora,
                            temperatura_2m,
                            precipitacion,
                            rafaga_viento_10m,
                            source
                        )
                        VALUES (
                            :destino,
                            :fecha_hora,
                            :temperatura,
                            :precipitacion,
                            :rafaga,
                            :source
                        )
                        ON CONFLICT (destino, fecha_hora)
                        DO NOTHING
                    """), registros)

            print(
                f"{destino}: {len(registros)} horas revisadas "
                "(sin insertar duplicados)"
            )


    @task(outlets=[BRONZE_OPENMETEO])
    def finalizar_bronze():
        print("Bronze finalizado. Silver puede comenzar.")

    tabla = crear_tabla()
    rangos = calcular_rangos()
    tabla >> rangos
    extraccion = extraer_y_cargar(rangos)
    carga_horaria = cargar_forecast_horario()
    tabla >> carga_horaria
    fin = finalizar_bronze()
    [extraccion, carga_horaria] >> fin


g06_bronze()