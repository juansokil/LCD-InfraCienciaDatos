from airflow.decorators import dag, task
from datetime import datetime

@dag(
    dag_id='01_hola_mundo_taskflow',
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=['playground']
)
def hola_mundo():
    
    @task
    def saludar():
        return "👋 ¡Hola desde la TaskFlow API!"

    saludar()  
    
hola_mundo()
