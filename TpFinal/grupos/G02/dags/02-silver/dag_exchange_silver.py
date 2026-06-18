from datetime import datetime
import os

from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text


def transformar_bronze_a_silver():
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")

    engine = create_engine(
        f"postgresql://{db_user}:{db_pass}@data_warehouse:5432/{db_name}"
    )

    query_crear_tabla = text(
        """
        CREATE TABLE IF NOT EXISTS silver.exchange_rates (
            id SERIAL PRIMARY KEY,
            clear_ts TIMESTAMP NOT NULL,
            api_timestamp BIGINT NOT NULL,
            base_currency VARCHAR(10) NOT NULL,
            currency_code VARCHAR(10) NOT NULL,
            exchange_rate NUMERIC(18, 6) NOT NULL,
            ingested_at TIMESTAMP NOT NULL,
            bronze_raw_id INTEGER NOT NULL,
            source_payload_hash VARCHAR(64) NOT NULL,
            CHECK (BTRIM(base_currency) <> ''),
            CHECK (BTRIM(currency_code) <> ''),
            CHECK (exchange_rate > 0),
            UNIQUE (api_timestamp, currency_code)
        );
        """
    )

    query_migrar_tabla = text(
        """
        ALTER TABLE silver.exchange_rates
        ADD COLUMN IF NOT EXISTS bronze_raw_id INTEGER,
        ADD COLUMN IF NOT EXISTS source_payload_hash VARCHAR(64);
        """
    )

    query_crear_indices = text(
        """
        CREATE INDEX IF NOT EXISTS idx_silver_exchange_rates_currency_code
        ON silver.exchange_rates (currency_code);

        CREATE INDEX IF NOT EXISTS idx_silver_exchange_rates_clear_ts
        ON silver.exchange_rates (clear_ts);
        """
    )

    query_insertar = text(
        """
        INSERT INTO silver.exchange_rates (
            clear_ts,
            api_timestamp,
            base_currency,
            currency_code,
            exchange_rate,
            ingested_at,
            bronze_raw_id,
            source_payload_hash
        )
        SELECT
            TO_TIMESTAMP(br.api_timestamp) AS clear_ts,
            br.api_timestamp,
            UPPER(BTRIM(br.base_currency)) AS base_currency,
            UPPER(BTRIM(rate.key)) AS currency_code,
            rate.value::numeric AS exchange_rate,
            br.ingested_at,
            br.id AS bronze_raw_id,
            br.payload_hash AS source_payload_hash
        FROM bronze.exchange_rates_raw br
        CROSS JOIN jsonb_each_text(br.rates) AS rate(key, value)
        WHERE br.base_currency IS NOT NULL
          AND BTRIM(br.base_currency) <> ''
          AND rate.key IS NOT NULL
          AND BTRIM(rate.key) <> ''
          AND rate.value IS NOT NULL
          AND rate.value::numeric > 0
        ON CONFLICT (api_timestamp, currency_code) DO NOTHING;
        """
    )

    with engine.begin() as conn:
        conn.execute(query_crear_tabla)
        conn.execute(query_migrar_tabla)
        conn.execute(query_crear_indices)
        conn.execute(query_insertar)

    print("Transformacion de Capa Silver completada con exito.")


with DAG(
    dag_id="02_silver_exchange_rates",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
) as dag:
    tarea_silver = PythonOperator(
        task_id="limpieza_silver",
        python_callable=transformar_bronze_a_silver,
    )
