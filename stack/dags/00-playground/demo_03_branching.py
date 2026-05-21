from airflow.decorators import dag, task
from datetime import datetime
import random

@dag(
    dag_id='03_branching_taskflow',
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=['playground']
)
def dag_bifurcado():

    @task
    def obtener_numero():
        n = random.randint(1, 100)
        print(f"🔢 Número generado: {n}")
        return n

    @task.branch
    def decidir_camino(numero):
        if numero % 2 == 0:
            return "camino_par"
        return "camino_impar"

    @task
    def camino_par():
        print("✅ El número es PAR. Ejecutando lógica A.")

    @task
    def camino_impar():
        print("❌ El número es IMPAR. Ejecutando lógica B.")

    # Definimos el flujo
    num = obtener_numero()
    decidir_camino(num) >> [camino_par(), camino_impar()]

dag_bifurcado()
