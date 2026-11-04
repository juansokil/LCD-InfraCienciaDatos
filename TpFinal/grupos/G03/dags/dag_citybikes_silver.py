import glob
import os
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
import pandas as pd
import json

def process_silver_data():
    # Ruta donde Bronze guardó los JSONs
    raw_base_path = "/opt/airflow/data/raw/citybikes_ecobici/"
    
    # Buscar todos los archivos json de forma recursiva
    list_of_files = glob.glob(f"{raw_base_path}/**/*.json", recursive=True)
    if not list_of_files:
        raise ValueError("No se encontraron archivos en la capa Bronze.")
    
    # Tomar el archivo más reciente
    latest_file = max(list_of_files, key=os.path.getctime)
    print(f"Leyendo archivo crudo: {latest_file}")
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Dependiendo de la estructura de CityBikes, acá aplanamos las estaciones
    # (Ejemplo típico: data['network']['stations'])
    stations = data.get('network', {}).get('stations', [])
    
    if not stations:
        print("No se encontraron estaciones en el JSON.")
        return

    # Convertir a DataFrame para limpiar y estructurar (Silver)
    df = pd.DataFrame(stations)
    
    # Limpieza básica inicial (ej: seleccionar columnas clave y limpiar nulos)
    df = df[['id', 'name', 'free_bikes', 'empty_slots', 'timestamp']]
    df['processed_at'] = datetime.utcnow().isoformat()
    
    # Definir ruta de salida para Silver (capa processed)
    output_dir = "/opt/airflow/data/processed/citybikes_ecobici/"
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"silver_ecobici_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    df.to_csv(output_file, index=False)
    print(f"Datos limpios guardados exitosamente en: {output_file}")

default_args = {
    'owner': 'G03',
    'start_date': datetime(2026, 11, 1),
}

with DAG(
        dag_id='citybikes_silver',
        default_args=default_args,
        schedule=None,  # <-- Cambiado de schedule_interval a schedule
        catchup=False
    ) as dag:
    
    transform_task = PythonOperator(
        task_id='transform_bronze_to_silver',
        python_callable=process_silver_data
    )