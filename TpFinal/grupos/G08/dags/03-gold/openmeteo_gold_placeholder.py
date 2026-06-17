from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="g08_openmeteo_gold_placeholder",
    start_date=datetime(2026, 6, 17),
    schedule="20 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g08", "gold", "placeholder"],
)
def openmeteo_gold_placeholder():
    @task
    def placeholder():
        print("Placeholder Gold: las tablas analiticas se agregaran despues.")

    placeholder()


openmeteo_gold_placeholder()
