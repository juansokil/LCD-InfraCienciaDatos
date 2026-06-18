"""
DAG: crypto_silver
Clase 04 - Transformacion Bronze a Silver con calidad y quarantine

Pipeline: bronze.crypto_markets -> Evaluar -> Limpiar -> silver.crypto_markets
                                                       -> silver.quarantine_crypto_markets

Este DAG implementa la Capa Silver de la Arquitectura Medallion.
La idea central es: Bronze tiene datos CRUDOS (tal cual vinieron de la API).
Silver tiene datos LIMPIOS, validados y deduplicados
(la deduplicacion Y la normalizacion se hacen en SQL -- pushdown --
y la validacion semantica con Pydantic generado desde el contrato).

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
import os
import sys

# Hacemos visible el paquete `common` (esta dos niveles arriba en stack/dags/)
# para poder importar el modulo de contratos compartido entre Bronze y Silver.
sys.path.append("/opt/airflow/dags")
from common.contracts import build_pydantic_from_contract, load_contract  # noqa: E402

try:  # Airflow 3.x
    from airflow.sdk import get_current_context
except ImportError:  # fallback Airflow 2.x
    from airflow.operators.python import get_current_context  # noqa: E402


# ============================================================
# CONFIGURACION
# ============================================================
# Misma connection string que el DAG Bronze.
# Apunta al PostgreSQL dentro de Docker.
DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)

# ============================================================
# DATA CONTRACT
# ============================================================
# El contrato `crypto_markets.yaml` define el schema y reglas del dataset.
# Ya lo aplicamos en clase 03 (Bronze) para validar la FORMA del payload
# de la API. Aca en Silver lo aplicamos para validar la SEMANTICA fila por
# fila con Pydantic generado dinamicamente desde el YAML.
#
# Si manana cambia el contrato (ej: agregar `description` como required),
# este DAG NO necesita modificarse. Solo se actualiza el YAML.
CONTRACT_PATH = "/opt/airflow/data/contracts/crypto_markets.yaml"


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


def _target_date() -> str:
    """Fecha 'YYYY-MM-DD' del intervalo que procesa este run.

    Es la pieza que hace el DAG incremental + backfilleable: cada run
    procesa SOLO los snapshots de su dia. Reproceso historico:
        airflow dags backfill crypto_silver -s 2024-01-01 -e 2024-01-31
    """
    return get_current_context()["ds"]


# ============================================================
# DEFINICION DEL DAG
# ============================================================
@dag(
    dag_id="crypto_silver",
    start_date=datetime(2024, 1, 1),

    # @daily: una corrida por dia; cada run procesa los snapshots de SU
    # fecha (data_interval). catchup=False -> no auto-corre la historia;
    # para reprocesar el pasado se usa `airflow dags backfill`.
    schedule="@daily",

    catchup=False,
    tags=["prod", "silver", "crypto"],
    doc_md="""
    ## Crypto Silver - Transformacion y Calidad
    Lee los snapshots del DIA, aplica el contrato de datos y separa
    registros validos (Silver) de invalidos (Quarantine).

    Incremental por dia: cada run procesa los snapshots de su
    fecha (data_interval) y hace DELETE+append de ESE dia.
    Idempotente por dia y reprocesable.

    ### Correr "para atras" (reproceso historico)
    `catchup=False` -> al despausar NO se auto-corre la historia.
    Para reprocesar un rango pasado, desde la CLI de Airflow:

        airflow dags backfill crypto_silver -s 2024-01-01 -e 2024-01-31

    Cada dia se procesa por separado (DELETE del dia + append), asi
    que se puede repetir sin duplicar y sin pisar los demas dias.
    """,
)
def crypto_silver():
    """
    DAG de la Capa Silver. Transforma datos crudos de Bronze en datos
    limpios y validados.

    Concepto clave: IDEMPOTENCIA POR DIA
    Cada run procesa los snapshots de su fecha y hace DELETE
    (de ese dia) + append. Correr 1 o 10 veces el mismo dia da
    el mismo resultado (no duplica) y NO pisa los demas dias,
    lo que permite reprocesar historia con `airflow dags backfill`.
    """

    # ============================================================
    # TAREA 1: LEER BRONZE (fuente de datos)
    # ============================================================
    @task
    def read_bronze():
        """
        Leer los snapshots del DIA que procesa este run.

        INCREMENTAL: filtra bronze.crypto_markets por la fecha del run
        (data_interval / `ds`), no toda la historia. Esto hace el DAG
        backfilleable: `airflow dags backfill crypto_silver -s <ini>
        -e <fin>` reprocesa cada dia por separado.

        Dedup y normalizacion (symbol->UPPER, name->Title, trim,
        ''->NULL) se hacen en SQL -- pushdown: el worker recibe los
        datos ya deduplicados y normalizados (solo la validacion de
        contrato corre en Python, por diseno contract-driven).

        Retorna: lista de dicts del DIA (deduplicados + normalizados).
        """
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        # SQL PUSHDOWN: dedup + normalizacion se hacen en Postgres, no en pandas.
        # Armamos la lista de columnas desde el catalogo para:
        #   - normalizar en SQL (symbol->UPPER, name->Title, trim, ''->NULL)
        #   - NO perder columnas extra (ath, atl, ...) -> evolution-safe
        #     (no se puede `SELECT *, upper(symbol) AS symbol`: columnas duplicadas)
        cols = pd.read_sql(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'bronze' AND table_name = 'crypto_markets'
            ORDER BY ordinal_position
            """,
            engine,
        )
        TEXT_TYPES = {"text", "character varying", "varchar", "character", "char"}
        KEEP_RAW = {"id", "snapshot_ts", "ingested_at"}  # llaves/audit: sin tocar
        select_exprs = []
        for cname, dtype in zip(cols["column_name"], cols["data_type"]):
            q = f'"{cname}"'
            if cname == "symbol":
                select_exprs.append(f"upper(NULLIF(btrim({q}), '')) AS {q}")
            elif cname == "name":
                select_exprs.append(f"initcap(NULLIF(btrim({q}), '')) AS {q}")
            elif dtype in TEXT_TYPES and cname not in KEEP_RAW:
                # trim + blancos -> NULL (normalizacion Silver, set-based)
                select_exprs.append(f"NULLIF(btrim({q}), '') AS {q}")
            else:
                # numericas/timestamp + llaves/audit: tal cual (raw)
                select_exprs.append(q)
        select_list = ",\n                   ".join(select_exprs)

        # Fecha del run: incremental + backfill (solo los snapshots de ese dia).
        ds = _target_date()

        # DISTINCT ON (id, snapshot_ts) + ORDER BY ... ingested_at DESC =
        # "1 fila por (id, snapshot_ts): la de ingested_at mas reciente"
        # (equivalente exacto a drop_duplicates(keep="last") tras ordenar).
        # WHERE snapshot_ts::date = ds -> SOLO el dia que procesa este run.
        query = f"""
            SELECT DISTINCT ON (id, snapshot_ts)
                   {select_list}
            FROM bronze.crypto_markets
            WHERE snapshot_ts::date = '{ds}'
            ORDER BY id, snapshot_ts, ingested_at DESC
        """
        df = pd.read_sql(query, engine)

        snaps = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 0
        print(f"[{ds}] Leidos {len(df)} registros de Bronze "
              f"({snaps} snapshots del dia)")

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
        Deduplicar, normalizar texto, validar contra Data Contract,
        y separar en Silver (validos) y Quarantine (invalidos).

        Hace 4 cosas:

        1. DEDUPLICAR: si hay 2 registros con mismo (id, snapshot_ts),
           se queda con el ultimo por ingested_at.

        2. NORMALIZAR: estandarizar strings (UPPER, Title case, strip).

        3. VALIDAR contra el contrato YAML: Pydantic se construye en
           runtime desde `crypto_markets.yaml` (no hay clase hardcodeada).
           Cambiar el contrato = editar YAML. Sin tocar este DAG.

        4. SEPARAR: los que pasan el contrato van a Silver,
           los que no van a Quarantine con el motivo del rechazo.

        Retorna: diccionario con 2 listas (silver y quarantine).
        """
        import pandas as pd

        # --- 1. CARGAR CONTRATO + CONSTRUIR PYDANTIC EN RUNTIME ---
        # Esta es la diferencia clave vs la version anterior:
        # NO hay `class CryptoContract(BaseModel)` hardcodeado.
        # El modelo se genera dinamicamente desde `crypto_markets.yaml`.
        contract = load_contract(CONTRACT_PATH)
        CryptoContract = build_pydantic_from_contract(contract)
        print(f"Contrato cargado: {contract['dataset']} v{contract['version']}")
        print(f"Modelo Pydantic generado con campos: "
              f"{list(CryptoContract.model_fields.keys())}")

        df = pd.DataFrame(records)

        # --- 2. DEDUPLICACION ---
        # Ya viene deduplicada de SQL (read_bronze: DISTINCT ON) -- pushdown.
        # No repetimos el dedup en pandas: el set-based lo hizo Postgres.

        # --- 3. NORMALIZACION DE STRINGS ---
        # Ya hecha en SQL (read_bronze): symbol->UPPER, name->Title,
        # trim y blancos->NULL -- pushdown. No se repite en pandas.

        # --- 4. VALIDACION fila por fila con Pydantic dinamico ---
        # Solo pasamos a Pydantic las columnas que el contrato declara
        # (sino podriamos tener problemas con `extra fields`).
        # Pero conservamos TODAS las columnas en la fila final (no
        # perdemos info de las columnas extra como ath, atl, etc.).
        contract_field_names = set(CryptoContract.model_fields.keys())
        validos, invalidos = [], []

        for _, row in df.iterrows():
            row_dict = row.to_dict()
            # Subset solo con las columnas declaradas en el contrato
            row_for_validation = {
                k: v for k, v in row_dict.items() if k in contract_field_names
            }
            try:
                # Si Pydantic NO lanza, la fila pasa el contrato.
                CryptoContract(**row_for_validation)
                validos.append(row_dict)
            except Exception as e:
                # Capturamos el motivo del rechazo en la fila
                # para poder analizarlo en quarantine.
                row_dict["quarantine_reason"] = (
                    f"{type(e).__name__}: {str(e)[:300]}"
                )
                invalidos.append(row_dict)

        # --- 5. CONVERTIR A DATAFRAMES + AGREGAR METADATA ---
        df_silver = pd.DataFrame(validos)
        df_quarantine = pd.DataFrame(invalidos)

        now = datetime.now().isoformat()
        for d in [df_silver, df_quarantine]:
            if not d.empty:
                d["_processed_at"] = now
                d["_source_table"] = "bronze.crypto_markets"
                d["_contract_version"] = str(contract.get("version"))

        s, q = len(df_silver), len(df_quarantine)
        print(f"Silver: {s} | Quarantine: {q} | "
              f"Tasa: {s / max(s + q, 1) * 100:.1f}%")

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
        Cargar los validos del DIA en silver.crypto_markets.

        INCREMENTAL e idempotente POR DIA:
          1) DELETE de las filas de ese dia (si la tabla existe)
          2) append de las filas procesadas de ese dia
        Correr el mismo dia N veces no duplica y NO pisa los demas
        dias -> habilita `airflow dags backfill`. Gold sigue leyendo
        silver.crypto_markets completo (Silver acumula todos los dias;
        solo cambia COMO se escribe).
        """
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(split_data["silver"])
        engine = sqlalchemy.create_engine(DB_URI)
        ds = _target_date()

        # Idempotencia POR DIA: schema + DELETE de ese dia (si la tabla existe).
        # to_regclass devuelve NULL si la tabla no existe -> 1ra corrida no
        # borra nada (el append de abajo la crea).
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
            existe = conn.execute(sqlalchemy.text(
                "SELECT to_regclass('silver.crypto_markets')"
            )).scalar()
            if existe:
                conn.execute(sqlalchemy.text(
                    f"DELETE FROM silver.crypto_markets WHERE snapshot_ts::date = '{ds}'"
                ))

        if df.empty:
            print(f"[{ds}] silver.crypto_markets: 0 registros (dia sin validos)")
            return

        # append: agrega SOLO el dia (ya lo borramos arriba -> idempotente por dia)
        df.to_sql("crypto_markets", engine, schema="silver", if_exists="append", index=False)

        snaps = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 0
        print(f"[{ds}] silver.crypto_markets: +{len(df)} registros "
              f"({snaps} snapshots del dia)")

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
        ds = _target_date()

        # Idempotencia POR DIA (igual patron que load_silver).
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
            existe = conn.execute(sqlalchemy.text(
                "SELECT to_regclass('silver.quarantine_crypto_markets')"
            )).scalar()
            if existe:
                conn.execute(sqlalchemy.text(
                    f"DELETE FROM silver.quarantine_crypto_markets WHERE snapshot_ts::date = '{ds}'"
                ))

        if df.empty:
            print(f"[{ds}] silver.quarantine_crypto_markets: 0 registros (dia OK)")
            return

        df.to_sql("quarantine_crypto_markets", engine, schema="silver", if_exists="append", index=False)
        print(f"[{ds}] silver.quarantine_crypto_markets: +{len(df)} registros")

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

    bronze_data = read_bronze()              # Paso 1: Leer Bronze del dia (incremental)
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
