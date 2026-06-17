from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="g08_openmeteo_silver_placeholder",
    start_date=datetime(2026, 6, 17),
    schedule="10 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g08", "silver", "placeholder"],
)
def openmeteo_silver_placeholder():
    @task
    def placeholder():
        print("Placeholder Silver: la limpieza real se agregara despues.")

    placeholder()


openmeteo_silver_placeholder()
