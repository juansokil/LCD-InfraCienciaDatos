"""Assets del pipeline G06: el "cable" que encadena las capas.

Solo Bronze tiene reloj (cron), porque es el borde: le pide datos a la API.
De ahi en adelante, cada capa arranca cuando la anterior termino de escribir:

    g06_bronze  cron horario          --emite-->  BRONZE_OPENMETEO
    g06_silver  schedule=[BRONZE]     --emite-->  SILVER_OPENMETEO
    g06_gold    schedule=[SILVER]     --emite-->  GOLD_OPENMETEO

Se definen en UN solo lugar: si cada DAG escribiera su propio Asset(...),
un error de tipeo en el nombre cortaria la cadena sin ningun aviso.
"""
from airflow.sdk import Asset

BRONZE_OPENMETEO = Asset(name="bronze_openmeteo")
SILVER_OPENMETEO = Asset(name="silver_openmeteo")
GOLD_OPENMETEO = Asset(name="gold_openmeteo")
