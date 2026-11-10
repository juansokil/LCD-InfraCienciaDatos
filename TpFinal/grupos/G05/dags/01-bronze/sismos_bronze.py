import os
import json
import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
import psycopg2
from pydantic import ValidationError
from psycopg2.extras import execute_batch
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from airflow import DAG
from airflow.operators.python import PythonOperator
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from contracts import build_pydantic_from_contract, load_contract

logger = logging.getLogger(__name__)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"
CONTRACT_PATH = Path("/opt/airflow/data/contracts/sismos.yaml")
_EVENT_CONTRACT = None


def validate_event_contract(
    event_id, props, longitude, latitude, depth
):
    global _EVENT_CONTRACT
    if _EVENT_CONTRACT is None:
        _EVENT_CONTRACT = build_pydantic_from_contract(load_contract(CONTRACT_PATH))

    _EVENT_CONTRACT(
        id=event_id,
        mag=props.get("mag"),
        place=props.get("place"),
        time_epoch=props.get("time"),
        updated_epoch=props.get("updated"),
        type=props.get("type"),
        status=props.get("status"),
        tsunami=props.get("tsunami"),
        sig=props.get("sig"),
        mag_type=props.get("magType"),
        longitude=longitude,
        latitude=latitude,
        depth=depth,
    )


def load_backfill_config():
    with CONTRACT_PATH.open(encoding="utf-8") as contract_file:
        contract = yaml.safe_load(contract_file)
    delivery = contract["delivery"]
    return (
        delivery["source_endpoint"],
        int(delivery["initial_backfill_days"]),
        int(delivery["maximum_events_per_request"]),
        delivery["event_type"],
    )

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
        port=int(os.getenv("SOURCE_DB_PORT", 5432)),
        dbname=os.getenv("SOURCE_DB_NAME", "InfraCienciaDatos"),
        user=os.getenv("SOURCE_DB_USER", "admin"),
        password=os.getenv("SOURCE_DB_PASS", "admin")
    )

def guardar_payload(payload, run_id, now):
    # 2. Guardar archivo crudo en landing zone particionado por fecha
    raw_dir = f"/opt/airflow/data/raw/sismos/year={now.year}/month={now.strftime('%m')}/day={now.strftime('%d')}"
    os.makedirs(raw_dir, exist_ok=True)
    raw_file = os.path.join(
        raw_dir,
        f"sismos_{now.strftime('%H%M%S%f')}_{uuid.uuid4().hex[:8]}.json",
    )
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    logger.info("Guardado archivo crudo en %s", raw_file)

    # 3. Parsear elementos GeoJSON a registros tabulares
    features = payload.get("features", [])
    if not isinstance(features, list):
        raise ValueError("La respuesta GeoJSON de USGS no contiene una lista 'features'.")

    records = []
    for index, feat in enumerate(features):
        if not isinstance(feat, dict):
            raise ValueError(f"El evento USGS en la posicion {index} no es un objeto GeoJSON.")

        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry", {}) or {}
        coords = geom.get("coordinates", [None, None, None])
        if not isinstance(coords, (list, tuple)):
            coords = [None, None, None]
        lon = coords[0] if len(coords) > 0 else None
        lat = coords[1] if len(coords) > 1 else None
        depth = coords[2] if len(coords) > 2 else None
        event_id = feat.get("id")
        updated_epoch = props.get("updated")
        if not event_id or updated_epoch is None:
            raise ValueError(
                f"El evento USGS en la posicion {index} no tiene 'id' o 'updated'."
            )
        try:
            validate_event_contract(event_id, props, lon, lat, depth)
        except ValidationError as exc:
            raise ValueError(
                f"El evento USGS '{event_id}' no cumple data/contracts/sismos.yaml: {exc}"
            ) from exc

        records.append((
            event_id,
            props.get("mag"),
            props.get("place"),
            props.get("time"),
            updated_epoch,
            props.get("tz"),
            props.get("url"),
            props.get("detail"),
            props.get("felt"),
            props.get("cdi"),
            props.get("mmi"),
            props.get("alert"),
            props.get("status"),
            props.get("tsunami"),
            props.get("sig"),
            props.get("net"),
            props.get("code"),
            props.get("ids"),
            props.get("sources"),
            props.get("types"),
            props.get("nst"),
            props.get("dmin"),
            props.get("rms"),
            props.get("gap"),
            props.get("magType"),
            props.get("type"),
            props.get("title"),
            lon,
            lat,
            depth,
            run_id
        ))

    # 4. Inserción idempotente en PostgreSQL
    insert_sql = """
        INSERT INTO bronze.sismos_crudo (
            id, mag, place, time_epoch, updated_epoch, tz, url, detail,
            felt, cdi, mmi, alert, status, tsunami, sig, net, code, ids,
            sources, types, nst, dmin, rms, gap, mag_type, type, title,
            longitude, latitude, depth, run_id
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (id, updated_epoch) DO NOTHING;
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS bronze;
                CREATE TABLE IF NOT EXISTS bronze.sismos_crudo (
                    id VARCHAR(50) NOT NULL,
                    mag FLOAT,
                    place TEXT,
                    time_epoch BIGINT,
                    updated_epoch BIGINT NOT NULL,
                    tz INT,
                    url TEXT,
                    detail TEXT,
                    felt INT,
                    cdi FLOAT,
                    mmi FLOAT,
                    alert VARCHAR(20),
                    status VARCHAR(20),
                    tsunami INT,
                    sig INT,
                    net VARCHAR(20),
                    code VARCHAR(50),
                    ids TEXT,
                    sources TEXT,
                    types TEXT,
                    nst INT,
                    dmin FLOAT,
                    rms FLOAT,
                    gap FLOAT,
                    mag_type VARCHAR(20),
                    type VARCHAR(50),
                    title TEXT,
                    longitude FLOAT,
                    latitude FLOAT,
                    depth FLOAT,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source VARCHAR(50) DEFAULT 'USGS API',
                    run_id VARCHAR(100),
                    CONSTRAINT sismos_crudo_pkey PRIMARY KEY (id, updated_epoch)
                );
            """)
            # Migrar sin borrar datos: las instalaciones existentes tenian
            # una PK solo por id, que impedia conservar versiones anteriores.
            cur.execute("""
                DO $$
                DECLARE
                    pk_name TEXT;
                    pk_columns TEXT[];
                    expected_columns TEXT[] := ARRAY['id', 'updated_epoch'];
                BEGIN
                    SELECT c.conname,
                           array_agg(a.attname ORDER BY k.ordinality)
                    INTO pk_name, pk_columns
                    FROM pg_constraint c
                    CROSS JOIN LATERAL unnest(c.conkey)
                        WITH ORDINALITY AS k(attnum, ordinality)
                    JOIN pg_attribute a
                      ON a.attrelid = c.conrelid
                     AND a.attnum = k.attnum
                    WHERE c.conrelid = 'bronze.sismos_crudo'::regclass
                      AND c.contype = 'p'
                    GROUP BY c.conname;

                    IF pk_columns IS DISTINCT FROM expected_columns THEN
                        IF pk_name IS NOT NULL THEN
                            EXECUTE format(
                                'ALTER TABLE bronze.sismos_crudo DROP CONSTRAINT %I',
                                pk_name
                            );
                        END IF;

                        ALTER TABLE bronze.sismos_crudo
                            ALTER COLUMN id SET NOT NULL,
                            ALTER COLUMN updated_epoch SET NOT NULL;
                        ALTER TABLE bronze.sismos_crudo
                            ADD CONSTRAINT sismos_crudo_pkey
                            PRIMARY KEY (id, updated_epoch);
                    END IF;
                END $$;
            """)
            execute_batch(cur, insert_sql, records, page_size=500)
        conn.commit()
        logger.info("Cargados %d registros en bronze.sismos_crudo", len(records))
    finally:
        conn.close()


def extraer_y_guardar_raw(**context):
    run_id = context.get("run_id", "manual_run")
    now = datetime.now(timezone.utc)

    response = requests.get(USGS_URL, timeout=30)
    response.raise_for_status()
    guardar_payload(response.json(), run_id, now)


def ejecutar_backfill_30_dias(**context):
    endpoint, backfill_days, max_events, event_type = load_backfill_config()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=backfill_days)
    run_id = context.get("run_id", "backfill_manual")

    def descargar_intervalo(interval_start, interval_end):
        params = {
            "format": "geojson",
            "starttime": interval_start.isoformat(timespec="milliseconds"),
            "endtime": interval_end.isoformat(timespec="milliseconds"),
            "eventtype": event_type,
            "orderby": "time-asc",
            "limit": max_events,
        }
        response = requests.get(endpoint, params=params, timeout=120)
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("La respuesta de USGS no contiene una lista 'features'.")

        if len(features) >= max_events:
            interval_seconds = (interval_end - interval_start).total_seconds()
            if interval_seconds <= 1:
                raise RuntimeError(
                    "USGS alcanzó el límite de eventos en un intervalo de "
                    "un segundo; no se puede subdividir con seguridad."
                )
            midpoint = interval_start + (interval_end - interval_start) / 2
            logger.info(
                "USGS devolvió %d eventos; subdividiendo %s a %s",
                len(features),
                interval_start.isoformat(),
                interval_end.isoformat(),
            )
            descargar_intervalo(interval_start, midpoint)
            descargar_intervalo(midpoint, interval_end)
            return

        guardar_payload(payload, run_id, datetime.now(timezone.utc))
        logger.info(
            "Backfill guardó %d eventos entre %s y %s",
            len(features),
            interval_start.isoformat(),
            interval_end.isoformat(),
        )

    descargar_intervalo(start, end)


with DAG(
    dag_id="01_bronze_sismos",
    start_date=datetime(2026, 1, 1),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["bronze", "usgs", "sismos"]
) as dag:

    tarea_ingesta = PythonOperator(
        task_id="ingestar_sismos_usgs",
        python_callable=extraer_y_guardar_raw,
        # Recien levantado el stack, la primera corrida a veces falla antes de
        # empezar (Airflow todavia esta arrancando). Con reintentar alcanza.
        retries=2,
        retry_delay=timedelta(seconds=30),
    )

    disparar_silver = TriggerDagRunOperator(
        task_id="disparar_silver",
        trigger_dag_id="02_silver_sismos",
        wait_for_completion=False
    )

    tarea_ingesta >> disparar_silver


with DAG(
    dag_id="00_backfill_sismos_30_dias",
    start_date=datetime(2026, 1, 1),
    # Corre una sola vez, apenas se levanta el stack: la consigna pide que
    # arranque sin activar DAGs a mano, y el feed horario solo trae 7 dias.
    schedule="@once",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["bronze", "usgs", "sismos", "backfill"],
) as dag:

    tarea_backfill = PythonOperator(
        task_id="backfill_30_dias_usgs",
        python_callable=ejecutar_backfill_30_dias,
        retries=2,
        retry_delay=timedelta(seconds=30),
    )

    disparar_silver_backfill = TriggerDagRunOperator(
        task_id="disparar_silver",
        trigger_dag_id="02_silver_sismos",
        wait_for_completion=False,
    )

    tarea_backfill >> disparar_silver_backfill
