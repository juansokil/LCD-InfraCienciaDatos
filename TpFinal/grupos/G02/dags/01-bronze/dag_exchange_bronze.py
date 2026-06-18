from datetime import datetime
import hashlib
import json
import os

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text


API_URL = "https://openexchangerates.org/api/latest.json"
SOURCE_NAME = "openexchangerates_latest"


def extraer_api_a_bronze():
    api_key = os.getenv("API_KEY")
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")

    if not api_key:
        raise ValueError("Falta la variable de entorno API_KEY")

    response = requests.get(
        API_URL,
        params={"app_id": api_key},
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    payload_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()

    engine = create_engine(
        f"postgresql://{db_user}:{db_pass}@data_warehouse:5432/{db_name}"
    )

    query_crear_tabla = text(
        """
        CREATE TABLE IF NOT EXISTS bronze.exchange_rates_raw (
            id SERIAL PRIMARY KEY,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR(100) NOT NULL,
            base_currency VARCHAR(10) NOT NULL,
            api_timestamp BIGINT NOT NULL,
            raw_json JSONB NOT NULL,
            rates JSONB NOT NULL,
            disclaimer TEXT,
            license TEXT,
            payload_hash VARCHAR(64) NOT NULL UNIQUE
        );
        """
    )

    query_insertar = text(
        """
        INSERT INTO bronze.exchange_rates_raw (
            source,
            base_currency,
            api_timestamp,
            raw_json,
            rates,
            disclaimer,
            license,
            payload_hash
        )
        VALUES (
            :source,
            :base_currency,
            :api_timestamp,
            CAST(:raw_json AS JSONB),
            CAST(:rates AS JSONB),
            :disclaimer,
            :license,
            :payload_hash
        )
        ON CONFLICT (payload_hash) DO NOTHING;
        """
    )

    with engine.begin() as conn:
        conn.execute(query_crear_tabla)
        conn.execute(
            query_insertar,
            {
                "source": SOURCE_NAME,
                "base_currency": payload["base"],
                "api_timestamp": payload["timestamp"],
                "raw_json": payload_text,
                "rates": json.dumps(payload["rates"], sort_keys=True),
                "disclaimer": payload.get("disclaimer"),
                "license": payload.get("license"),
                "payload_hash": payload_hash,
            },
        )

    print("Carga Bronze completada con exito.")


with DAG(
    dag_id="01_bronze_exchange_rates",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
) as dag:
    tarea_bronze = PythonOperator(
        task_id="extraer_api_a_bronze",
        python_callable=extraer_api_a_bronze,
    )
