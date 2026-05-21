from airflow.decorators import dag, task
from datetime import datetime
import random


@dag(
    dag_id='02_secuencia_taskflow',
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=['playground']
)
def task_flow():

    @task
    def generar_numero():
        return random.randint(1, 100)

    @task
    def sumar_diez(n):
        print(f"➕ Recibido: {n}. Sumando 10...")
        return n + 10

    sumar_diez(generar_numero())

task_flow()
