import os
import json
import logging
from datetime import datetime, timezone
import requests
import psycopg2
from psycopg2.extras import execute_batch
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
        port=int(os.getenv("SOURCE_DB_PORT", 5432)),
        dbname=os.getenv("SOURCE_DB_NAME", "InfraCienciaDatos"),
        user=os.getenv("SOURCE_DB_USER", "admin"),
        password=os.getenv("SOURCE_DB_PASS", "admin")
    )

def extraer_y_guardar_raw(**context):
    run_id = context.get("run_id", "manual_run")
    now = datetime.now(timezone.utc)
    
    # 1. Extracción desde la API de USGS
    response = requests.get(USGS_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    
    # 2. Guardar archivo crudo en landing zone particionado por fecha
    raw_dir = f"/opt/airflow/data/raw/sismos/year={now.year}/month={now.strftime('%m')}/day={now.strftime('%d')}"
    os.makedirs(raw_dir, exist_ok=True)
    raw_file = os.path.join(raw_dir, f"sismos_{int(now.timestamp())}.json")
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    logger.info("Guardado archivo crudo en %s", raw_file)

    # 3. Parsear elementos GeoJSON a registros tabulares
    features = payload.get("features", [])
    records = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry", {}) or {}
        coords = geom.get("coordinates", [None, None, None])
        lon = coords[0] if len(coords) > 0 else None
        lat = coords[1] if len(coords) > 1 else None
        depth = coords[2] if len(coords) > 2 else None

        records.append((
            feat.get("id"),
            props.get("mag"),
            props.get("place"),
            props.get("time"),
            props.get("updated"),
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
        ON CONFLICT (id) DO UPDATE SET
            mag = EXCLUDED.mag,
            updated_epoch = EXCLUDED.updated_epoch,
            status = EXCLUDED.status,
            tsunami = EXCLUDED.tsunami,
            sig = EXCLUDED.sig,
            run_id = EXCLUDED.run_id;
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS bronze;
                CREATE TABLE IF NOT EXISTS bronze.sismos_crudo (
                    id VARCHAR(50) PRIMARY KEY,
                    mag FLOAT,
                    place TEXT,
                    time_epoch BIGINT,
                    updated_epoch BIGINT,
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
                    run_id VARCHAR(100)
                );
            """)
            execute_batch(cur, insert_sql, records, page_size=500)
        conn.commit()
        logger.info("Cargados %d registros en bronze.sismos_crudo", len(records))
    finally:
        conn.close()

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
        python_callable=extraer_y_guardar_raw
    )

    disparar_silver = TriggerDagRunOperator(
        task_id="disparar_silver",
        trigger_dag_id="02_silver_sismos",
        wait_for_completion=False
    )

    tarea_ingesta >> disparar_silver

