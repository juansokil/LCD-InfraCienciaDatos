"""
DAG: crypto_silver
Clase 04 - Transformacion Bronze a Silver con calidad y quarantine

Pipeline: bronze.crypto_markets -> Evaluar -> Limpiar -> silver.crypto_markets
                                                       -> silver.quarantine_crypto_markets

Este DAG implementa la Capa Silver de la Arquitectura Medallion.
La idea central es: Bronze tiene datos CRUDOS (tal cual vinieron de la API).
Silver tiene datos LIMPIOS, validados y deduplicados.

Los registros que no pasan las validaciones van a "quarantine"
(una tabla aparte) para que un humano los revise. Esto es una
buena practica en Data Engineering: nunca descartar datos, solo separarlos.

Flujo de tareas:
    read_bronze() --> evaluate_quality() --> clean_and_split() --> load_silver()
                                                               --> load_quarantine()
                                                               --> log_summary()
"""

# ============================================================
# IMPORTS
# ============================================================
from airflow.decorators import dag, task
from datetime import datetime
import math


# ============================================================
# CONFIGURACION
# ============================================================
# Misma connection string que el DAG Bronze.
# Apunta al PostgreSQL dentro de Docker.
DB_URI = "postgresql+psycopg2://admin:admin@postgres:5432/InfraCienciaDatos"


# ============================================================
# FUNCION AUXILIAR (a nivel de modulo)
# ============================================================
# Esta funcion esta FUERA del @dag, a nivel de modulo.
# Es una funcion "helper" que se usa en varias tareas.
# A diferencia de las tareas (@task), esta funcion NO se ejecuta
# como un paso independiente de Airflow, sino que es llamada
# desde dentro de las tareas.
def _clean_records(records):
    """
    Limpiar NaN/inf de records para que XCom (JSON) no explote.

    Problema: pandas crea valores NaN (Not a Number) e inf (Infinity)
    cuando hay datos faltantes o divisiones por cero. Estos valores
    son validos en Python/pandas, pero NO son validos en JSON.
    Como Airflow usa JSON para pasar datos entre tareas (XCom),
    necesitamos reemplazarlos por None (que en JSON es null).

    Parametro: lista de diccionarios (cada dict es una fila)
    Retorna: la misma lista pero con NaN/inf reemplazados por None
    """
    for row in records:
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
    return records


# ============================================================
# DEFINICION DEL DAG
# ============================================================
@dag(
    dag_id="crypto_silver",
    start_date=datetime(2024, 1, 1),

    # schedule=None significa que este DAG NO se ejecuta automaticamente.
    # Solo se ejecuta cuando alguien lo "triggerea" manualmente desde
    # la UI de Airflow (boton "Play") o desde la CLI.
    # Esto tiene sentido para Silver porque queremos control sobre
    # cuando se procesan los datos (a diferencia de Bronze que corre
    # cada 5 minutos automaticamente).
    schedule=None,

    catchup=False,
    tags=["silver", "crypto"],
    doc_md="""
    ## Crypto Silver - Transformacion y Calidad
    Lee TODOS los datos acumulados de Bronze, aplica contrato de datos,
    separa registros validos (Silver) de invalidos (Quarantine).

    Idempotente: reconstruye Silver completo en cada corrida
    (replace) a partir de todo Bronze.
    """,
)
def crypto_silver():
    """
    DAG de la Capa Silver. Transforma datos crudos de Bronze en datos
    limpios y validados.

    Concepto clave: IDEMPOTENCIA
    Este DAG es "idempotente", lo que significa que si lo corres
    1 vez o 10 veces, el resultado es el mismo. Esto es porque
    usa if_exists="replace" (borra y recrea Silver desde cero
    a partir de todo Bronze). En produccion esto es muy importante
    porque permite re-ejecutar sin miedo a duplicar datos.
    """

    # ============================================================
    # TAREA 1: LEER BRONZE (fuente de datos)
    # ============================================================
    @task
    def read_bronze():
        """
        Leer todos los datos acumulados de bronze.crypto_markets.

        Notar que leemos TODOS los datos de Bronze, no solo los nuevos.
        Esto es parte del patron "full refresh": Silver se reconstruye
        completo en cada corrida. Es mas simple y seguro que intentar
        procesar solo los deltas (datos nuevos).

        Retorna: lista de diccionarios con todos los registros de Bronze.
        """
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        # Leer toda la tabla bronze.crypto_markets
        # pd.read_sql() ejecuta la query y devuelve un DataFrame
        df = pd.read_sql("SELECT * FROM bronze.crypto_markets", engine)

        # Contar snapshots unicos para el log
        # .nunique() cuenta valores unicos en una columna
        dias = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 1
        print(f"Leidos {len(df)} registros de Bronze ({dias} snapshots)")

        # Convertir a lista de dicts y limpiar NaN para XCom
        return _clean_records(df.to_dict(orient="records"))

    # ============================================================
    # TAREA 2: EVALUAR CALIDAD (diagnostico)
    # ============================================================
    @task
    def evaluate_quality(records: list):
        """
        Evaluar calidad de los datos: completitud, duplicados, rangos.

        Esta tarea NO modifica los datos, solo los analiza y reporta.
        Es como un "chequeo medico" de los datos antes de procesarlos.

        Metricas que evalua:
        - Completitud: % de celdas que NO son null (100% = perfecto)
        - Duplicados: registros repetidos por (id, snapshot_ts)

        Segun el score de calidad, emite una decision:
        - >= 95%: PROCESS_TO_SILVER (todo bien, procesar normalmente)
        - >= 85%: PROCESS_WITH_WARNING (procesar pero alertar)
        - < 85%:  HALT_AND_ALERT (parar y notificar al equipo)

        En esta version siempre procesamos (no frena el pipeline),
        pero en produccion se podria agregar un BranchOperator que
        detenga el flujo si la calidad es muy baja.
        """
        import pandas as pd

        df = pd.DataFrame(records)

        # Calcular completitud por columna:
        # isnull().sum() cuenta nulls por columna
        # dividido len(df) da la proporcion de nulls
        # 1 - eso da la proporcion de NO nulls (completitud)
        # * 100 para tener porcentaje
        completitud = (1 - df.isnull().sum() / len(df)) * 100

        # Contar duplicados: registros con misma combinacion (id, snapshot_ts)
        # En Bronze puede haber duplicados si el DAG corrio mas de una vez
        # para el mismo snapshot. Esto es normal, se limpia en Silver.
        duplicados = (
            df.duplicated(subset=["id", "snapshot_ts"]).sum()
            if "snapshot_ts" in df.columns
            else df.duplicated(subset=["id"]).sum()
        )

        # Score general: promedio de completitud de todas las columnas
        quality_score = completitud.mean()

        print("=== Reporte de Calidad ===")
        print(f"Completitud promedio: {quality_score:.1f}%")
        print(f"Duplicados: {duplicados}")

        # Decision basada en el score
        if quality_score >= 95:
            print(f"-> PROCESS_TO_SILVER")
        elif quality_score >= 85:
            print(f"-> PROCESS_WITH_WARNING")
        else:
            print(f"-> HALT_AND_ALERT")

        # Pasamos los datos sin modificar a la siguiente tarea
        return records

    # ============================================================
    # TAREA 3: LIMPIAR Y SEPARAR (transformacion principal)
    # ============================================================
    @task
    def clean_and_split(records: list):
        """
        Deduplicar, normalizar texto, validar contrato de datos,
        y separar en Silver (validos) y Quarantine (invalidos).

        Esta es la tarea mas importante del DAG Silver. Hace 4 cosas:

        1. DEDUPLICAR: si hay 2 registros con mismo (id, snapshot_ts),
           se queda con el ultimo por ingested_at.

        2. NORMALIZAR: estandarizar strings (UPPER, Title case, strip).

        3. VALIDAR: aplicar un "contrato de datos" - reglas que definen
           que es un registro valido. Por ejemplo: precio >= 0, id no nulo.

        4. SEPARAR: los que pasan el contrato van a Silver,
           los que no van a Quarantine.

        Retorna: diccionario con 2 listas (silver y quarantine).
        """
        import pandas as pd

        df = pd.DataFrame(records)

        # --- 1. DEDUPLICACION ---
        # sort_values por ingested_at: pone los mas recientes al final
        # drop_duplicates con keep="last": si hay duplicados por (id, snapshot_ts),
        # se queda con el ultimo (el mas reciente)
        dedup_cols = ["id", "snapshot_ts"] if "snapshot_ts" in df.columns else ["id"]
        df = df.sort_values("ingested_at").drop_duplicates(subset=dedup_cols, keep="last")

        # --- 2. NORMALIZACION DE STRINGS ---
        # .str.strip(): elimina espacios al inicio y final ("  btc  " -> "btc")
        # .str.upper(): convierte a mayusculas ("btc" -> "BTC")
        # .str.title(): primera letra mayuscula ("bitcoin" -> "Bitcoin")
        df["symbol"] = df["symbol"].str.strip().str.upper()
        df["name"] = df["name"].str.strip().str.title()

        # --- 3. VALIDACION (Contrato de Datos) ---
        # Definimos reglas que DEBE cumplir un registro para ser valido.
        # Cada condicion retorna True/False por fila.
        # El & (AND) requiere que TODAS las condiciones sean True.
        #
        # Reglas:
        #   - id no puede ser nulo (necesitamos identificar la cripto)
        #   - symbol no puede ser nulo (necesitamos el ticker)
        #   - name no puede ser nulo (necesitamos el nombre)
        #   - current_price no puede ser nulo (dato fundamental)
        #   - current_price >= 0 (un precio negativo no tiene sentido)
        #   - market_cap_rank no puede ser nulo (necesitamos el ranking)
        df["_is_valid"] = (
            df["id"].notna()
            & df["symbol"].notna()
            & df["name"].notna()
            & df["current_price"].notna()
            & (df["current_price"] >= 0)
            & df["market_cap_rank"].notna()
        )

        # --- 4. SEPARAR Silver vs Quarantine ---
        # df[condicion] filtra las filas que cumplen la condicion
        # .drop(columns=["_is_valid"]) elimina la columna auxiliar
        # .copy() crea una copia independiente
        df_silver = df[df["_is_valid"]].drop(columns=["_is_valid"]).copy()
        df_quarantine = df[~df["_is_valid"]].drop(columns=["_is_valid"]).copy()

        # Agregar metadata de procesamiento a ambas tablas:
        # - _processed_at: cuando se proceso este registro
        # - _source_table: de donde vino (trazabilidad/lineage)
        now = datetime.now().isoformat()
        for d in [df_silver, df_quarantine]:
            d["_processed_at"] = now
            d["_source_table"] = "bronze.crypto_markets"

        s, q = len(df_silver), len(df_quarantine)
        print(f"Silver: {s} | Quarantine: {q} | Tasa: {s / max(s + q, 1) * 100:.1f}%")

        # Retornamos un diccionario con ambas listas.
        # XCom puede transportar dicts, listas, strings, numeros, etc.
        # Las tareas siguientes reciben este dict y acceden a
        # split_data["silver"] o split_data["quarantine"].
        return {
            "silver": _clean_records(df_silver.to_dict(orient="records")),
            "quarantine": _clean_records(df_quarantine.to_dict(orient="records")),
        }

    # ============================================================
    # TAREA 4: CARGAR SILVER (datos validos)
    # ============================================================
    @task
    def load_silver(split_data: dict):
        """
        Cargar registros validos en silver.crypto_markets.

        Usa if_exists="replace" (NO append como Bronze).
        Esto significa que BORRA la tabla Silver y la recrea desde cero.

        ¿Por que replace y no append?
        Porque Silver se reconstruye completo desde Bronze en cada corrida.
        Si usaramos append, tendriamos duplicados cada vez que corremos el DAG.
        Con replace, siempre tenemos un Silver limpio y consistente.

        Este patron se llama "full refresh" y es muy comun en capas
        de transformacion (Silver, Gold).
        """
        import pandas as pd
        import sqlalchemy

        # Extraer solo los registros "silver" del diccionario
        df = pd.DataFrame(split_data["silver"])
        engine = sqlalchemy.create_engine(DB_URI)

        # replace: borra la tabla y la recrea con los datos nuevos
        df.to_sql("crypto_markets", engine, schema="silver", if_exists="replace", index=False)

        dias = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 1
        print(f"silver.crypto_markets: {len(df)} registros ({dias} snapshots)")

    # ============================================================
    # TAREA 5: CARGAR QUARANTINE (datos invalidos)
    # ============================================================
    @task
    def load_quarantine(split_data: dict):
        """
        Cargar registros invalidos en silver.quarantine_crypto_markets.

        Los registros en quarantine no se descartan, se guardan en una
        tabla separada. Esto permite:
        1. Analizar POR QUE fallaron (debugging)
        2. Recuperarlos si el contrato de datos era demasiado estricto
        3. Auditar la calidad de la fuente de datos

        En produccion, un data engineer revisaria periodicamente la tabla
        de quarantine para detectar problemas sistematicos.
        """
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(split_data["quarantine"])
        engine = sqlalchemy.create_engine(DB_URI)
        df.to_sql("quarantine_crypto_markets", engine, schema="silver", if_exists="replace", index=False)
        print(f"silver.quarantine_crypto_markets: {len(df)} registros")

    # ============================================================
    # TAREA 6: LOG RESUMEN (reporte final)
    # ============================================================
    @task
    def log_summary(split_data: dict):
        """
        Imprimir resumen final del pipeline Silver.

        Esta tarea no modifica datos ni escribe en la DB.
        Solo imprime un resumen en los logs de Airflow para
        que el equipo pueda verificar de un vistazo si todo salio bien.

        La "tasa de exito" es el % de registros que pasaron a Silver
        (vs los que fueron a Quarantine). Un 100% es ideal.
        """
        s = len(split_data["silver"])
        q = len(split_data["quarantine"])
        total = s + q
        tasa = s / max(total, 1) * 100
        print("=== Resumen Pipeline Silver ===")
        print(f"Silver: {s} | Quarantine: {q} | Tasa de exito: {tasa:.1f}%")

    # ============================================================
    # DEFINICION DEL FLUJO
    # ============================================================
    # El flujo de Silver es mas complejo que Bronze porque tiene
    # tareas que se ejecutan en PARALELO:
    #
    # read_bronze -> evaluate_quality -> clean_and_split -> load_silver ----\
    #                                                   -> load_quarantine ---> log_summary
    #
    # load_silver y load_quarantine se ejecutan AL MISMO TIEMPO (en paralelo)
    # porque no dependen una de la otra. Ambas leen de split_data.
    #
    # El operador >> (bitshift) define dependencias:
    #   [load_s, load_q] >> log_summary(split)
    # Significa: "log_summary solo se ejecuta cuando AMBAS cargas terminan"

    bronze_data = read_bronze()              # Paso 1: Leer todo Bronze
    evaluated = evaluate_quality(bronze_data) # Paso 2: Evaluar calidad
    split = clean_and_split(evaluated)        # Paso 3: Limpiar y separar
    load_s = load_silver(split)               # Paso 4a: Cargar Silver (paralelo)
    load_q = load_quarantine(split)           # Paso 4b: Cargar Quarantine (paralelo)
    [load_s, load_q] >> log_summary(split)    # Paso 5: Resumen (espera a 4a y 4b)


# ============================================================
# INSTANCIACION DEL DAG
# ============================================================
# Igual que en Bronze: esta linea es obligatoria para que
# Airflow descubra y registre el DAG.
crypto_silver()
