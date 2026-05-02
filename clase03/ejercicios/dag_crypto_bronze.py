# =============================================================================
# =============================================================================
#
#   UNSAM - Licenciatura en Ciencia de Datos
#   Data Engineering - Clase 03
#
#   ARCHIVO EDUCATIVO: DAG de Ingesta Bronze desde CoinGecko API
#
#   Este archivo es una copia COMENTADA del DAG de produccion.
#   El codigo es identico; los comentarios explican cada decision
#   de diseno para que puedan entenderlo y modificarlo.
#
# =============================================================================
# =============================================================================

"""
DAG: crypto_bronze
Clase 03 - Ingesta desde API CoinGecko a Capa Bronze

Pipeline: API CoinGecko -> DataFrame -> bronze.crypto_markets + bronze.global_market
Dos endpoints en paralelo:
  - /coins/markets -> top 50 criptos (datos por moneda)
  - /global -> datos agregados del mercado crypto total

Corre cada 5 minutos, acumulando snapshots con precios en tiempo real.
"""

# =============================================================================
# IMPORTS
# =============================================================================
# QUE ES UN DAG?
# ---------------
# DAG = Directed Acyclic Graph (Grafo Dirigido Aciclico).
# En Apache Airflow, un DAG es la definicion de un pipeline de datos:
# un conjunto de TAREAS (tasks) conectadas entre si con un orden de ejecucion.
#
#   - "Dirigido" = las tareas tienen una direccion (A -> B significa "A corre
#     antes que B"). No es bidireccional.
#   - "Aciclico" = no puede haber ciclos (A -> B -> C -> A seria invalido).
#     Esto garantiza que el pipeline siempre termina.
#
# Airflow lee TODOS los archivos .py de la carpeta "dags/" cada pocos segundos
# y busca objetos DAG. Cada DAG que encuentre aparece en la interfaz web
# (localhost:8080) donde podemos: monitorearlo, ejecutarlo manualmente,
# ver logs, pausarlo, etc.
#
# DECORADORES @dag y @task (TaskFlow API)
# ----------------------------------------
# Desde Airflow 2.0+ existe la "TaskFlow API" que permite definir DAGs y
# tareas usando decoradores de Python, de forma mucho mas limpia:
#
#   @dag   -> Convierte una funcion en la DEFINICION de un DAG completo.
#             Los parametros del decorador (schedule, catchup, etc.) configuran
#             el comportamiento del DAG.
#
#   @task  -> Convierte una funcion en una TAREA dentro del DAG.
#             Lo que la funcion retorna se guarda automaticamente en XCom
#             (mecanismo interno de Airflow para pasar datos entre tareas).
#
# Sin estos decoradores, tendriamos que usar clases como PythonOperator,
# manejar XCom manualmente con ti.xcom_push() / ti.xcom_pull(), etc.
# Los decoradores simplifican enormemente el codigo.
# =============================================================================
from airflow.decorators import dag, task
from datetime import datetime
import math
import os


# =============================================================================
# CONEXION A BASE DE DATOS
# =============================================================================
# URI de conexion a PostgreSQL siguiendo el formato de SQLAlchemy:
#
#   postgresql+psycopg2://usuario:password@host:puerto/base_de_datos
#
# Desglosando:
#   - postgresql   = tipo de base de datos
#   - psycopg2     = driver (adaptador) que Python usa para hablar con PostgreSQL
#   - admin:admin  = usuario y password (definidos en docker-compose.yml)
#   - postgres      = hostname del servicio Docker (NO es "localhost" porque
#                    estamos DENTRO de la red de Docker)
#   - 5432         = puerto por defecto de PostgreSQL
#   - InfraCienciaDatos = nombre de la base de datos
#
# IMPORTANTE: En produccion NUNCA pondriamos credenciales hardcodeadas en el
# codigo. Usariamos Airflow Connections, variables de entorno, o un gestor
# de secretos (como AWS Secrets Manager o HashiCorp Vault). Aqui lo
# simplificamos para fines educativos.
# =============================================================================
DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


# =============================================================================
# FUNCION AUXILIAR: Limpieza de NaN/inf para serializacion JSON (XCom)
# =============================================================================
# POR QUE EXISTE ESTA FUNCION?
#
# Cuando una @task retorna datos, Airflow los serializa a JSON para guardarlos
# en XCom (la base de datos interna que comparte datos entre tareas).
#
# El PROBLEMA: JSON estandar (RFC 8259) NO soporta estos valores especiales
# de Python/float:
#
#   - NaN (Not a Number): aparece cuando un dato numerico no existe, es
#     invalido, o resulta de operaciones como 0/0.
#     Ejemplo: max_supply de Ethereum es None -> pd.to_numeric lo convierte a NaN.
#
#   - inf / -inf (infinito): aparece en divisiones por cero u operaciones
#     matematicas extremas.
#     Ejemplo: algun calculo de porcentaje donde el denominador es 0.
#
#   - datetime / Timestamp de Pandas: son objetos Python que el serializador
#     JSON no sabe convertir a string automaticamente.
#
# Si intentamos serializar {"price": float('nan')} a JSON, Airflow explota con:
#   ValueError: Out of range float values are not JSON compliant
#
# LA SOLUCION: recorrer todos los registros y reemplazar NaN/inf por None.
# En JSON, None de Python se convierte en "null", que es un valor valido.
#
# NOTA: Los objetos datetime y Timestamp de Pandas tambien causan problemas
# de serializacion. Por eso mas adelante convertimos las fechas a strings con
# .isoformat() y .strftime() ANTES de retornar datos desde las tareas.
# =============================================================================
def _clean_records(records):
    """Limpiar NaN/inf de records para que XCom (JSON) no explote."""
    for row in records:
        for k, v in row.items():
            # math.isnan() y math.isinf() solo funcionan con tipo float,
            # por eso PRIMERO verificamos isinstance(v, float).
            # Si v fuera un string o int, math.isnan() lanzaria TypeError.
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
    return records


# =============================================================================
# DEFINICION DEL DAG CON EL DECORADOR @dag
# =============================================================================
# Cada parametro del decorador @dag configura un aspecto del DAG.
# Veamos que hace cada uno:
#
#   dag_id="crypto_bronze"
#     Nombre UNICO del DAG. Es lo que aparece en la interfaz web de Airflow.
#     Convencion: usamos el nombre del dominio + la capa (crypto_bronze).
#
#   start_date=datetime(2024, 1, 1)
#     Fecha desde la cual Airflow "considera" que el DAG existe.
#     NO significa que va a ejecutar desde esa fecha (eso depende de catchup).
#     Es solo una referencia temporal para el scheduler.
#
#   schedule="*/5 * * * *"
#     Frecuencia de ejecucion usando sintaxis CRON (estandar de Unix).
#     Los 5 campos son: minuto hora dia_mes mes dia_semana
#       */5 * * * * = "cada 5 minutos, cualquier hora, cualquier dia"
#     Otros ejemplos:
#       "0 * * * *"    = cada hora en punto (minuto 0)
#       "0 8 * * *"    = todos los dias a las 08:00
#       "0 0 * * 1"    = cada lunes a medianoche
#       "@daily"        = alias para "0 0 * * *"
#
#   catchup=False
#     CRITICO: si el DAG estuvo apagado 2 horas, NO ejecuta las ~24 corridas
#     que se "perdieron". Solo ejecuta la proxima.
#     Con catchup=True, Airflow intentaria ejecutar TODAS las corridas
#     pendientes desde start_date. Para APIs en tiempo real como precios,
#     esto no tiene sentido porque los datos historicos ya no estan disponibles.
#
#   tags=["bronze", "crypto"]
#     Etiquetas para filtrar y organizar DAGs en la UI de Airflow.
#     "bronze" indica la capa del data lake; "crypto" el dominio de datos.
#
#   doc_md="..."
#     Documentacion en Markdown que aparece en la UI de Airflow cuando
#     hacemos click en el DAG y vamos a la pestana "Docs".
# =============================================================================
@dag(
    dag_id="crypto_bronze",
    start_date=datetime(2024, 1, 1),
    schedule="*/5 * * * *",
    catchup=False,
    tags=["bronze", "crypto"],
    doc_md="""
    ## Crypto Bronze - Ingesta cada 5 minutos
    Consulta **dos endpoints** de CoinGecko en paralelo:
    - Top 50 criptomonedas por market cap -> `bronze.crypto_markets`
    - Datos globales del mercado crypto -> `bronze.global_market`

    Cada corrida genera un snapshot unico (los precios cambian constantemente).
    """,
)
def crypto_bronze():

    # ============================================================
    # ENDPOINT 1: /coins/markets (datos por cripto)
    # ============================================================
    # QUE ES COINGECKO?
    # CoinGecko es una plataforma que agrega datos de criptomonedas de
    # cientos de exchanges (Binance, Coinbase, etc.). Su API es gratuita
    # (con limites de uso) y NO requiere API key.
    #
    # QUE DEVUELVE /coins/markets?
    # Una lista (array JSON) de objetos, uno por cada criptomoneda, con
    # campos como:
    #   - id, symbol, name: identificacion de la moneda
    #   - current_price: precio actual en la moneda de referencia (USD)
    #   - market_cap: capitalizacion de mercado (precio * supply circulante)
    #   - total_volume: volumen total operado en las ultimas 24hs
    #   - high_24h, low_24h: maximo y minimo en las ultimas 24hs
    #   - ath (all-time high): precio maximo historico
    #   - atl (all-time low): precio minimo historico
    #   - circulating_supply, total_supply, max_supply: datos de oferta
    #   - y ~30 campos mas...
    #
    # Es como una "tabla" donde cada fila es una moneda (BTC, ETH, SOL, etc.)
    # y cada columna es una metrica financiera.
    #
    # NOTA SOBRE IMPORTS DENTRO DE LAS FUNCIONES:
    # En Airflow, es buena practica importar librerias DENTRO de las tareas
    # (no al inicio del archivo). Esto es porque Airflow parsea TODOS los
    # archivos .py de la carpeta dags/ cada pocos segundos para detectar
    # cambios. Si importamos librerias pesadas (pandas, requests) a nivel
    # de modulo, cada parseo seria mas lento. Importar dentro de la funcion
    # hace que la libreria solo se cargue cuando la tarea realmente se ejecuta.
    # ============================================================
    @task
    def fetch_markets():
        """Consultar CoinGecko API - Top 50 criptomonedas."""
        import requests

        url = "https://api.coingecko.com/api/v3/coins/markets"

        # Parametros de la query (se envian como ?vs_currency=usd&order=... en la URL).
        # Estos parametros controlan QUE datos le pedimos a la API:
        params = {
            "vs_currency": "usd",        # Precios expresados en dolares (USD)
            "order": "market_cap_desc",   # Ordenar por market cap, de mayor a menor
            "per_page": 50,               # Top 50 criptomonedas (las mas grandes)
            "page": 1,                    # Primera pagina de resultados
            "sparkline": False,           # No incluir datos para mini-graficos (ahorra bandwidth)
        }

        print("Consultando CoinGecko /coins/markets ...")
        response = requests.get(url, params=params)

        # raise_for_status() lanza una excepcion HTTPError si el status code
        # es 4xx (error del cliente) o 5xx (error del servidor).
        # Por ejemplo: 429 Too Many Requests, 500 Internal Server Error.
        # Esto hace que Airflow marque la tarea como FAILED y podamos ver
        # el error detallado en los logs. Sin esto, podriamos procesar una
        # respuesta de error sin darnos cuenta.
        response.raise_for_status()

        data = response.json()
        print(f"Registros obtenidos: {len(data)}")

        # El return guarda 'data' automaticamente en XCom gracias al decorador @task.
        # La siguiente tarea (transform_markets) puede recibirlo como parametro.
        return data

    # ============================================================
    # ENDPOINT 2: /global (datos del mercado total)
    # ============================================================
    # QUE DEVUELVE /global?
    # Un UNICO objeto JSON con datos AGREGADOS de todo el mercado crypto:
    #   - active_cryptocurrencies: cuantas criptos existen (~14,000+)
    #   - markets: cantidad de exchanges/mercados
    #   - total_market_cap: market cap total en distintas monedas fiat
    #       {"usd": 2500000000000, "eur": 2200000000000, ...}
    #   - total_volume: volumen total de operaciones en 24hs
    #   - market_cap_percentage: dominancia de cada cripto
    #       {"btc": 52.5, "eth": 16.3, "usdt": 3.8, ...}
    #     (BTC domina ~50% del mercado total, ETH ~15-20%)
    #   - market_cap_change_percentage_24h_usd: cambio % del mercado en 24hs
    #
    # POR QUE USAMOS 2 ENDPOINTS?
    # Porque son datos COMPLEMENTARIOS que responden preguntas distintas:
    #
    #   /coins/markets -> "Cuanto vale Bitcoin HOY? Y Ethereum?"
    #                     (detalle INDIVIDUAL por moneda)
    #
    #   /global        -> "Como esta el mercado crypto EN GENERAL?"
    #                     (contexto MACRO del mercado total)
    #
    # En analisis, combinar ambos datasets es poderoso. Podemos responder:
    #   - "BTC subio 5%, pero el mercado total subio 7%. Entonces BTC subio
    #     MENOS que el promedio del mercado (bajo en terminos relativos)."
    #   - "La dominancia de BTC bajo del 55% al 48%. Los altcoins estan
    #     ganando terreno."
    #   - "El volumen total del mercado se duplico: hay mucha actividad."
    #
    # RATE LIMIT Y REINTENTOS:
    # -------------------------
    # El decorador @task acepta parametros adicionales:
    #   retries=2    -> si la tarea falla, Airflow la REINTENTA hasta 2 veces mas
    #   retry_delay=10 -> espera 10 segundos entre cada reintento
    #
    # Esto es CRITICO para APIs externas que pueden:
    #   - Devolver HTTP 429 (Too Many Requests) por rate limiting
    #   - Tener caidas temporales (errores 500, 502, 503)
    #   - Sufrir timeouts por congestion de red
    #
    # CoinGecko FREE TIER tiene un limite de ~10-30 requests por minuto.
    # Si lo excedemos, devuelve HTTP 429 y nos bloquea temporalmente.
    # Con retries=2 y retry_delay=10, tenemos 3 intentos totales
    # (1 original + 2 reintentos) con 10 segundos de espera entre cada uno.
    # ============================================================
    @task(retries=2, retry_delay=10)
    def fetch_global():
        """Consultar CoinGecko API - Datos globales del mercado."""
        import requests
        import time

        # =============================================================
        # SLEEP PARA RESPETAR EL RATE LIMIT
        # =============================================================
        # Esperamos 5 segundos ANTES de hacer la request.
        # Esto es porque fetch_markets() ya hizo una request justo antes,
        # y CoinGecko (free tier) puede rechazarnos si hacemos requests
        # demasiado seguidas (HTTP 429 - Too Many Requests).
        #
        # En produccion, usariamos estrategias mas sofisticadas:
        #   - Backoff exponencial (esperar 1s, luego 2s, luego 4s, ...)
        #   - Token bucket rate limiter
        #   - Cache de respuestas (no pedir si ya tenemos datos recientes)
        #   - API key de pago (limites mucho mas altos: 500+ req/min)
        #
        # Pero para el curso, un sleep(5) simple y explicito es suficiente.
        # =============================================================
        time.sleep(5)

        url = "https://api.coingecko.com/api/v3/global"

        print("Consultando CoinGecko /global ...")
        response = requests.get(url)
        response.raise_for_status()

        # La respuesta de /global viene ENVUELTA en un objeto:
        #   {"data": { ...los datos reales... }}
        # Por eso accedemos a ["data"] para obtener el contenido que nos interesa.
        # Esto es un patron comun en APIs: envolver la respuesta real en un campo "data".
        data = response.json()["data"]
        print(f"Mercado global: {data.get('active_cryptocurrencies', '?')} criptos activas")
        return data

    # ============================================================
    # TRANSFORM: markets
    # ============================================================
    # Esta tarea toma los datos crudos de /coins/markets y los PREPARA
    # para cargarse en la base de datos. Hace 3 cosas:
    #   1) Selecciona solo las columnas relevantes (de ~30 a 22)
    #   2) Corrige los tipos de datos (type coercion)
    #   3) Agrega columnas de metadata (ingested_at, snapshot_ts)
    #
    # El parametro "data: list" recibe AUTOMATICAMENTE el valor retornado
    # por fetch_markets() gracias al sistema XCom del decorador @task.
    # Airflow resuelve esta dependencia cuando conectamos las tareas al
    # final de la funcion del DAG.
    # ============================================================
    @task
    def transform_markets(data: list):
        """Seleccionar columnas, tipar y agregar metadata."""
        import pandas as pd

        # Convertimos la lista de diccionarios a un DataFrame de Pandas.
        # Cada elemento de 'data' es un dict con ~30+ campos por moneda.
        df = pd.DataFrame(data)

        # =============================================================
        # SELECCION DE COLUMNAS: POR QUE ESTAS 22 COLUMNAS?
        # =============================================================
        # La API devuelve ~30+ columnas por moneda, pero no todas son utiles
        # para nuestro analisis. Seleccionamos 22 columnas organizadas en
        # categorias tematicas:
        #
        # -- IDENTIFICACION (3 columnas): id, symbol, name --
        #   Necesarias para saber DE QUE moneda estamos hablando.
        #   - "id": identificador unico de CoinGecko (ej: "bitcoin", "ethereum")
        #   - "symbol": ticker de la moneda (ej: "btc", "eth", "sol")
        #   - "name": nombre legible (ej: "Bitcoin", "Ethereum")
        #
        # -- PRECIOS (4 columnas): current_price, high_24h, low_24h, price_change_24h --
        #   El precio actual y su rango en las ultimas 24 horas.
        #   - current_price: precio ahora mismo en USD
        #   - high_24h / low_24h: maximo y minimo de las ultimas 24hs
        #   - price_change_24h: cambio absoluto (en USD) respecto a hace 24hs
        #   Fundamental para cualquier analisis financiero.
        #
        # -- CAMBIOS PORCENTUALES (3 columnas) --
        #   price_change_percentage_24h, market_cap_change_24h,
        #   market_cap_change_percentage_24h
        #   Permiten medir la VOLATILIDAD y TENDENCIA reciente.
        #   Utiles para alertas: "si BTC cae mas de 5% en 24hs, avisar".
        #
        # -- MARKET CAP Y VOLUMEN (4 columnas) --
        #   market_cap, market_cap_rank, fully_diluted_valuation, total_volume
        #   - market_cap = precio * circulating_supply (valor total de la moneda)
        #   - market_cap_rank = posicion en el ranking (BTC=1, ETH=2, ...)
        #   - fully_diluted_valuation = market cap SI todas las monedas existieran
        #     (incluye las que aun no se "minaron" o emitieron)
        #   - total_volume = cuanto se opero en 24hs (indicador de LIQUIDEZ)
        #
        # -- SUPPLY (3 columnas): circulating_supply, total_supply, max_supply --
        #   Datos sobre la OFERTA de monedas:
        #   - circulating_supply: monedas actualmente en circulacion
        #   - total_supply: monedas creadas (incluye bloqueadas/quemadas)
        #   - max_supply: limite MAXIMO de monedas que pueden existir
        #     Bitcoin tiene max_supply = 21,000,000 (finito, como el oro)
        #     Ethereum NO tiene max_supply (None/NaN en los datos)
        #
        # -- ATH/ATL HISTORICOS (6 columnas) --
        #   ath, ath_change_percentage, ath_date, atl, atl_change_percentage, atl_date
        #   - ATH = All-Time High (precio MAXIMO historico de la moneda)
        #   - ATL = All-Time Low (precio MINIMO historico de la moneda)
        #   - ath_change_percentage: cuanto esta por debajo del maximo (-30% = esta
        #     a 30% de su record)
        #   - Las fechas indican CUANDO se alcanzo el ATH/ATL
        #   Contexto historico: "BTC esta a -25% de su maximo historico"
        #
        # -- TIMESTAMP DE LA API (1 columna): last_updated --
        #   Cuando CoinGecko actualizo este dato por ultima vez.
        #   Util para detectar datos "stale" (viejos/desactualizados).
        #
        # COLUMNAS QUE NO SELECCIONAMOS (y por que):
        #   - image: URL del logo de la moneda, no es un dato numerico util
        #   - roi: retorno sobre inversion, viene null para muchas monedas
        #   - sparkline_in_7d: datos para mini-graficos, muy pesado en bytes
        # =============================================================
        columnas_bronze = [
            # Identificacion
            "id", "symbol", "name",
            # Precios
            "current_price", "high_24h", "low_24h", "price_change_24h",
            # Cambios porcentuales
            "price_change_percentage_24h",
            "market_cap_change_24h", "market_cap_change_percentage_24h",
            # Market cap y volumen
            "market_cap", "market_cap_rank", "fully_diluted_valuation", "total_volume",
            # Supply
            "circulating_supply", "total_supply", "max_supply",
            # ATH/ATL historicos
            "ath", "ath_change_percentage", "ath_date",
            "atl", "atl_change_percentage", "atl_date",
            # Timestamp de la API
            "last_updated",
        ]

        # .copy() crea una copia INDEPENDIENTE del DataFrame.
        # Sin copy(), tendriamos un "view" (vista) del DataFrame original.
        # Modificar un view puede generar SettingWithCopyWarning en Pandas
        # y comportamientos inesperados. Con copy() estamos seguros.
        df = df[columnas_bronze].copy()

        # =============================================================
        # TYPE COERCION: pd.to_numeric(errors="coerce")
        # =============================================================
        # Los datos de la API pueden venir como strings, None, o tipos mixtos
        # en una misma columna. pd.to_numeric() intenta convertir cada valor
        # a un tipo numerico (int o float).
        #
        # El parametro errors="coerce" es la CLAVE de esta operacion:
        #
        #   errors="raise" (default): LANZA ERROR si encuentra un valor no numerico.
        #     Peligroso: un solo dato malo rompe TODO el pipeline.
        #
        #   errors="coerce": convierte valores no numericos a NaN silenciosamente.
        #     Seguro: no perdemos datos (queda NaN para investigar despues) y
        #     no rompemos el pipeline.
        #
        #   errors="ignore": deja los valores como estan sin convertir.
        #     Riesgoso: la columna queda con tipos mixtos (string + float).
        #
        # Ejemplos concretos:
        #   pd.to_numeric(None, errors="coerce")      -> NaN
        #   pd.to_numeric("N/A", errors="coerce")     -> NaN
        #   pd.to_numeric("21000000", errors="coerce") -> 21000000.0
        #   pd.to_numeric(42000.5, errors="coerce")    -> 42000.5 (ya es numerico)
        #
        # Usamos "coerce" porque es la estrategia mas segura para la capa Bronze:
        # preservamos todos los datos posibles sin detener la ingesta.
        # =============================================================
        numeric_cols = [
            "current_price", "high_24h", "low_24h", "price_change_24h",
            "price_change_percentage_24h",
            "market_cap_change_24h", "market_cap_change_percentage_24h",
            "market_cap", "market_cap_rank", "fully_diluted_valuation", "total_volume",
            "circulating_supply", "total_supply", "max_supply",
            "ath", "ath_change_percentage", "atl", "atl_change_percentage",
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # =============================================================
        # COLUMNAS DE METADATA: ingested_at y snapshot_ts
        # =============================================================
        # Estas columnas NO vienen de la API. Las AGREGAMOS nosotros para
        # darle contexto temporal a cada registro. Son fundamentales en
        # cualquier pipeline de datos serio.
        #
        # ingested_at: momento EXACTO en que ingestamos los datos.
        #   - Formato ISO 8601: "2024-03-15T14:30:45.123456"
        #   - Precision: hasta microsegundos.
        #   - Uso principal: AUDITORIA. "A que hora exacta corrio este pipeline?"
        #   - Usamos .isoformat() para convertir el objeto datetime a STRING,
        #     porque los objetos datetime de Python NO son serializables a JSON
        #     (XCom necesita JSON puro, y datetime no es un tipo JSON valido).
        #
        # snapshot_ts: marca temporal redondeada al minuto.
        #   - Formato: "2024-03-15 14:30" (sin segundos ni microsegundos)
        #   - Uso principal: AGRUPAR registros de la misma corrida.
        #   - Todas las 50 criptos de una misma corrida comparten snapshot_ts.
        #   - Permite consultas como:
        #       SELECT * FROM bronze.crypto_markets WHERE snapshot_ts = '2024-03-15 14:30'
        #     para obtener exactamente un snapshot completo.
        #
        # POR QUE DOS CAMPOS DE TIEMPO?
        #   - ingested_at es para AUDITAR (precision exacta, unica por corrida)
        #   - snapshot_ts es para AGRUPAR y CONSULTAR (redondeado, mas practico)
        #
        # Ejemplo: si el DAG corre a las 14:30:47.123456:
        #   ingested_at = "2024-03-15T14:30:47.123456" (momento exacto)
        #   snapshot_ts = "2024-03-15 14:30"            (para agrupar los 50 registros)
        # =============================================================
        now = datetime.now()
        df["ingested_at"] = now.isoformat()
        df["snapshot_ts"] = now.strftime("%Y-%m-%d %H:%M")

        print(f"Snapshot: {df['snapshot_ts'].iloc[0]} | {df.shape[0]} registros, {df.shape[1]} columnas")

        # =============================================================
        # SERIALIZACION SEGURA PARA XCOM (paso de datos entre tareas)
        # =============================================================
        # df.to_dict(orient="records") convierte el DataFrame a una lista
        # de diccionarios:
        #   [{"id": "bitcoin", "current_price": 42000, ...},
        #    {"id": "ethereum", "current_price": 2200, ...}, ...]
        #
        # Luego _clean_records() recorre cada registro y reemplaza
        # NaN/inf por None para que la serializacion JSON de XCom no falle.
        #
        # Este es un PATRON COMUN en Airflow con TaskFlow API:
        #   DataFrame -> to_dict("records") -> limpiar NaN/inf -> return (XCom)
        #
        # Alternativas que NO funcionan bien:
        #   - Retornar el DataFrame directamente: XCom no puede serializar
        #     objetos Pandas a JSON.
        #   - Usar to_json(): devuelve un string JSON, no una estructura Python
        #     que Airflow pueda inspeccionar en la UI.
        # =============================================================
        return _clean_records(df.to_dict(orient="records"))

    # ============================================================
    # TRANSFORM + LOAD: global
    # ============================================================
    # Esta tarea combina transformacion Y carga en una sola funcion.
    # Es mas simple que markets porque solo hay UN registro (no una tabla
    # de 50 filas). Separar transform y load seria over-engineering aqui.
    #
    # Notar que recibe "data: dict" (un DICCIONARIO, no una lista),
    # porque /global devuelve un unico objeto con datos del mercado total.
    # ============================================================
    @task
    def load_global(data: dict):
        """Transformar y cargar datos globales en bronze.global_market."""
        import pandas as pd
        import sqlalchemy

        now = datetime.now()

        # Extraemos manualmente los campos que nos interesan del JSON anidado.
        # Usamos .get() con valores default ({}) para evitar KeyError si falta
        # un campo. Sin .get(), data["total_market_cap"]["usd"] lanzaria
        # KeyError si "total_market_cap" no existiera.
        #
        # Algunos campos estan ANIDADOS (dict dentro de dict):
        #   data["total_market_cap"] = {"usd": 2.5e12, "eur": 2.2e12, ...}
        #   data["market_cap_percentage"] = {"btc": 52.5, "eth": 16.3, ...}
        # Solo nos quedamos con el valor en USD o la moneda relevante.
        row = {
            "active_cryptocurrencies": data.get("active_cryptocurrencies"),
            "markets": data.get("markets"),
            # .get("total_market_cap", {}).get("usd") es un patron de "safe navigation":
            # si "total_market_cap" no existe, retorna {} (dict vacio),
            # y luego .get("usd") sobre un dict vacio retorna None.
            # Nunca lanza excepcion, siempre retorna algo valido.
            "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
            "total_volume_usd": data.get("total_volume", {}).get("usd"),
            # DOMINANCIA: que porcentaje del market cap total corresponde a BTC/ETH.
            # Es un indicador clave del mercado:
            #   - Si btc_dominance SUBE: el mercado se "concentra" en Bitcoin
            #     (los inversores buscan seguridad en la cripto mas grande).
            #   - Si btc_dominance BAJA: los altcoins estan ganando terreno
            #     (se llama "alt season" cuando esto pasa fuertemente).
            "btc_dominance": data.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance": data.get("market_cap_percentage", {}).get("eth"),
            "market_cap_change_pct_24h": data.get("market_cap_change_percentage_24h_usd"),
            # Mismas columnas de metadata que en markets, para consistencia
            # entre ambas tablas Bronze.
            "ingested_at": now.isoformat(),
            "snapshot_ts": now.strftime("%Y-%m-%d %H:%M"),
        }

        df = pd.DataFrame([row])
        engine = sqlalchemy.create_engine(DB_URI)

        # =============================================================
        # ESTRATEGIA BRONZE: if_exists="append" (ACUMULAR datos crudos)
        # =============================================================
        # En la arquitectura Medallion (Bronze -> Silver -> Gold):
        #
        # BRONZE = datos CRUDOS, tal cual vienen de la fuente, con minima
        #   transformacion. Es nuestro "archivo historico".
        #   - Usamos "append" para ACUMULAR cada snapshot sin borrar los anteriores.
        #   - Cada corrida (cada 5 min) agrega un nuevo registro.
        #   - NUNCA borramos datos en Bronze: es nuestro backup/respaldo historico.
        #   - Si algo sale mal en Silver o Gold, siempre podemos REPROCESAR
        #     desde Bronze (es la fuente de verdad).
        #
        # SILVER = datos LIMPIADOS, validados, deduplicados, con esquema definido.
        #   - Aqui podriamos usar "replace" o UPSERT para mantener solo la
        #     version mas reciente de cada registro.
        #
        # GOLD = datos AGREGADOS, optimizados para dashboards y reportes.
        #   - Tablas orientadas a preguntas de negocio especificas.
        #
        # La alternativa if_exists="replace" BORRARIA toda la tabla y la
        # recrearia con SOLO los datos nuevos de esta corrida. En Bronze,
        # NUNCA queremos esto porque perderiamos todo el historial de precios
        # y no podriamos hacer analisis temporal.
        # =============================================================
        df.to_sql("global_market", engine, schema="bronze", if_exists="append", index=False)

        print(f"bronze.global_market: +1 registro | BTC dom: {row['btc_dominance']:.1f}%")

    # ============================================================
    # LOAD: markets
    # ============================================================
    @task
    def load_markets(records: list):
        """Acumular en bronze.crypto_markets (append directo)."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)
        engine = sqlalchemy.create_engine(DB_URI)

        # Append: cada corrida agrega 50 registros (uno por moneda).
        # Velocidad de crecimiento de la tabla:
        #   - 1 hora  = 12 corridas * 50 monedas = 600 registros
        #   - 1 dia   = 288 corridas * 50 monedas = 14,400 registros
        #   - 1 semana = ~100,800 registros
        #
        # Este crecimiento es INTENCIONAL en Bronze: queremos el historial
        # completo para poder analizar tendencias de precios, calcular
        # promedios moviles, detectar anomalias, etc.
        #
        # Si la tabla crece demasiado, la solucion NO es borrar datos de Bronze,
        # sino particionar la tabla por fecha, archivar datos viejos en
        # almacenamiento frio (S3, GCS), o crear tablas Silver resumidas.
        df.to_sql("crypto_markets", engine, schema="bronze", if_exists="append", index=False)

        # Consultas de VERIFICACION: cuantos registros y snapshots tenemos en total.
        # Esto aparece en los logs de Airflow y es util para monitorear
        # que el pipeline funciona correctamente sin necesidad de abrir
        # la base de datos manualmente.
        total = pd.read_sql("SELECT COUNT(*) as n FROM bronze.crypto_markets", engine)["n"][0]
        snapshots = pd.read_sql(
            "SELECT COUNT(DISTINCT snapshot_ts) as n FROM bronze.crypto_markets", engine
        )["n"][0]

        print(f"+{len(df)} registros ({df.shape[1]} cols) | Total: {total} ({snapshots} snapshots)")

    # ============================================================
    # FLUJO DEL DAG: Definicion de dependencias entre tareas
    # ============================================================
    # Aqui es donde conectamos las tareas y definimos el ORDEN de ejecucion.
    #
    # Con la TaskFlow API, las dependencias se definen de forma IMPLICITA:
    # si una tarea recibe como parametro el resultado de otra, Airflow
    # entiende automaticamente que debe ejecutar primero la que produce el dato.
    #
    # FLUJO SECUENCIAL PARA EVITAR RATE LIMIT:
    # ------------------------------------------
    # Ejecutamos los endpoints de forma SECUENCIAL (markets primero, global
    # despues), NO en paralelo. Aunque Airflow soporta ejecucion paralela,
    # lo evitamos por una razon practica:
    #
    # CoinGecko free tier tiene rate limits estrictos (~10-30 req/min).
    # Si lanzamos 2 requests SIMULTANEAS, es mas probable que una falle
    # con HTTP 429 (Too Many Requests) porque el servidor ve 2 requests
    # llegando al mismo tiempo desde la misma IP.
    #
    # El flujo resultante es:
    #
    #   fetch_markets -> transform_markets -> load_markets
    #                                                       |
    #                                                       v (secuencial)
    #                                            fetch_global -> load_global
    #
    # Asi, cuando fetch_global() se ejecuta, ya pasaron varios segundos
    # desde fetch_markets() (el tiempo de transform + load), MAS los 5
    # segundos de sleep() que tiene fetch_global() internamente.
    # Esto reduce drasticamente el riesgo de rate limiting.
    #
    # Si tuvieramos una API key de pago con limites altos, podriamos
    # ejecutar ambos pipelines en paralelo para mayor velocidad.
    # ============================================================

    # Pipeline de markets: fetch -> transform -> load
    raw_markets = fetch_markets()
    transformed = transform_markets(raw_markets)
    loaded = load_markets(transformed)

    # Pipeline de global: fetch -> load
    # Se ejecuta DESPUES de markets porque Airflow ejecuta las tareas
    # en el orden en que se definen cuando no hay dependencia explicita,
    # y ademas fetch_global() tiene el sleep(5) interno como proteccion.
    raw_global = fetch_global()
    load_global(raw_global)


# =============================================================================
# INSTANCIACION DEL DAG
# =============================================================================
# Esta linea es OBLIGATORIA. Llama a la funcion decorada con @dag para
# crear el objeto DAG que Airflow necesita detectar.
#
# Sin esta linea, Airflow parsea el archivo, ve que hay una funcion decorada
# con @dag, pero como nunca se llama, no se crea el objeto DAG y NO aparece
# en la interfaz web.
#
# Internamente, crypto_bronze() NO ejecuta las tareas: solo REGISTRA la
# definicion del DAG (tareas, dependencias, schedule, etc.) en el metadata
# database de Airflow. Las tareas se ejecutan cuando el scheduler determina
# que es momento segun el cron expression definido en schedule.
# =============================================================================
crypto_bronze()
