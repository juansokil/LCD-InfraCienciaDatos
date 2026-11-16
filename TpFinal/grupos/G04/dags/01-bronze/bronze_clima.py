import os
import json
import uuid
import logging
import requests

from pathlib import Path
from datetime import datetime, timezone, timedelta
from hashlib import sha256

from sqlalchemy import text
from airflow.sdk import dag, task, get_current_context

from common.db import get_warehouse_engine
from common.assets import BRONZE_CLIMA


# ==========================================================
# CONFIGURACION OPEN-METEO
# ==========================================================

API_URL = "https://api.open-meteo.com/v1/forecast"

API_CURRENT = (
    "temperature_2m,relative_humidity_2m,"
    "apparent_temperature,wind_speed_10m"
)

API_DAILY = (
    "temperature_2m_max,temperature_2m_min,"
    "apparent_temperature_max,precipitation_sum,"
    "wind_speed_10m_max"
)

API_TIMEZONE = "America/Argentina/Buenos_Aires"
API_FORECAST_DAYS = 7
API_TEMPERATURE_UNIT = "celsius"
API_WIND_SPEED_UNIT = "kmh"
API_PRECIPITATION_UNIT = "mm"
API_TIMEOUT_SECONDS = 30

DAG_TAGS = ["tpfinal", "open-meteo", "G04"]
DAG_CATCHUP = False
DAG_MAX_ACTIVE_RUNS = 1
DAG_RETRIES = 2
DAG_RETRY_DELAY_MINUTES = 2

logger = logging.getLogger(__name__)


# ==========================================================
# 1. CARGAR CIUDADES
# ==========================================================

def cargar_ciudades() -> list[dict]:
    ruta_base = Path(os.environ["PROJECT_ROOT"])
    ruta = ruta_base / "config" / "ciudades.json"

    with open(ruta, "r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    ciudades = datos["ciudades"]

    if len(ciudades) != 5:
        raise ValueError("Deben existir exactamente 5 ciudades")

    ids = {ciudad["id"] for ciudad in ciudades}

    ids_esperados = {
        "buenos_aires",
        "cordoba",
        "mendoza",
        "bariloche",
        "salta"
    }

    if ids != ids_esperados:
        raise ValueError("Las ciudades no coinciden con el contrato")

    return ciudades


# ==========================================================
# 2. CONSTRUIR PARAMETROS
# ==========================================================

def construir_params(
    latitud: float,
    longitud: float
) -> dict:

    return {
        "latitude": latitud,
        "longitude": longitud,
        "current": API_CURRENT,
        "daily": API_DAILY,
        "timezone": API_TIMEZONE,
        "forecast_days": API_FORECAST_DAYS,
        "temperature_unit": API_TEMPERATURE_UNIT,
        "wind_speed_unit": API_WIND_SPEED_UNIT,
        "precipitation_unit": API_PRECIPITATION_UNIT
    }


# ==========================================================
# 3. VALIDAR RESPUESTA
# ==========================================================

def _validar_respuesta(datos: dict) -> None:

    if not isinstance(datos, dict):
        raise ValueError("La respuesta no es un objeto JSON")

    secciones = [
        "current",
        "daily",
        "current_units",
        "daily_units"
    ]

    for seccion in secciones:
        if not isinstance(datos.get(seccion), dict):
            raise ValueError(f"Falta o es invalida: {seccion}")

    actuales = [
        "time",
        "temperature_2m",
        "relative_humidity_2m"
    ]

    diarias = [
        "time",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum"
    ]

    for variable in actuales:
        if variable not in datos["current"]:
            raise ValueError(
                f"Falta variable actual: {variable}"
            )

    for variable in diarias:
        if variable not in datos["daily"]:
            raise ValueError(
                f"Falta variable diaria: {variable}"
            )

    # Todos los arrays diarios deben tener siete posiciones.
    for variable, valores in datos["daily"].items():
        if not isinstance(valores, list):
            raise ValueError(
                f"La variable {variable} no es un array"
            )

        if len(valores) != API_FORECAST_DAYS:
            raise ValueError(
                f"Pronostico incompleto: {variable}"
            )

    # Comprobamos que las unidades sean las solicitadas.
    unidades_actuales = {
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "apparent_temperature": "°C",
        "wind_speed_10m": "km/h"
    }

    unidades_diarias = {
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "apparent_temperature_max": "°C",
        "precipitation_sum": "mm",
        "wind_speed_10m_max": "km/h"
    }

    for variable, unidad in unidades_actuales.items():
        if variable in datos["current"]:
            if datos["current_units"].get(variable) != unidad:
                raise ValueError(
                    f"Unidad inesperada: {variable}"
                )

    for variable, unidad in unidades_diarias.items():
        if variable in datos["daily"]:
            if datos["daily_units"].get(variable) != unidad:
                raise ValueError(
                    f"Unidad inesperada: {variable}"
                )


# ==========================================================
# 4. CONSULTAR OPEN-METEO
# ==========================================================

def consultar_open_meteo(params: dict) -> bytes:

    respuesta = requests.get(
        API_URL,
        params=params,
        timeout=API_TIMEOUT_SECONDS
    )

    respuesta.raise_for_status()

    payload_bytes = respuesta.content

    try:
        datos = json.loads(payload_bytes)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("Open-Meteo devolvio JSON invalido") from error

    _validar_respuesta(datos)

    # No reformateamos el JSON original.
    return payload_bytes


# ==========================================================
# 5. GENERAR IDENTIFICADOR DETERMINISTA
# ==========================================================

def generar_consulta_id(
    run_id: str,
    ciudad_id: str
) -> str:

    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"open-meteo:{run_id}:{ciudad_id}"
        )
    )


# ==========================================================
# 6. GUARDAR JSON ORIGINAL
# ==========================================================

def guardar_raw(
    payload_bytes: bytes,
    consulta_id: str,
    ingested_at
) -> str:

    if ingested_at.tzinfo is None:
        raise ValueError("ingested_at debe tener zona horaria")

    ruta_base = Path(os.environ["PROJECT_ROOT"])

    carpeta = (
        ruta_base
        / "data"
        / "raw"
        / f"ds={ingested_at.astimezone(timezone.utc):%Y-%m-%d}"
    )

    carpeta.mkdir(parents=True, exist_ok=True)

    ruta = carpeta / f"{consulta_id}.json"

    try:
        with open(ruta, "xb") as archivo:
            archivo.write(payload_bytes)

    except FileExistsError:
        if ruta.read_bytes() != payload_bytes:
            raise ValueError(
                "El archivo raw existe con otro contenido"
            )

    return str(ruta)


# ==========================================================
# 7. BUSCAR SNAPSHOT YA GUARDADO
# ==========================================================

def _buscar_snapshot(run_id: str, ciudad_id: str):

    consulta = text("""
        SELECT raw_path, payload_sha256
        FROM bronze.clima_raw
        WHERE run_id = :run_id
          AND ciudad_id = :ciudad_id
    """)

    engine = get_warehouse_engine()

    with engine.connect() as conexion:
        resultado = conexion.execute(
            consulta,
            {
                "run_id": run_id,
                "ciudad_id": ciudad_id
            }
        )

        fila = resultado.mappings().one_or_none()

    return dict(fila) if fila else None


# ==========================================================
# 8. INSERTAR SNAPSHOT EN POSTGRESQL
# ==========================================================

def insertar_snapshot(registro: dict) -> bool:

    consulta = text("""
        INSERT INTO bronze.clima_raw (
            consulta_id,
            run_id,
            ciudad_id,
            ciudad_nombre,
            latitud,
            longitud,
            ingested_at,
            source_url,
            raw_path,
            payload_sha256,
            payload
        )
        VALUES (
            CAST(:consulta_id AS UUID),
            :run_id,
            :ciudad_id,
            :ciudad_nombre,
            :latitud,
            :longitud,
            :ingested_at,
            :source_url,
            :raw_path,
            :payload_sha256,
            CAST(:payload AS JSONB)
        )
        ON CONFLICT (run_id, ciudad_id) DO NOTHING
        RETURNING consulta_id
    """)

    parametros = {
        **registro,
        "payload": json.dumps(registro["payload"])
    }

    engine = get_warehouse_engine()

    with engine.begin() as conexion:
        resultado = conexion.execute(
            consulta,
            parametros
        )

        return resultado.scalar_one_or_none() is not None


# ==========================================================
# 9. EJECUTAR INGESTA COMPLETA
# ==========================================================

def ejecutar_ingesta(run_id: str) -> dict:

    ciudades = cargar_ciudades()

    ciudades_ok = 0
    nuevas = 0
    repetidas = 0

    ruta_base = Path(os.environ["PROJECT_ROOT"])

    for ciudad in ciudades:

        ciudad_id = ciudad["id"]

        try:
            consulta_id = generar_consulta_id(
                run_id,
                ciudad_id
            )

            # Primero verificamos PostgreSQL.
            existente = _buscar_snapshot(
                run_id,
                ciudad_id
            )

            if existente is not None:

                ruta_existente = Path(existente["raw_path"])

                if not ruta_existente.is_file():
                    raise FileNotFoundError(
                        f"No existe raw: {ruta_existente}"
                    )

                hash_actual = sha256(
                    ruta_existente.read_bytes()
                ).hexdigest()

                if hash_actual != existente["payload_sha256"]:
                    raise ValueError(
                        f"Hash raw incorrecto: {ciudad_id}"
                    )

                repetidas += 1
                ciudades_ok += 1

                logger.info(
                    "Snapshot ya existente: %s",
                    ciudad_id
                )
                continue

            # Si falló antes el INSERT, reutilizamos
            # el archivo raw sin volver a consultar la API.
            carpeta_raw = ruta_base / "data" / "raw"

            archivos = list(
                carpeta_raw.glob(
                    f"ds=*/{consulta_id}.json"
                )
            )

            if len(archivos) > 1:
                raise ValueError(
                    f"Multiples archivos raw: {consulta_id}"
                )

            if archivos:
                ruta = str(archivos[0])
                payload_bytes = archivos[0].read_bytes()

                _validar_respuesta(
                    json.loads(payload_bytes)
                )

                ingested_at = datetime.fromtimestamp(
                    archivos[0].stat().st_mtime,
                    tz=timezone.utc
                )

            else:
                params = construir_params(
                    ciudad["latitud"],
                    ciudad["longitud"]
                )

                payload_bytes = consultar_open_meteo(params)

                ingested_at = datetime.now(timezone.utc)

                ruta = guardar_raw(
                    payload_bytes,
                    consulta_id,
                    ingested_at
                )

            registro = {
                "consulta_id": consulta_id,
                "run_id": run_id,
                "ciudad_id": ciudad_id,
                "ciudad_nombre": ciudad["nombre"],
                "latitud": ciudad["latitud"],
                "longitud": ciudad["longitud"],
                "ingested_at": ingested_at,
                "source_url": API_URL,
                "raw_path": ruta,
                "payload_sha256": sha256(
                    payload_bytes
                ).hexdigest(),
                "payload": json.loads(payload_bytes)
            }

            insertado = insertar_snapshot(registro)

            if insertado:
                nuevas += 1
            else:
                repetidas += 1

            ciudades_ok += 1

            logger.info(
                "Ciudad procesada: %s",
                ciudad["nombre"]
            )

        except Exception:
            logger.exception(
                "Fallo la ingesta de %s",
                ciudad_id
            )
            raise

    if ciudades_ok != 5:
        raise RuntimeError("Lote Bronze incompleto")

    resumen = {
        "ciudades_ok": ciudades_ok,
        "nuevas": nuevas,
        "repetidas": repetidas
    }

    logger.info("Resumen Bronze: %s", resumen)

    return resumen


# ==========================================================
# 10. DAG DE AIRFLOW
# ==========================================================

@dag(
    dag_id="bronze_clima",
    schedule="@hourly",
    start_date=datetime(2026, 11, 4, tzinfo=timezone.utc),
    catchup=DAG_CATCHUP,
    max_active_runs=DAG_MAX_ACTIVE_RUNS,
    is_paused_upon_creation=False,
    tags=DAG_TAGS
)
def bronze_clima():

    @task(
        task_id="ingestar_clima",
        retries=DAG_RETRIES,
        retry_delay=timedelta(
            minutes=DAG_RETRY_DELAY_MINUTES
        ),
        outlets=[BRONZE_CLIMA]
    )
    def _task_ingesta():

        contexto = get_current_context()
        run_id = contexto["run_id"]

        return ejecutar_ingesta(run_id)

    _task_ingesta()


bronze_clima_dag = bronze_clima()
