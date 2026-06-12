import os
import json
from datetime import datetime
import requests
from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

# argumentos del DAG
default_args = {
    'owner': 'grupo03',
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
}

# declarar el DAG
with DAG(
    dag_id='weather_bronze_pipeline',
    default_args=default_args,
    schedule_interval='@hourly',
    is_paused_upon_creation=False,        # asi arranca activo por defecto
    catchup=False
) as dag:

    @task
    def cargar_coordenadas():
        """Lee el archivo JSON de configuración montado en Airflow"""
        # En Docker, mapearemos este archivo a /opt/airflow/coordenadas.json
        ruta_json = '/opt/airflow/coordenadas.json'
        with open(ruta_json, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config

    @task
    def extraer_e_ingresar_bronze(config):
        """Consulta la API para cada ciudad y guarda el JSON crudo en Postgres"""
        # Tomamos la URL base y las variables del JSON
        base_url = "https://api.open-meteo.com/v1/forecast"
        variables_clima = ",".join(config["variables"])
        
        # Conectamos a la base de datos usando el Hook de Airflow (usa la conexión 'postgres_default')
        pg_hook = PostgresHook(postgres_conn_id='postgres_default')
        conn = pg_hook.get_conn()
        cursor = conn.cursor()

        tiempo_actual = datetime.now()

        for ciudad in config["cities"]:
            params = {
                "latitude": ciudad["latitude"],
                "longitude": ciudad["longitude"],
                "current": variables_clima,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "past_days": 90,
                "timezone": "auto"
            }
            
            try:
                # Petición a Open-Meteo
                respuesta = requests.get(base_url, params=params)
                respuesta.raise_for_status()
                data_json = respuesta.json()
                
                # Insertar en la capa bronze el JSON completo como texto estructurado
                query = """
                    INSERT INTO bronze.raw_weather_data (ciudad, raw_json, tiempo_extraccion)
                    VALUES (%s, %s, %s);
                """
                cursor.execute(query, (ciudad["name"], json.dumps(data_json), tiempo_actual))
                print(f"Datos de {ciudad['name']} guardados exitosamente en bronze.")
                
            except Exception as e:
                print(f"Error al procesar la ciudad {ciudad['name']}: {str(e)}")
                continue

        conn.commit()
        cursor.close()
        conn.close()

    # 3. Definir el flujo de tareas
    config_datos = cargar_coordenadas()
    extraer_e_ingresar_bronze(config_datos)