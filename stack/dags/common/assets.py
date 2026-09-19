"""
Airflow Assets compartidos del pipeline crypto (clase06 - orquestacion data-aware).

=============================================================================
QUE ES UN ASSET (Airflow 3)
=============================================================================
Un `Asset` es un identificador logico de un "dato que existe" (una tabla, un
archivo, una particion). Sirve para encadenar DAGs por DATOS en vez de por
horario (cron):

  - El DAG PRODUCTOR declara, en la tarea que escribe el dato, que lo "produce":
        @task(outlets=[SILVER_CRYPTO])
        def load_silver(...): ...
    Cuando esa tarea termina OK, Airflow marca el asset como ACTUALIZADO.

  - El DAG CONSUMIDOR se programa POR el asset (no por cron):
        @dag(schedule=[SILVER_CRYPTO], ...)
    -> arranca solo cuando el productor actualiza el asset.

  - UN DAG PUEDE PUBLICAR VARIOS ASSETS, y cada uno tener su propio consumidor.
    `crypto_gold` emite GOLD_STAR (lo mira el dashboard) y GOLD_ABT (lo consume
    crypto_ml): dos salidas del mismo DAG, dos audiencias distintas, cada una
    avisada en el momento exacto en que SU dato quedo escrito.

  - Y al reves: si N DAGs declaran el mismo `schedule=[X]`, TODOS se disparan
    cuando X se actualiza. Un upstream, N downstream -- lo que el offset de
    cron no sabe expresar (tendrias que elegirle un minuto a cada uno).

=============================================================================
POR QUE DEFINIRLOS UNA SOLA VEZ ACA
=============================================================================
Productor y consumidor tienen que referirse al MISMO asset. Si cada DAG
construyera su propio `Asset(...)`, un typo en el nombre rompe el encadenado
en silencio. Definirlos una vez en `common` y que todos los importen garantiza
que el identificador coincida.

Se usan assets POR NOMBRE (sin URI) para evitar la validacion de "scheme"
reservado de Airflow 3 (p.ej. `postgres://` dispara warnings). El nombre es
suficiente como identificador logico para fines didacticos.
"""

from airflow.sdk import Asset

# =============================================================================
# LA CADENA PRODUCTIVA
# =============================================================================
# Un solo reloj, en el borde. De ahi en adelante, datos:
#
#   crypto_bronze   cron 0,15,30,45   --emite-->  BRONZE_CRYPTO
#   crypto_silver   schedule=[BRONZE_CRYPTO]   --emite-->  SILVER_CRYPTO
#   crypto_gold     schedule=[SILVER_CRYPTO]   --emite-->  GOLD_STAR + GOLD_ABT
#   crypto_ml       schedule=[GOLD_ABT]
#
# Bronze conserva cron porque es el BORDE: consulta una API externa y no tiene
# nada aguas arriba que esperar. Ningun otro DAG adivina tiempos.
#
# Consecuencia buscada: si Silver falla, Gold NO corre. Antes corria igual
# (cron) y publicaba Gold sobre datos viejos sin que nadie se enterara.

# Producido por crypto_bronze (la tarea load_markets declara outlets=[BRONZE_CRYPTO]).
BRONZE_CRYPTO = Asset(name="bronze_crypto_markets")

# Producido por crypto_silver (la tarea load_silver declara outlets=[SILVER_CRYPTO]).
SILVER_CRYPTO = Asset(name="silver_crypto_markets")

# Producidos por crypto_gold (el DAG productivo), que es el UNICO dueno de las
# tablas gold.* reales. Un dato, un dueno.
#   GOLD_STAR -> star schema BI (dim_* + fact_*) + las vistas semanticas gold.v_*
#                Consumidor: el dashboard Streamlit (localhost:8501).
#   GOLD_ABT  -> la ABT para ML (gold.gold_abt_crypto)
#                Consumidor: crypto_ml (scoring batch) y el workshop de clase06.
GOLD_STAR = Asset(name="gold_star")
GOLD_ABT = Asset(name="gold_abt")
