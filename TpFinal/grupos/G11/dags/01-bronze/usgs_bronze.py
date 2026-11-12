"""
DAG usgs_bronze - Capa Bronze: ingesta cruda de sismos desde la API de USGS.

    API USGS (GeoJSON) --> data/raw/usgs/ds=AAAA-MM-DD/HHMMSS_<feed>.geojson
                       --> bronze.usgs_sismos  (append, con ingested_at)

DECISIONES
----------
* Fuente: los "feeds" GeoJSON de USGS (sin auth, sin key):
    https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
  - all_month: todos los sismos de los ultimos 30 dias (~10.000 eventos)
  - all_day:   los de las ultimas 24 h (~300 eventos)

* Primera corrida = all_month. Si bronze esta vacio, bajamos el mes entero:
  asi, apenas se levanta el stack, el dashboard ya tiene 30 dias de historia.
  Despues bajamos all_day cada 30 minutos. Las 24 h se solapan entre
  corridas A PROPOSITO: USGS corrige los sismos despues de publicarlos
  (la magnitud, el estado automatic -> reviewed). Volver a bajarlos es lo que
  nos trae esas correcciones; Silver se queda con la ultima version.

* Bronze no limpia ni deduplica: guarda TODO lo que llego, tal cual (mismos
  nombres y tipos que la API: el tiempo sigue en milisegundos). Cada fila
  lleva su auditoria: ingested_at, feed y archivo crudo de donde salio.

* El crudo (el archivo .geojson) se guarda ademas de la tabla: si manana
  cambiamos que columnas extraemos, podemos reprocesar sin volver a llamar a
  la API.

* Corre solo al levantar el stack: `CronTriggerTimetable(run_immediately=True)`
  le dice a Airflow que, al crear el DAG, dispare ya la corrida mas reciente
  en vez de esperar al proximo "y media".
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import dag, task
from airflow.timetables.trigger import CronTriggerTimetable

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_SISMOS  # noqa: E402
from common.db import ejecutar, transaccion, valor  # noqa: E402

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson"
RAW_DIR = Path("/opt/airflow/data/raw/usgs")

DDL_BRONZE = """
CREATE TABLE IF NOT EXISTS bronze.usgs_sismos (
    -- identificador del evento en USGS
    event_id      TEXT,
    -- properties del GeoJSON, con los mismos nombres y tipos que la API
    mag           DOUBLE PRECISION,
    place         TEXT,
    time_ms       BIGINT,          -- epoch en milisegundos (UTC)
    updated_ms    BIGINT,          -- ultima modificacion del evento en USGS
    url           TEXT,
    felt          INTEGER,
    cdi           DOUBLE PRECISION,
    mmi           DOUBLE PRECISION,
    alert         TEXT,
    status        TEXT,
    tsunami       INTEGER,
    sig           INTEGER,
    net           TEXT,
    code          TEXT,
    nst           INTEGER,
    dmin          DOUBLE PRECISION,
    rms           DOUBLE PRECISION,
    gap           DOUBLE PRECISION,
    mag_type      TEXT,
    event_type    TEXT,
    title         TEXT,
    -- geometry.coordinates = [longitud, latitud, profundidad_km]
    longitude     DOUBLE PRECISION,
    latitude      DOUBLE PRECISION,
    depth         DOUBLE PRECISION,
    -- auditoria de la ingesta
    feed          TEXT,
    feed_generated_ms BIGINT,      -- cuando genero USGS el feed
    archivo_raw   TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_usgs_event ON bronze.usgs_sismos (event_id);
"""

COLUMNAS = [
    "event_id", "mag", "place", "time_ms", "updated_ms", "url", "felt", "cdi",
    "mmi", "alert", "status", "tsunami", "sig", "net", "code", "nst", "dmin",
    "rms", "gap", "mag_type", "event_type", "title", "longitude", "latitude",
    "depth", "feed", "feed_generated_ms", "archivo_raw", "ingested_at",
]


def _fila(feature: dict, feed: str, generado, archivo: str, ingested_at) -> tuple:
    """Aplana un Feature del GeoJSON a una tupla con el orden de COLUMNAS."""
    p = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or [None, None, None]
    coords = (list(coords) + [None, None, None])[:3]
    return (
        feature.get("id"), p.get("mag"), p.get("place"), p.get("time"),
        p.get("updated"), p.get("url"), p.get("felt"), p.get("cdi"),
        p.get("mmi"), p.get("alert"), p.get("status"), p.get("tsunami"),
        p.get("sig"), p.get("net"), p.get("code"), p.get("nst"),
        p.get("dmin"), p.get("rms"), p.get("gap"), p.get("magType"),
        p.get("type"), p.get("title"), coords[0], coords[1], coords[2],
        feed, generado, archivo, ingested_at,
    )


@dag(
    dag_id="usgs_bronze",
    schedule=CronTriggerTimetable("*/30 * * * *", timezone="UTC", run_immediately=True),
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={"retries": 3, "retry_delay": timedelta(minutes=1)},
    tags=["g11", "bronze", "usgs"],
    doc_md=__doc__,
)
def usgs_bronze():

    @task
    def elegir_feed() -> str:
        """Crea la tabla si no existe y decide que feed bajar."""
        ejecutar(DDL_BRONZE)
        filas = valor("SELECT count(*) FROM bronze.usgs_sismos")
        feed = "all_month" if filas == 0 else "all_day"
        print(f"bronze.usgs_sismos tiene {filas} filas -> bajamos '{feed}'")
        return feed

    @task
    def descargar(feed: str) -> dict:
        """Baja el feed y guarda el payload TAL CUAL en la zona raw.

        Por XCom pasa solo la RUTA del archivo, no el contenido: el feed
        mensual pesa ~7 MB y XCom vive en la base de metadatos de Airflow.
        """
        import requests

        resp = requests.get(FEED_URL.format(feed=feed), timeout=90)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("type") != "FeatureCollection" or "features" not in payload:
            raise ValueError(f"Respuesta inesperada de USGS: claves {list(payload)[:5]}")

        ahora = datetime.now(timezone.utc)
        carpeta = RAW_DIR / f"ds={ahora:%Y-%m-%d}"
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / f"{ahora:%H%M%S}_{feed}.geojson"
        archivo.write_bytes(resp.content)

        n = len(payload["features"])
        print(f"{feed}: {n} eventos -> {archivo}")
        return {
            "feed": feed,
            "archivo": str(archivo),
            "eventos": n,
            "generado_ms": (payload.get("metadata") or {}).get("generated"),
        }

    @task(outlets=[BRONZE_SISMOS])
    def cargar_bronze(info: dict) -> int:
        """Lee el crudo y lo agrega (append) a bronze.usgs_sismos.

        `outlets=[BRONZE_SISMOS]`: cuando esta tarea termina OK, Airflow marca
        el asset como actualizado y usgs_silver arranca solo.
        """
        from psycopg2.extras import execute_values

        payload = json.loads(Path(info["archivo"]).read_text(encoding="utf-8"))
        ingested_at = datetime.now(timezone.utc)
        relativo = info["archivo"].replace("/opt/airflow/", "")
        filas = [
            _fila(f, info["feed"], info["generado_ms"], relativo, ingested_at)
            for f in payload["features"]
        ]

        with transaccion() as cur:
            execute_values(
                cur,
                f"INSERT INTO bronze.usgs_sismos ({', '.join(COLUMNAS)}) VALUES %s",
                filas,
                page_size=1000,
            )
            cur.execute("SELECT count(*), count(DISTINCT event_id) FROM bronze.usgs_sismos")
            total, distintos = cur.fetchone()

        print(f"+{len(filas)} filas | bronze total: {total} filas, {distintos} eventos distintos")
        return len(filas)

    cargar_bronze(descargar(elegir_feed()))


usgs_bronze()
