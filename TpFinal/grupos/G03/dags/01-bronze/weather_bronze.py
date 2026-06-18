import os
import json
from datetime import datetime
import requests
from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    'owner': 'grupo03',
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
}

with DAG(
    dag_id='weather_bronze_pipeline',
    default_args=default_args,
    schedule='@hourly',
    is_paused_upon_creation=False,
    catchup=False
) as dag:

    @task
    def cargar_coordenadas():
        ruta_json = '/opt/airflow/coordenadas.json'
        with open(ruta_json, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config

    @task
    def extraer_e_ingresar_bronze(config):
        base_url = "https://api.open-meteo.com/v1/forecast"
        
        pg_hook = PostgresHook(postgres_conn_id='postgres_default')
        conn = pg_hook.get_conn()
        cursor = conn.cursor()
        tiempo_actual = datetime.now()

        for ciudad in config["cities"]:
            params = {
                "latitude": ciudad["latitude"],
                "longitude": ciudad["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "current": "temperature_2m,wind_speed_10m,wind_direction_10m,is_day,weather_code",
                "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code,is_day",
                "past_days": 90,
                "timezone": "auto"
            }
            
            try:
                respuesta = requests.get(base_url, params=params)
                respuesta.raise_for_status()
                data_json = respuesta.json()
                
                query = """
                    INSERT INTO bronze.raw_weather_data (ciudad, raw_json, tiempo_extraccion)
                    VALUES (%s, %s, %s);
                """
                cursor.execute(query, (ciudad["name"], json.dumps(data_json), tiempo_actual))
                print(f"Datos históricos y actuales de {ciudad['name']} guardados en bronze.")
                
            except Exception as e:
                print(f"Error al procesar la ciudad {ciudad['name']}: {str(e)}")
                continue

        conn.commit()
        cursor.close()
        conn.close()

    trigger_silver = TriggerDagRunOperator(
        task_id="trigger_weather_silver",
        trigger_dag_id="weather_silver_pipeline",
    )

    # --- ACÁ ESTÁ EL CAMBIO SINTÁCTICO LIMPIO ---
    config_datos = cargar_coordenadas()
    extraccion = extraer_e_ingresar_bronze(config_datos)
    
    # Enlazamos la tarea de extracción con el gatillo automático
    extraccion >> trigger_silver