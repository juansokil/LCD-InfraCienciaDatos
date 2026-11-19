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

  - UN ASSET PUEDE TENER VARIOS CONSUMIDORES. `crypto_silver` emite
    SILVER_CRYPTO, y ahi arrancan DOS DAGs en paralelo: `crypto_gold`, que
    arma el star para BI, y `crypto_ml`, que arma lo suyo para ML. Un
    productor, N consumidores -- lo que el offset de cron no sabe expresar
    (tendrias que elegirle un minuto a cada uno).

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
#   crypto_gold     schedule=[SILVER_CRYPTO]   --emite-->  GOLD_STAR   (BI)
#   crypto_ml       schedule=[SILVER_CRYPTO]   --emite-->  GOLD_ABT    (ML)
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

# Cada tabla tiene UN dueno, y el asset lo declara el DAG que la escribe:
#   GOLD_STAR -> lo emite crypto_gold: star schema BI (dim_* + fact_*) + las
#                vistas semanticas gold.v_*, ya verificadas (sin huerfanos).
#                Las lee el dashboard Streamlit (localhost:8501), que no es un
#                DAG: consulta cuando alguien abre la pagina. Ningun DAG lo
#                consume hoy; se declara por lo mismo que GOLD_ABT, abajo.
#   GOLD_ABT  -> lo emite crypto_ml: la ABT para ML (gold.gold_abt_crypto), que
#                es la forma que el pipeline de ML le da a los datos. Hoy no
#                tiene consumidor aguas abajo; se declara porque documenta que
#                ese dato existe y deja colgar otro DAG sin tocar este.
GOLD_STAR = Asset(name="gold_star")
GOLD_ABT = Asset(name="gold_abt")
