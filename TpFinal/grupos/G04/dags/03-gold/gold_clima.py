from datetime import datetime
from airflow import DAG
from airflow.datasets import Dataset
from airflow.providers.postgres.operators.postgres import PostgresOperator

# Definición de los Assets de la arquitectura Medallion
silver_clima_dataset = Dataset("s3://medallion/silver/clima")
gold_clima_dataset = Dataset("s3://medallion/gold/clima")

default_args = {
    'owner': 'G04-integrante3',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 1,
}

with DAG(
    dag_id='g04_gold_clima_pipeline',
    default_args=default_args,
    description='Pipeline de Capa Gold para Open-Meteo (Dimensiones, Hechos y Vistas)',
    schedule=[silver_clima_dataset], # Se dispara automáticamente al actualizarse Silver
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['g04', 'gold', 'open-meteo', 'medallion']
) as dag:

    # Tarea 1: Ejecutar el script DDL y carga de Dimensiones + Hechos
    crear_y_poblar_gold = PostgresOperator(
        task_id='crear_y_poblar_gold_tables',
        postgres_conn_id='postgres_default', # Conexión estándar configurada en el stack
        sql='sql/gold_clima.sql',
        outlets=[gold_clima_dataset] # Emite el asset al terminar con éxito
    )

    # Tarea 2: Crear / Actualizar las vistas analíticas para el Dashboard
    crear_vistas_analiticas = PostgresOperator(
        task_id='crear_vistas_analiticas',
        postgres_conn_id='postgres_default',
        sql='sql/gold_views.sql'
    )

    # Orden de ejecución secuencial
    crear_y_poblar_gold >> crear_vistas_analiticas