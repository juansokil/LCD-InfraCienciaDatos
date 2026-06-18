from datetime import datetime
import os

from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text


def transformar_silver_a_gold():
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")

    engine = create_engine(
        f"postgresql://{db_user}:{db_pass}@data_warehouse:5432/{db_name}"
    )

    query_crear_dim_currency = text(
        """
        CREATE TABLE IF NOT EXISTS gold.dim_currency (
            currency_code VARCHAR(10) PRIMARY KEY,
            first_seen_at TIMESTAMP NOT NULL,
            last_seen_at TIMESTAMP NOT NULL,
            is_ars BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (BTRIM(currency_code) <> '')
        );
        """
    )

    query_crear_dim_time = text(
        """
        CREATE TABLE IF NOT EXISTS gold.dim_time (
            api_timestamp BIGINT PRIMARY KEY,
            clear_ts TIMESTAMP NOT NULL,
            date_day DATE NOT NULL,
            hour_of_day INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            month_number INTEGER NOT NULL,
            year_number INTEGER NOT NULL
        );
        """
    )

    query_crear_fact = text(
        """
        CREATE TABLE IF NOT EXISTS gold.fact_ars_exchange_rates (
            id SERIAL PRIMARY KEY,
            api_timestamp BIGINT NOT NULL,
            clear_ts TIMESTAMP NOT NULL,
            base_currency VARCHAR(10) NOT NULL,
            currency_code VARCHAR(10) NOT NULL,
            rate_per_usd NUMERIC(18, 6) NOT NULL,
            ars_per_usd NUMERIC(18, 6) NOT NULL,
            ars_per_currency NUMERIC(24, 8) NOT NULL,
            currency_per_ars NUMERIC(24, 12) NOT NULL,
            variation_pct_vs_previous NUMERIC(18, 6),
            bronze_raw_id INTEGER NOT NULL,
            source_payload_hash VARCHAR(64) NOT NULL,
            loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (BTRIM(base_currency) <> ''),
            CHECK (BTRIM(currency_code) <> ''),
            CHECK (rate_per_usd > 0),
            CHECK (ars_per_usd > 0),
            CHECK (ars_per_currency > 0),
            CHECK (currency_per_ars > 0),
            UNIQUE (api_timestamp, currency_code)
        );
        """
    )

    query_crear_indices = text(
        """
        CREATE INDEX IF NOT EXISTS idx_gold_fact_ars_currency_code
        ON gold.fact_ars_exchange_rates (currency_code);

        CREATE INDEX IF NOT EXISTS idx_gold_fact_ars_clear_ts
        ON gold.fact_ars_exchange_rates (clear_ts);

        CREATE INDEX IF NOT EXISTS idx_gold_fact_ars_variation
        ON gold.fact_ars_exchange_rates (variation_pct_vs_previous);
        """
    )

    query_cargar_dim_currency = text(
        """
        INSERT INTO gold.dim_currency (
            currency_code,
            first_seen_at,
            last_seen_at,
            is_ars,
            updated_at
        )
        SELECT
            currency_code,
            MIN(clear_ts) AS first_seen_at,
            MAX(clear_ts) AS last_seen_at,
            currency_code = 'ARS' AS is_ars,
            CURRENT_TIMESTAMP AS updated_at
        FROM silver.exchange_rates
        GROUP BY currency_code
        ON CONFLICT (currency_code) DO UPDATE SET
            first_seen_at = LEAST(
                gold.dim_currency.first_seen_at,
                EXCLUDED.first_seen_at
            ),
            last_seen_at = GREATEST(
                gold.dim_currency.last_seen_at,
                EXCLUDED.last_seen_at
            ),
            is_ars = EXCLUDED.is_ars,
            updated_at = CURRENT_TIMESTAMP;
        """
    )

    query_cargar_dim_time = text(
        """
        INSERT INTO gold.dim_time (
            api_timestamp,
            clear_ts,
            date_day,
            hour_of_day,
            day_of_week,
            month_number,
            year_number
        )
        SELECT DISTINCT
            api_timestamp,
            clear_ts,
            clear_ts::date AS date_day,
            EXTRACT(HOUR FROM clear_ts)::integer AS hour_of_day,
            EXTRACT(ISODOW FROM clear_ts)::integer AS day_of_week,
            EXTRACT(MONTH FROM clear_ts)::integer AS month_number,
            EXTRACT(YEAR FROM clear_ts)::integer AS year_number
        FROM silver.exchange_rates
        ON CONFLICT (api_timestamp) DO UPDATE SET
            clear_ts = EXCLUDED.clear_ts,
            date_day = EXCLUDED.date_day,
            hour_of_day = EXCLUDED.hour_of_day,
            day_of_week = EXCLUDED.day_of_week,
            month_number = EXCLUDED.month_number,
            year_number = EXCLUDED.year_number;
        """
    )

    query_cargar_fact = text(
        """
        WITH ars_rates AS (
            SELECT
                api_timestamp,
                exchange_rate AS ars_per_usd
            FROM silver.exchange_rates
            WHERE currency_code = 'ARS'
        ),
        derived_rates AS (
            SELECT
                s.api_timestamp,
                s.clear_ts,
                s.base_currency,
                s.currency_code,
                s.exchange_rate AS rate_per_usd,
                ars.ars_per_usd,
                ars.ars_per_usd / s.exchange_rate AS ars_per_currency,
                s.exchange_rate / ars.ars_per_usd AS currency_per_ars,
                s.bronze_raw_id,
                s.source_payload_hash
            FROM silver.exchange_rates s
            INNER JOIN ars_rates ars
                ON s.api_timestamp = ars.api_timestamp
            WHERE s.exchange_rate > 0
              AND ars.ars_per_usd > 0
        ),
        rates_with_previous AS (
            SELECT
                derived_rates.*,
                LAG(ars_per_currency) OVER (
                    PARTITION BY currency_code
                    ORDER BY api_timestamp
                ) AS previous_ars_per_currency
            FROM derived_rates
        )
        INSERT INTO gold.fact_ars_exchange_rates (
            api_timestamp,
            clear_ts,
            base_currency,
            currency_code,
            rate_per_usd,
            ars_per_usd,
            ars_per_currency,
            currency_per_ars,
            variation_pct_vs_previous,
            bronze_raw_id,
            source_payload_hash,
            loaded_at
        )
        SELECT
            api_timestamp,
            clear_ts,
            base_currency,
            currency_code,
            rate_per_usd,
            ars_per_usd,
            ars_per_currency,
            currency_per_ars,
            CASE
                WHEN previous_ars_per_currency IS NULL
                    OR previous_ars_per_currency = 0
                    THEN NULL
                ELSE (
                    (ars_per_currency - previous_ars_per_currency)
                    / previous_ars_per_currency
                ) * 100
            END AS variation_pct_vs_previous,
            bronze_raw_id,
            source_payload_hash,
            CURRENT_TIMESTAMP AS loaded_at
        FROM rates_with_previous
        ON CONFLICT (api_timestamp, currency_code) DO UPDATE SET
            clear_ts = EXCLUDED.clear_ts,
            base_currency = EXCLUDED.base_currency,
            rate_per_usd = EXCLUDED.rate_per_usd,
            ars_per_usd = EXCLUDED.ars_per_usd,
            ars_per_currency = EXCLUDED.ars_per_currency,
            currency_per_ars = EXCLUDED.currency_per_ars,
            variation_pct_vs_previous = EXCLUDED.variation_pct_vs_previous,
            bronze_raw_id = EXCLUDED.bronze_raw_id,
            source_payload_hash = EXCLUDED.source_payload_hash,
            loaded_at = CURRENT_TIMESTAMP;
        """
    )

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        conn.execute(query_crear_dim_currency)
        conn.execute(query_crear_dim_time)
        conn.execute(query_crear_fact)
        conn.execute(query_crear_indices)
        conn.execute(query_cargar_dim_currency)
        conn.execute(query_cargar_dim_time)
        conn.execute(query_cargar_fact)

    print("Transformacion de Capa Gold completada con exito.")


with DAG(
    dag_id="03_gold_ars_exchange_rates",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
) as dag:
    tarea_gold = PythonOperator(
        task_id="modelo_gold_ars",
        python_callable=transformar_silver_a_gold,
    )
