import pandas as pd
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text


DB_URI = "postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db"


def _get_engine():
    return create_engine(DB_URI)


def transformar_gold():

    engine = _get_engine()

    # ─────────────────────────────
    # 1. LEER SILVER
    # ─────────────────────────────
    query = text("""
        SELECT *
        FROM silver.weather
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if df.empty:
        print("No hay datos en silver")
        return

    print(f"Registros silver leídos: {len(df)}")

    # ─────────────────────────────
    # 2. FEATURE ENGINEERING
    # ─────────────────────────────

    df["is_rainy_day"] = df["precipitation"].fillna(0) > 0

    # ─────────────────────────────
    # 3. AGREGACIONES GOLD
    # ─────────────────────────────
    gold_df = df.groupby("city").agg(
        avg_temp_max=("temperature_max", "mean"),
        avg_temp_min=("temperature_min", "mean"),
        max_temp_max=("temperature_max", "max"),
        min_temp_min=("temperature_min", "min"),
        total_precipitation=("precipitation", "sum"),
        rainy_days=("is_rainy_day", "sum")
    ).reset_index()

    # ─────────────────────────────
    # 4. LIMPIEZA FINAL
    # ─────────────────────────────
    gold_df = gold_df.round(2)

    # ─────────────────────────────
    # 5. GUARDAR EN GOLD
    # ─────────────────────────────
    gold_df.to_sql(
        name="weather_summary",
        schema="gold",
        con=engine,
        if_exists="replace",
        index=False
    )

    print("GOLD generado correctamente:")
    print(gold_df)


# ─────────────────────────────
# DAG
# ─────────────────────────────
with DAG(
    dag_id="openmeteo_gold",
    start_date=datetime(2026, 6, 1),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
    doc_md="""
    ### GOLD - Weather Analytics

    Este DAG genera métricas agregadas desde `silver.weather`:

    - Promedios de temperatura por ciudad
    - Extremos (max/min)
    - Precipitación total
    - Días lluviosos

    Output: `gold.weather_summary`
    """,
) as dag:

    transformar_gold_task = PythonOperator(
        task_id="transformar_gold",
        python_callable=transformar_gold,
    )