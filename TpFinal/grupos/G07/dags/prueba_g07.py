from airflow.sdk import dag, task


@dag(
    dag_id="prueba_g07",
    schedule=None,
    catchup=False,
    tags=["G07", "prueba"]
)
def prueba_g07():

    @task
    def saludar():
        print("TP Final del grupo G07")

    saludar()


prueba_g07()
