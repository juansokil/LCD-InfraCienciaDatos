import requests
import pandas as pd
import json
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine

# Ciudades que vamos a consultar
CIUDADES = {
    "Buenos Aires": (-34.61, -58.38),
    "Cordoba": (-31.41, -64.18),
    "Rosario": (-32.95, -60.66),
    "Mendoza": (-32.89, -68.84)
}


def cargar_bronze():

    registros = []

    for ciudad, (lat, lon) in CIUDADES.items():

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}"
            f"&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=America/Argentina/Buenos_Aires"
        )

        response = requests.get(url)
        response.raise_for_status()

        registros.append({
            "ciudad": ciudad,
            "latitud": lat,
            "longitud": lon,
            "api_response": json.dumps(response.json()),
            "ingested_at": datetime.now()
        })

    df = pd.DataFrame(registros)

    engine = create_engine(
        "postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db"
    )

    df.to_sql(
        name="weather_raw",
        con=engine,
        schema="bronze",
        if_exists="append",
        index=False
    )

    print(f"Se insertaron {len(df)} registros en bronze.weather_raw")


with DAG(
    dag_id="openmeteo_bronze",
    start_date=datetime(2026, 6, 1),
    schedule="@daily",
    catchup=False,
    is_paused_upon_creation=False
) as dag:

    cargar_datos = PythonOperator(
        task_id="cargar_bronze",
        python_callable=cargar_bronze
    )

