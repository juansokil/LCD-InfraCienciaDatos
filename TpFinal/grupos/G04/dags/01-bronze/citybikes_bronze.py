"""
DAG Bronze — CityBikes
Ingesta cruda: por cada red configurada pega a /v2/networks/{id} y guarda
un snapshot de cada estacion (objeto JSON crudo) en bronze.citybikes_stations_raw.

Schedule: cada 5 min (la API refresca cada 2-5 min). Activo por default.
"""
from __future__ import annotations

import json
import time

import pendulum
import requests
from airflow.sdk import dag, task
from sqlalchemy import text

from citybikes_common import API_BASE, NETWORKS, get_warehouse_engine

ENSURE_TABLE = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE TABLE IF NOT EXISTS bronze.citybikes_stations_raw (
    ingestion_id    BIGSERIAL   PRIMARY KEY,
    network_id      TEXT        NOT NULL,
    network_name    TEXT,
    city            TEXT,
    country         TEXT,
    station_id      TEXT        NOT NULL,
    station_payload JSONB       NOT NULL,
    source          TEXT        NOT NULL DEFAULT 'api.citybik.es/v2',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

INSERT_SQL = text("""
    INSERT INTO bronze.citybikes_stations_raw
        (network_id, network_name, city, country, station_id, station_payload, source, ingested_at)
    VALUES
        (:network_id, :network_name, :city, :country, :station_id,
         CAST(:station_payload AS JSONB), :source, :ingested_at)
""")


@dag(
    dag_id="citybikes_bronze",
    schedule="*/5 * * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    tags=["citybikes", "bronze"],
    # Reintentos: si el warehouse todavia no esta listo (arranque en frio), reintenta
    # en vez de quedar en rojo. Las tareas son idempotentes, asi que es seguro.
    default_args={"retries": 3, "retry_delay": pendulum.duration(seconds=30)},
)
def citybikes_bronze():

    @task
    def ensure_table():
        eng = get_warehouse_engine()
        with eng.begin() as conn:
            conn.execute(text(ENSURE_TABLE))

    @task
    def ingest():
        eng = get_warehouse_engine()
        # un unico timestamp por corrida: todas las estaciones del snapshot comparten reloj
        snapshot_ts = pendulum.now("UTC")
        rows = []

        for net in NETWORKS:
            try:
                resp = requests.get(
                    f"{API_BASE}/networks/{net}",
                    params={"fields": "name,location,stations"},
                    timeout=30,
                    headers={"User-Agent": "TP-Final-G04 (educational)"},
                )
                resp.raise_for_status()
                network = resp.json().get("network", {})
                loc = network.get("location", {}) or {}
                net_name = network.get("name")
                city = loc.get("city")
                country = loc.get("country")

                for st in network.get("stations", []) or []:
                    rows.append({
                        "network_id": net,
                        "network_name": net_name,
                        "city": city,
                        "country": country,
                        "station_id": str(st.get("id")),
                        "station_payload": json.dumps(st),
                        "source": "api.citybik.es/v2",
                        "ingested_at": snapshot_ts,
                    })
                print(f"[OK] {net}: {len(network.get('stations', []) or [])} estaciones")
            except Exception as exc:  # noqa: BLE001
                # una red que falla no debe romper el DAG entero
                print(f"[WARN] red '{net}' fallo: {exc}")

            time.sleep(1)  # cortesia con el rate limit (300 req/h)

        if rows:
            with eng.begin() as conn:
                conn.execute(INSERT_SQL, rows)
        print(f"[BRONZE] insertadas {len(rows)} filas en este snapshot")
        return len(rows)

    ensure_table() >> ingest()


citybikes_bronze()
