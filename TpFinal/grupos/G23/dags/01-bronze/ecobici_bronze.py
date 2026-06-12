"""
DAG Bronze - CityBikes EcoBici Buenos Aires.

Ingiere snapshots de estaciones desde:
https://api.citybik.es/v2/networks/ecobici-buenos-aires

Estrategia Bronze:
- append-only: cada corrida agrega un snapshot nuevo;
- una fila por estacion por snapshot;
- conserva el registro crudo en raw_json y extra_json para reprocesar Silver.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from airflow.decorators import dag, task


NETWORK_ID = "ecobici-buenos-aires"
API_URL = f"https://api.citybik.es/v2/networks/{NETWORK_ID}"

DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


def _normalize_timestamp(value):
    """CityBikes puede devolver '+00:00Z'; Postgres acepta '+00:00' o 'Z', no ambos."""
    if value is None:
        return None
    if isinstance(value, str) and value.endswith("+00:00Z"):
        return value[:-1]
    return value


@dag(
    dag_id="ecobici_bronze",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["prod", "bronze", "citybikes", "ecobici"],
    doc_md="""
    ## EcoBici Bronze

    Toma snapshots cada 15 minutos desde CityBikes y carga
    `bronze.ecobici_stations_raw`.
    """,
)
def ecobici_bronze():
    @task(retries=2)
    def fetch_network() -> dict:
        import requests

        response = requests.get(API_URL, timeout=30)
        response.raise_for_status()
        payload = response.json()

        stations = payload.get("network", {}).get("stations", [])
        if not stations:
            raise ValueError("CityBikes no devolvio estaciones para EcoBici Buenos Aires.")

        print(f"Estaciones recibidas: {len(stations)}")
        return payload

    @task
    def transform_stations(payload: dict) -> list[dict]:
        network = payload["network"]
        stations = network.get("stations", [])
        ingested_at = datetime.now(timezone.utc)
        snapshot_id = str(uuid.uuid4())

        records = []
        for station in stations:
            extra = station.get("extra") or {}
            records.append(
                {
                    "snapshot_id": snapshot_id,
                    "ingested_at": ingested_at.isoformat(),
                    "source": "citybikes",
                    "network_id": network.get("id"),
                    "network_name": network.get("name"),
                    "station_id": station.get("id"),
                    "station_uid": extra.get("uid"),
                    "station_name": station.get("name"),
                    "latitude": station.get("latitude"),
                    "longitude": station.get("longitude"),
                    "free_bikes": station.get("free_bikes"),
                    "empty_slots": station.get("empty_slots"),
                    "station_timestamp": _normalize_timestamp(station.get("timestamp")),
                    "last_updated": _normalize_timestamp(extra.get("last_updated")),
                    "is_renting": extra.get("renting"),
                    "is_returning": extra.get("returning"),
                    "address": extra.get("address"),
                    "slots": extra.get("slots"),
                    "normal_bikes": extra.get("normal_bikes"),
                    "virtual": extra.get("virtual"),
                    "extra_json": json.dumps(extra, ensure_ascii=False),
                    "raw_json": json.dumps(station, ensure_ascii=False),
                }
            )

        print(f"Snapshot {snapshot_id}: {len(records)} estaciones transformadas.")
        return records

    @task
    def load_bronze(records: list[dict]) -> None:
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        create_sql = sqlalchemy.text(
            """
            CREATE SCHEMA IF NOT EXISTS bronze;

            CREATE TABLE IF NOT EXISTS bronze.ecobici_stations_raw (
                snapshot_id TEXT NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL,
                source TEXT NOT NULL,
                network_id TEXT,
                network_name TEXT,
                station_id TEXT NOT NULL,
                station_uid TEXT,
                station_name TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                free_bikes INTEGER,
                empty_slots INTEGER,
                station_timestamp TIMESTAMPTZ,
                last_updated TIMESTAMPTZ,
                is_renting BOOLEAN,
                is_returning BOOLEAN,
                address TEXT,
                slots INTEGER,
                normal_bikes INTEGER,
                virtual BOOLEAN,
                extra_json JSONB,
                raw_json JSONB
            );
            """
        )

        insert_sql = sqlalchemy.text(
            """
            INSERT INTO bronze.ecobici_stations_raw (
                snapshot_id, ingested_at, source, network_id, network_name,
                station_id, station_uid, station_name, latitude, longitude,
                free_bikes, empty_slots, station_timestamp, last_updated,
                is_renting, is_returning, address, slots, normal_bikes, virtual,
                extra_json, raw_json
            )
            VALUES (
                :snapshot_id, :ingested_at, :source, :network_id, :network_name,
                :station_id, :station_uid, :station_name, :latitude, :longitude,
                :free_bikes, :empty_slots, :station_timestamp, :last_updated,
                :is_renting, :is_returning, :address, :slots, :normal_bikes, :virtual,
                CAST(:extra_json AS JSONB), CAST(:raw_json AS JSONB)
            );
            """
        )

        with engine.begin() as conn:
            conn.execute(create_sql)
            conn.execute(insert_sql, records)

        print(f"bronze.ecobici_stations_raw: +{len(records)} filas")

    payload = fetch_network()
    records = transform_stations(payload)
    load_bronze(records)


ecobici_bronze()
