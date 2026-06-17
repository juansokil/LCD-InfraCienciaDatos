import json
import requests
import pandas as pd
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine

# 1. Definimos las 4 ciudades extremas que elegiste con sus coordenadas
CIUDADES = {
    "Jujuy": {"lat": -24.19, "lon": -65.30},
    "Mendoza": {"lat": -32.89, "lon": -68.83},
    "Buenos Aires": {"lat": -34.61, "lon": -58.38},
    "Ushuaia": {"lat": -54.80, "lon": -68.30}
}

def extraer_datos_clima():
    datos_totales = []
    
    # 2. Le pedimos el pronóstico a la API para cada ciudad
    for ciudad, coords in CIUDADES.items():
        # URL de la API pidiendo las temperaturas máximas, mínimas y lluvia
        url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=America%2FArgentina%2FBuenos_Aires"
        
        respuesta = requests.get(url)
        datos_json = respuesta.json()
        
        # 3. Guardamos el dato crudo (Bronze) agregando metadatos (ciudad y fecha de ingesta)
        registro = {
            "ciudad": ciudad,
            "datos_crudos": json.dumps(datos_json), # Convertimos el JSON en texto para guardarlo
            "fecha_extraccion": datetime.now()
        }
        datos_totales.append(registro)
        
    # 4. Convertimos nuestra lista en una tabla (DataFrame)
    df = pd.DataFrame(datos_totales)
    
    # 5. Nos conectamos a la base de datos Postgres que tenés corriendo en Docker
    # (El usuario, contraseña y base de datos se llaman 'airflow')
    engine = create_engine('postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db')
    
    # 6. Guardamos la tabla en el esquema 'bronze'
    df.to_sql('clima_raw', engine, schema='bronze', if_exists='append', index=False)
    print("¡Datos guardados exitosamente en la capa Bronze!")

# 7. Configuramos el Orquestador (Airflow)
with DAG(
    dag_id="01_bronze_clima",
    start_date=datetime(2026, 6, 15), # Fecha de inicio
    schedule_interval="@daily",       # Le decimos que corra 1 vez por día
    catchup=False,
    is_paused_upon_creation=False     # REQUISITO DEL TP: Que arranque prendido solo
) as dag:

    # Creamos la tarea que va a ejecutar nuestra función de arriba
    tarea_extraccion = PythonOperator(
        task_id="extraer_api_openmeteo",
        python_callable=extraer_datos_clima
    )