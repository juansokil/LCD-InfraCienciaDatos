"""
DAG: citybikes_bronze
Ingesta desde la API de CityBikes a la capa Bronze.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.decorators import dag, task

try:  # Airflow 3.x
    from airflow.sdk import get_current_context
except ImportError:  # fallback Airflow 2.x
    from airflow.operators.python import get_current_context  # noqa: E402

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_CITYBIKES  # noqa: E402
from common.contracts import load_contract  # noqa: E402


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'CityBikes')}"
)

DATA_DIR = Path("/opt/airflow/data")
CONTRACT_PATH = DATA_DIR / "contracts" / "citybikes_stations.yaml"
RAW_DIR = DATA_DIR / "raw" / "citybikes"
QUARANTINE_DIR = DATA_DIR / "quarantine" / "citybikes"
API_BASE = "https://api.citybik.es/v2/networks"

# Metadata de auditoria, igual en las dos tablas.
AUDIT_COLS = ["snapshot_ts", "ingested_at", "run_id", "raw_path", "contract_version", "source"]

# Columna de bronze
EXTRA_COLS = {
    "station_uid": "uid",
    "address": "address",
    "post_code": "post_code",
    "slots": "slots",
    "normal_bikes": "normal_bikes",
    "ebikes": "ebikes",
    "renting": "renting",
    "returning": "returning",
    "virtual": "virtual",
    "source_last_updated": "last_updated",
}

STATION_COLS = [
    "network_id", "station_id", "name", "latitude", "longitude",
    "source_timestamp", "free_bikes", "empty_slots",
    *EXTRA_COLS,
    "extra_json",
]

NETWORK_COLS = [
    "network_id", "name", "city", "country", "latitude", "longitude",
    "company_json", "gbfs_href", "station_count",
]

def validar_forma(payload: dict, contract: dict) -> None:
    """Lanza ValueError con el motivo si el payload no respeta el contrato."""
    forma = contract["payload"]
    root = payload.get(forma["root_key"])
    if not isinstance(root, dict):
        raise ValueError(f"payload.root_key: falta '{forma['root_key']}'")
    registros = root.get(forma["records_key"])
    if not isinstance(registros, list):
        raise ValueError(f"payload.records_key: falta '{forma['records_key']}'")
    if len(registros) < forma.get("min_records", 1):
        raise ValueError(f"payload.min_records: llegaron {len(registros)} estaciones")

    requeridas = [
        col["source"].removeprefix("stations[].")
        for col in contract["schema"]
        if not col.get("nullable", False) and col["source"].startswith("stations[].")
    ]
    for i, st in enumerate(registros):
        faltan = [k for k in requeridas if st.get(k) is None]
        if faltan:
            raise ValueError(f"schema.nullable: estacion #{i} ({st.get('id')}) sin {faltan}")


def _texto(valor):
    if valor is None:
        return None
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def aplanar(payload: dict) -> tuple[dict, list[dict]]:
    """Devuelve (fila de la red, filas de estaciones), todo como texto."""
    red = payload["network"]
    loc = red.get("location") or {}
    fila_red = {
        "network_id": red["id"],
        "name": red.get("name"),
        "city": loc.get("city"),
        "country": loc.get("country"),
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "company_json": red.get("company"),
        "gbfs_href": red.get("gbfs_href"),
        "station_count": len(red["stations"]),
    }

    filas = []
    for st in red["stations"]:
        extra = st.get("extra") or {}
        fila = {
            "network_id": red["id"],
            "station_id": st["id"],
            "name": st.get("name"),
            "latitude": st.get("latitude"),
            "longitude": st.get("longitude"),
            "source_timestamp": st.get("timestamp"),
            "free_bikes": st.get("free_bikes"),
            "empty_slots": st.get("empty_slots"),
            **{col: extra.get(clave) for col, clave in EXTRA_COLS.items()},
            "extra_json": extra,
        }
        filas.append(fila)

    return (
        {k: _texto(v) for k, v in fila_red.items()},
        [{k: _texto(v) for k, v in f.items()} for f in filas],
    )


def _momento_logico(ctx) -> datetime:
    """Momento de la corrida: estable entre retries (el ingested_at no)."""
    dag_run = ctx.get("dag_run")
    return (
        ctx.get("logical_date")
        or getattr(dag_run, "run_after", None)
        or datetime.now(timezone.utc)
    )


# =============================================================================
# DAG
# =============================================================================

@dag(
    dag_id="citybikes_bronze",
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    start_date=datetime(2026, 10, 1),
    schedule="*/5 * * * *",
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["bronze", "citybikes"],
    doc_md=__doc__,
)
def citybikes_bronze():

    @task
    def leer_contrato() -> list[str]:
        """Las redes a consultar salen del contrato."""
        contract = load_contract(CONTRACT_PATH)
        redes = contract["delivery"]["networks"]
        print(f"[contract] {contract['dataset']} v{contract['version']}: {redes}")
        return redes

    @task
    def crear_tablas():
        """DDL idempotente. Los schemas los crea init.sql; las tablas las crea el DAG."""
        import sqlalchemy

        cols_st = ",\n".join(f'"{c}" text' for c in STATION_COLS)
        cols_red = ",\n".join(f'"{c}" text' for c in NETWORK_COLS)
        audit = """
            snapshot_ts      timestamptz NOT NULL,
            ingested_at      timestamptz NOT NULL,
            run_id           text NOT NULL,
            raw_path         text NOT NULL,
            contract_version text NOT NULL,
            source           text NOT NULL
        """
        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(
                f"CREATE TABLE IF NOT EXISTS bronze.citybikes_stations ({cols_st},{audit});"
            ))
            conn.execute(sqlalchemy.text(
                f"CREATE TABLE IF NOT EXISTS bronze.citybikes_networks ({cols_red},{audit});"
            ))
            conn.execute(sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_bronze_cb_st_snapshot "
                "ON bronze.citybikes_stations (snapshot_ts);"
            ))
            conn.execute(sqlalchemy.text(
                "CREATE INDEX IF NOT EXISTS ix_bronze_cb_st_run "
                "ON bronze.citybikes_stations (run_id);"
            ))

    @task(retries=3, retry_delay=timedelta(seconds=30))
    def fetch_red(network_id: str) -> dict:
        """GET a la API y payload crudo a la zona raw (gzip: Ecobici son ~250 KB
        por llamada, 288 llamadas por dia)."""
        import requests

        contract = load_contract(CONTRACT_PATH)
        url = contract["delivery"]["source_endpoint"].format(network_id=network_id)
        resp = requests.get(url, timeout=contract["delivery"]["timeout_seconds"])
        resp.raise_for_status()

        ctx = get_current_context()
        momento = _momento_logico(ctx)
        destino = RAW_DIR / network_id / f"ds={momento:%Y-%m-%d}"
        destino.mkdir(parents=True, exist_ok=True)
        archivo = destino / f"{momento:%H%M%S}.json.gz"
        archivo.write_bytes(gzip.compress(resp.content))

        restantes = resp.headers.get("ratelimit-remaining")
        print(f"{network_id}: {len(resp.content)} bytes -> {archivo} | rate-limit restante: {restantes}")
        return {"network_id": network_id, "raw_path": str(archivo)}

    @task
    def validar_payload(crudo: dict) -> dict:
        """Forma del payload contra el contrato. Si no cumple va a cuarentena."""
        contract = load_contract(CONTRACT_PATH)
        raw_path = Path(crudo["raw_path"])
        try:
            payload = json.loads(gzip.decompress(raw_path.read_bytes()))
            validar_forma(payload, contract)
        except ValueError as e:  # incluye JSONDecodeError
            ctx = get_current_context()
            destino = QUARANTINE_DIR / crudo["network_id"] / raw_path.parent.name
            destino.mkdir(parents=True, exist_ok=True)
            movido = destino / raw_path.name
            shutil.move(raw_path, movido)
            (destino / f"{raw_path.name}.error.json").write_text(json.dumps({
                "network_id": crudo["network_id"],
                "dataset": contract["dataset"],
                "contract_version": str(contract["version"]),
                "run_id": ctx["run_id"],
                "error": str(e),
            }, ensure_ascii=False, indent=2))
            print(f"[contract] {crudo['network_id']} -> cuarentena: {e}")
            return {**crudo, "ok": False, "raw_path": str(movido), "error": str(e)}

        print(f"[contract] {crudo['network_id']} OK")
        return {**crudo, "ok": True}

    @task(outlets=[BRONZE_CITYBIKES])
    def cargar_bronze(validados: list[dict]):
        """Aplana y carga las redes validas. Emite el asset -> dispara Silver."""
        import pandas as pd
        import sqlalchemy

        ctx = get_current_context()
        run_id = ctx["run_id"]
        contract = load_contract(CONTRACT_PATH)

        ok = [v for v in validados if v["ok"]]
        malos = [v["network_id"] for v in validados if not v["ok"]]
        if malos:
            print(f"Redes en cuarentena esta corrida: {malos}")
        if not ok:
            # Si no entro nada, que la corrida quede en rojo y Silver no corra.
            raise ValueError("Ninguna red paso el contrato")

        audit = {
            "snapshot_ts": _momento_logico(ctx),
            "ingested_at": datetime.now(timezone.utc),
            "run_id": run_id,
            "contract_version": str(contract["version"]),
            "source": "citybikes_api",
        }
        filas_red, filas_st = [], []
        for v in ok:
            payload = json.loads(gzip.decompress(Path(v["raw_path"]).read_bytes()))
            red, estaciones = aplanar(payload)
            filas_red.append({**red, **audit, "raw_path": v["raw_path"]})
            filas_st.extend({**e, **audit, "raw_path": v["raw_path"]} for e in estaciones)

        df_red = pd.DataFrame(filas_red, columns=NETWORK_COLS + AUDIT_COLS)
        df_st = pd.DataFrame(filas_st, columns=STATION_COLS + AUDIT_COLS)

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:  # todo o nada
            for tabla in ("citybikes_stations", "citybikes_networks"):
                conn.execute(
                    sqlalchemy.text(f"DELETE FROM bronze.{tabla} WHERE run_id = :r"),
                    {"r": run_id},
                )
            df_st.to_sql("citybikes_stations", conn, schema="bronze",
                         if_exists="append", index=False, method="multi", chunksize=1000)
            df_red.to_sql("citybikes_networks", conn, schema="bronze",
                          if_exists="append", index=False)

        print(f"bronze.citybikes_stations +{len(df_st)} | "
              f"bronze.citybikes_networks +{len(df_red)} | snapshot {audit['snapshot_ts']}")

    redes = leer_contrato()
    validados = validar_payload.expand(crudo=fetch_red.expand(network_id=redes))
    crear_tablas() >> cargar_bronze(validados)


citybikes_bronze()
