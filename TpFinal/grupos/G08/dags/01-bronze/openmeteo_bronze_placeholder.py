from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="g08_openmeteo_bronze_placeholder",
    start_date=datetime(2026, 6, 17),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g08", "bronze", "placeholder"],
)
def openmeteo_bronze_placeholder():
    @task
    def placeholder():
        print("Placeholder Bronze: la ingesta real de Open-Meteo se agregara despues.")

    placeholder()


openmeteo_bronze_placeholder()
