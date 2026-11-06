import subprocess
import sys
from airflow.sdk import dag, task

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

    ingestar_sismos()

bronze_usgs_g07()