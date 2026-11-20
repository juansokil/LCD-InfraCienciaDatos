"""
Assets de Airflow 3 que encadenan el pipeline por DATOS, no por horario.

    usgs_bronze   cron cada 30 min  --emite-->  BRONZE_SISMOS
    usgs_silver   schedule=[BRONZE_SISMOS]  --emite-->  SILVER_SISMOS
    usgs_gold     schedule=[SILVER_SISMOS]  --emite-->  GOLD_SISMOS

- El productor declara el asset en la tarea que ESCRIBE el dato:
      @task(outlets=[BRONZE_SISMOS])
  Cuando esa tarea termina OK, Airflow registra un "asset event".
- El consumidor se programa por el asset:
      @dag(schedule=[BRONZE_SISMOS])
  y arranca solo cuando llega ese evento.

Hay un solo reloj, en el borde (Bronze), porque la API no avisa cuando hay
sismos nuevos. De ahi en adelante cada capa corre porque la anterior termino
de escribir: si Silver falla, Gold no corre sobre datos viejos.

Se definen UNA vez aca para que productor y consumidor usen exactamente el
mismo identificador (un typo en un nombre romperia la cadena en silencio).
"""

from airflow.sdk import Asset

BRONZE_SISMOS = Asset(name="bronze_usgs_sismos")
SILVER_SISMOS = Asset(name="silver_sismos")
GOLD_SISMOS = Asset(name="gold_sismos_estrella")
