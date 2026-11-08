import subprocess
import sys
from airflow.sdk import dag, task
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

@dag(
    dag_id="bronze_usgs_g07",
    schedule=None,
    catchup=False,
    tags=["G07", "bronze"]
)
def bronze_usgs_g07():

    @task
    def ingestar_sismos():
        subprocess.run(
            [sys.executable, "/opt/airflow/scripts/ingest_usgs.py"],
            check=True
        )

    iniciar_silver = TriggerDagRunOperator(
        task_id="iniciar_silver",
        trigger_dag_id="silver_usgs_g07",
        wait_for_completion=True,
        poke_interval=10
    )

    ingestar_sismos() >> iniciar_silver


bronze_usgs_g07()