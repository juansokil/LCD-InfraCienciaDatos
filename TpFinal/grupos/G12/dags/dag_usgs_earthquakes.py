import sys
from datetime import datetime, timedelta
from pathlib import Path

# Agregar /opt/airflow para que encuentre los scripts dentro de Docker
sys.path.append('/opt/airflow')
sys.path.append(str(Path(__file__).resolve().parent.parent))

from airflow import DAG
from airflow.operators.python import PythonOperator

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
    schedule_interval='@daily',
    catchup=False,
    tags=['usgs', 'g12'],
) as dag:

    task_bronze = PythonOperator(
        task_id='ingest_bronze_task',
        python_callable=ingestar_usgs_bronze,
        op_kwargs={'modo': 'append'}
    )

    task_silver = PythonOperator(
        task_id='transform_silver_task',
        python_callable=procesar_silver_usgs
    )

    task_gold = PythonOperator(
        task_id='transform_gold_task',
        python_callable=procesar_gold_usgs
    )

    task_bronze >> task_silver >> task_gold