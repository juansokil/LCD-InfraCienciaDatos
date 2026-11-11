import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 1. Asegurar que Python (adentro y afuera de Docker) encuentre la carpeta 'scripts'
sys.path.insert(0, '/opt/airflow')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from airflow import DAG
from airflow.operators.python import PythonOperator

# 2. Importar funciones de los scripts en la raíz del repositorio
from scripts.ingest_bronze import ingestar_usgs_bronze
from scripts.transform_silver import procesar_silver_usgs
from scripts.transform_gold import procesar_gold_usgs

default_args = {
    'owner': 'grupo_12',
    'depends_on_past': False,
    'start_date': datetime(2026, 11, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='dag_usgs_earthquakes_pipeline',
    default_args=default_args,
    description='Pipeline Medallion sismos USGS',
    schedule='@once',  
    catchup=False,
    tags=['usgs', 'g12'],
) as dag:

    task_bronze = PythonOperator(
        task_id='ingest_bronze_task',
        python_callable=ingestar_usgs_bronze,
        op_kwargs={'modo': 'append'},
    )

    task_silver = PythonOperator(
        task_id='transform_silver_task',
        python_callable=procesar_silver_usgs,
    )

    task_gold = PythonOperator(
        task_id='transform_gold_task',
        python_callable=procesar_gold_usgs,
    )

    task_bronze >> task_silver >> task_gold