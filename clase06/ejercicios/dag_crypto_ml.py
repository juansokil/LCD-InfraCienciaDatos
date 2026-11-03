"""
DAG: crypto_ml
Clase 06 - La ABT + scoring (inferencia batch) con el @champion del Registry

Pipeline (dos ramas que no se cruzan):
  silver.crypto_markets + bronze.global_market  ->  gold.gold_abt_crypto  (la ABT)
  silver.crypto_markets + MLflow Registry       ->  gold.predicciones     (scoring)

Es la rama de ML del pipeline productivo (SERVING): se dispara POR DATO
(asset SILVER_CRYPTO), no por reloj, en paralelo a crypto_gold.

    crypto_bronze  cron 0,15,30,45          --emite--> BRONZE_CRYPTO
    crypto_silver  schedule=[BRONZE_CRYPTO] --emite--> SILVER_CRYPTO
    crypto_gold    schedule=[SILVER_CRYPTO] --emite--> GOLD_STAR   (BI)
    crypto_ml      schedule=[SILVER_CRYPTO] --emite--> GOLD_ABT    (ML)  <-- este DAG

Espera SILVER_CRYPTO porque es el dato que lee: los snapshots limpios de
Silver. Gold arma con ellos el star para BI; este DAG arma con ellos lo suyo
para ML. Son dos formas de Gold que salen de la misma fuente, y ninguna
depende de la otra: si el star de BI falla, el modelo sigue prediciendo.
Un asset dice "el dato que vas a leer esta listo".

A su vez emite GOLD_ABT en la task que escribe la ABT. Hoy nadie lo consume
aguas abajo: lo declara igual, porque el asset documenta que ese dato existe y
porque manana puede colgarse otro DAG ahi sin tocar este.

=============================================================================
DEPLOY
=============================================================================
Este archivo vive en clase06/ejercicios/ como material de la clase. Para
activarlo se copia a los DAGs del stack (el scheduler lo descubre solo, y
nace despausado: is_paused_upon_creation=False, modo produccion):

    cp clase06/ejercicios/dag_crypto_ml.py stack/dags/04-ml/

=============================================================================
ESTE DAG NO ELIGE EL CHAMPION, NI ENTRENA
=============================================================================
El entrenamiento y la ELECCION del champion se hacen en el notebook de
clase06 (seccion 3.3): el modelo nuevo entra como @challenger y pasa a
@champion solo si le gana al vigente, con una regla escrita antes de mirar.

Este DAG solo carga el champion y predice. Todo lo que muestra el tablero
lo predijo un champion: no hay historia armada despues con otro modelo.

Este DAG toma el champion VIGENTE por alias
(`models:/crypto_volatilidad_7d@champion`): cuando se promueve otra version
a @champion, la corrida siguiente la usa sola, sin tocar codigo.

=============================================================================
MLFLOW: EL SERVER DEL STACK
=============================================================================
El stack YA trae un MLflow Tracking Server (servicio `mlflow` del
docker-compose: backend Postgres + artifacts en volumen). Desde adentro de
la red Docker se llega por el NOMBRE DEL SERVICIO:

    http://mlflow:5000        (el mismo que desde tu maquina es localhost:5000)

La URI se lee de la env var MLFLOW_TRACKING_URI; si no esta seteada se usa
ese default. mlflow y scikit-learn ya estan en la imagen de Airflow
(stack/requirements.txt pinea mlflow==3.4.0, igual que el server).

=============================================================================
DISENO ANTI-ROJO (serving que arranca antes que el modelo)
=============================================================================
- Sin champion en el Registry (todavia no corriste la seccion 3.3 del
  notebook) -> el DAG SALTEA con un log claro, NO falla.
- Features incompletas (las ventanas de 7 dias siguen "calentando" porque
  el pipeline tiene pocos dias de historia) -> tambien saltea con log claro.
- Ya esta la prediccion del ultimo dia cerrado con este champion -> saltea:
  el modelo predice una vez por dia, no en cada corrida. Esta es la UNICA
  salteada que se pinta distinto: la task queda en ROSA (skipped) en Airflow,
  y las dos de abajo tambien. Asi la grilla muestra de un vistazo que corrida
  predijo (verde) y cuales se despertaron, vieron que ya estaba y no hicieron
  nada (rosa). Las otras salteadas quedan en verde a proposito: en un stack
  nuevo, las tasks de abajo tienen que correr igual para crear la tabla y las
  vistas.
- MLflow server caido o Postgres caido -> eso SI es falla real: el task
  falla y se ve en rojo (con retries por si fue un parpadeo).

Salida: gold.predicciones, IDEMPOTENTE por dia de features
(CREATE TABLE IF NOT EXISTS + DELETE del dia + INSERT): re-correr el DAG
el mismo dia reescribe ese dia, nunca duplica.
"""

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from datetime import datetime, timedelta, timezone
import os
import sys

# El asset se importa desde common/ (definido una sola vez, igual que el resto
# de la cadena: si cada DAG construyera su propio Asset(...), un typo lo rompe
# en silencio):
# productor y consumidor tienen que referirse al MISMO Asset, definido UNA vez.
sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_ABT, SILVER_CRYPTO  # noqa: E402

# --- Conexion a Postgres (mismo patron que bronze/silver/gold) ---
DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)

# --- MLflow / modelo (coincide con la seccion 3 del notebook de clase06) ---
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
# El Registry tiene UN modelo: crypto_volatilidad_7d, el de la ventana mas
# larga. La grilla del notebook compara las tres ventanas como runs (en
# Experiments); al Registry entra solo lo que puede ir a produccion, y que
# version va se decide moviendo el alias (seccion 3.3 del notebook).
#
# Si manana se quiere servir otra ventana, se cambia esta constante (o se
# parametriza con una Variable de Airflow). La ventana con la que entrenar
# las features NO se hardcodea: sale del propio modelo, leyendo su param
# `ventana_dias` -- eso es lo que evita el training-serving skew.
MODEL_NAME = "crypto_volatilidad_7d"   # el de la ventana mas larga
MODEL_ALIAS = "champion"

# MISMA definicion de features que el notebook: la query vive UNA sola vez
# por lado (notebook para entrenar, aca para scorear) y es IDENTICA
# -> cero training-serving skew.
#
# La VENTANA no se hardcodea: se lee del propio champion (param `ventana_dias`
# que loguea el notebook). Si manana se promueve un modelo entrenado con otra
# ventana, este DAG lo sigue solo. Hardcodear un 7 aca seria justamente la
# forma mas comun de training-serving skew: el modelo espera unas features y
# produccion le manda otras.
VENTANA_DEFAULT = 7

def features_sql(W: int) -> str:
    """Dataset diario para predecir QUE CRIPTOS VAN A SER LAS MOVIDAS MANANA.

    POR QUE VOLATILIDAD Y NO DIRECCION
    La direccion del precio no esta en los datos publicos de precio y volumen: se
    probo con tres ventanas y un target balanceado, y el modelo quedo siempre
    alrededor del azar. No es culpa del algoritmo -- la pregunta no tiene
    respuesta ahi.

    La volatilidad si: SE AGRUPA EN EL TIEMPO. Un dia movido sigue a otro movido.
    Es de los hechos mas establecidos en finanzas (Mandelbrot lo describio en
    1963; es la base de toda la familia GARCH). Medido sobre los datos del curso,
    la correlacion dia a dia da +0,447 para la volatilidad contra practicamente
    nada para la direccion.

    DE DONDE SALE EL DATO
    De los snapshots por cripto que `silver.crypto_markets` acumula (uno cada 15
    minutos, hasta 96 por dia si el stack queda prendido todo el dia) y que el
    cierre diario tira. Se lee Silver y no el hecho de Gold: el star es la forma
    que Gold les da a esos snapshots para BI, y el modelo arma la suya.

    EL TARGET ES CROSS-SECTIONAL
    `vol_manana > mediana de la volatilidad de manana`. La mitad le gana por
    definicion, asi que queda balanceado mitad y mitad SIEMPRE y el baseline se
    queda clavado en la mitad. Con un target absoluto ("mas volatil que hoy") el
    baseline se movia segun el humor del dia y dejaba de ser comparable.
    """
    if W > 1:
        bloque = f"""
        -- Resumen de los ultimos {W} dias
        AVG(vol)   OVER w_win                                     AS vol_{W}d,
        AVG(rango) OVER w_win                                     AS rango_{W}d,
        volumen / NULLIF(AVG(volumen) OVER w_win, 0)              AS vol_rel_{W}d,
        -- cuanto se despega la volatilidad de hoy de su propio promedio
        vol / NULLIF(AVG(vol) OVER w_win, 0)                      AS vol_vs_media_{W},"""
        decl = f""",
           w_win  AS (PARTITION BY crypto_id ORDER BY fecha
                      ROWS BETWEEN {W - 1} PRECEDING AND CURRENT ROW)"""
    else:
        bloque, decl = "", ""

    return f"""
WITH intra AS (
    -- Una fila por cripto y por dia, calculada con TODOS los snapshots del dia.
    -- El HAVING descarta dias con pocas mediciones: una volatilidad calculada
    -- con 3 puntos no es una volatilidad, es ruido.
    -- snapshot_ts llega como texto desde Bronze: se tipa aca para sacar el dia.
    SELECT id                                                         AS crypto_id,
           max(symbol)                                                AS symbol,
           snapshot_ts::timestamp::date                               AS fecha,
           stddev_samp(current_price) / NULLIF(avg(current_price), 0) * 100 AS vol,
           (max(current_price) - min(current_price))
               / NULLIF(avg(current_price), 0) * 100                  AS rango,
           avg(total_volume)                                          AS volumen,
           count(*)                                                   AS n_snaps,
           max(market_cap_rank)                                       AS market_cap_rank
    FROM silver.crypto_markets
    -- Un dia cuenta cuando ya esta su ultimo snapshot (el de las 23:45 UTC,
    -- 20:45 en Argentina, por el cron de Bronze) o cuando ya termino. Antes,
    -- su volatilidad todavia cambia con cada snapshot nuevo.
    WHERE snapshot_ts::timestamp::date < current_date
       OR EXISTS (SELECT 1 FROM silver.crypto_markets
                  WHERE snapshot_ts::timestamp = current_date + time '23:45')
    GROUP BY id, snapshot_ts::timestamp::date
    HAVING count(*) > 20
),
mediana AS (
    -- La vara del dia: la volatilidad tipica del mercado.
    SELECT fecha, percentile_cont(0.5) WITHIN GROUP (ORDER BY vol) AS med
    FROM intra GROUP BY fecha
),
serie AS (
    SELECT i.*, m.med AS mediana_vol_del_dia
    FROM intra i
    JOIN mediana m ON m.fecha = i.fecha
),
features AS (
    SELECT
        crypto_id, symbol, fecha,
        -- FEATURES: solo informacion disponible al cierre del dia t
        vol, rango, volumen, n_snaps, market_cap_rank,
        LAG(vol)   OVER w_hist                                    AS vol_ayer,
        LAG(rango) OVER w_hist                                    AS rango_ayer,{bloque}
        -- TARGET: manana, ¿esta cripto va a estar entre las mas movidas?
        -- Se compara contra la mediana de MANANA, no contra la de hoy: la
        -- pregunta es quien se mueve mas que el resto en ese momento.
        -- Solo si la fila siguiente ES manana: si falta ese dia (stack apagado,
        -- o la cripto no aparecio), la fila queda sin respuesta.
        CASE WHEN LEAD(fecha) OVER w_hist = fecha + 1
             THEN (LEAD(vol) OVER w_hist > LEAD(mediana_vol_del_dia) OVER w_hist)::int
        END                                                       AS target_alta_vol
    FROM serie
    WINDOW w_hist AS (PARTITION BY crypto_id ORDER BY fecha){decl}
)
SELECT * FROM features ORDER BY fecha, crypto_id
"""


def columnas_features(W: int) -> list:
    """Las features de esa ventana, en orden estable."""
    base = ["vol", "rango", "volumen", "n_snaps", "market_cap_rank",
            "vol_ayer", "rango_ayer"]
    if W > 1:
        base += [f"vol_{W}d", f"rango_{W}d", f"vol_rel_{W}d", f"vol_vs_media_{W}"]
    return base


# =============================================================================
# HELPERS DE DDL (los usa build_abt, abajo)
# =============================================================================
# Vienen del DAG de Gold: la ABT se construye con el mismo patron de CTAS en
# SQL. Van copiados y no en `common/` a proposito: cada DAG productivo del
# curso es autocontenido, y `common/` guarda solo lo que DOS DAGs tienen que
# compartir por fuerza (los assets, el contrato).

def _run_ddl(sql: str):
    """Ejecutar SQL DDL/CTAS en Postgres dentro de una transaccion.

    Asegura el schema `gold` (idempotente, igual que Silver) y corre el
    bloque SQL. `engine.begin()` hace commit al salir / rollback si falla.
    """
    import sqlalchemy

    engine = sqlalchemy.create_engine(DB_URI)
    with engine.begin() as conn:
        # exec_driver_sql manda el SQL CRUDO a psycopg2 (sin parsear `text()`):
        #   - psycopg2 ejecuta varios statements separados por `;` en una llamada
        #     -> NO hace falta splitear por `;` (un split ingenuo rompia cuando
        #        un `;` aparece dentro de un comentario `--` o de un string).
        #   - evita que `text()` interprete `:` (cast `::`) o `%` como binds.
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS gold")
        conn.exec_driver_sql(sql)


def _tabla_existe(nombre_calificado: str) -> bool:
    """True si la tabla existe (to_regclass devuelve NULL si no)."""
    import sqlalchemy

    engine = sqlalchemy.create_engine(DB_URI)
    with engine.connect() as conn:
        r = conn.execute(
            sqlalchemy.text("SELECT to_regclass(:t)"), {"t": nombre_calificado}
        ).scalar()
    return r is not None


@dag(
    dag_id="crypto_ml",
    start_date=datetime(2024, 1, 1),
    # DATA-AWARE: corre cuando `crypto_silver` termina de escribir y emite
    # SILVER_CRYPTO -- el dato que este DAG lee. Arranca junto con crypto_gold:
    # los dos consumen Silver y ninguno espera al otro.
    # Sin cron: el scoring no tiene sentido "a las y cinco", tiene sentido
    # cuando hay datos nuevos para scorear.
    schedule=[SILVER_CRYPTO],
    catchup=False,
    is_paused_upon_creation=False,  # modo produccion: nace prendido
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["prod", "ml", "serving", "crypto"],
    doc_md="""
    ## crypto_ml - Scoring con el @champion (serving)

    Consume el asset **`silver_crypto_markets`**, en paralelo a `crypto_gold`:
    cuando Silver termina de escribir, este DAG arma la **ABT** y, en
    paralelo, carga `models:/crypto_volatilidad_7d@champion` del MLflow del stack
    (`http://mlflow:5000`), reconstruye las features del ultimo dia cerrado con
    la MISMA query SQL del notebook (sobre `silver.crypto_markets`) y escribe
    **`gold.predicciones`** (idempotente por dia). Predice una vez por dia: con
    la corrida que trae el ultimo snapshot del dia (23:45 UTC); las demas saltean.

    **No entrena.** Si no hay champion o falta historia, saltea con un log
    claro (no falla). Ver el header del archivo.
    """,
)
def crypto_ml():

    # ============================================================
    # LA ABT: la tabla de features de este pipeline
    # ============================================================
    # Vivia en crypto_gold y se mudo aca, al DAG que la usa: la ABT es la
    # forma que Gold le da a los datos PARA ML, y quien la define es el
    # pipeline de ML. Una tabla, un dueno.
    #
    # No lee nada de Gold: se arma desde silver.crypto_markets y
    # bronze.global_market. Corre en paralelo al scoring porque no hay
    # dependencia de datos entre las dos ramas (el modelo necesita los
    # snapshots de Silver, que la ABT ya colapso).
    # ABT (Analytical Base Table) - wide table para ML
    # ============================================================
    # 1 fila por cripta. Construida con CTEs en SQL:
    #   latest   = DISTINCT ON (id) -> features directas (ultimo snapshot)
    #   temporal = GROUP BY id      -> avg/std/count (features temporales)
    #   glob     = ultimo bronze.global_market (contexto macro)
    # pd.cut() -> CASE WHEN (mismos bins/labels). market_dominance =
    # window SUM() OVER (). stddev_samp = std muestral (== pandas .std()).
    # El contexto global es OPCIONAL: si no existe bronze.global_market se
    # construye la ABT sin esas columnas (LEFT JOIN ON true con la fila
    # global, o se omite el bloque).
    @task(outlets=[GOLD_ABT])
    def build_abt():
        """gold.gold_abt_crypto via SQL (CTEs + window + CASE)."""
        tiene_global = _tabla_existe("bronze.global_market")

        glob_cte = """,
            glob AS (
                SELECT total_market_cap_usd,
                       btc_dominance,
                       market_cap_change_pct_24h
                FROM bronze.global_market
                ORDER BY snapshot_ts DESC, ingested_at DESC
                LIMIT 1
            )""" if tiene_global else ""

        glob_select = """,
                g.total_market_cap_usd        AS global_total_market_cap,
                g.btc_dominance               AS global_btc_dominance,
                g.market_cap_change_pct_24h   AS global_market_change_24h,
                round((b.market_cap
                       / NULLIF(g.total_market_cap_usd, 0) * 100)::numeric, 6)
                                              AS real_market_share""" if tiene_global else ""

        glob_join = "LEFT JOIN glob g ON true" if tiene_global else ""

        _run_ddl(f"""
            DROP TABLE IF EXISTS gold.gold_abt_crypto CASCADE;
            CREATE TABLE gold.gold_abt_crypto AS
            WITH enr AS (
                -- Metricas DERIVADAS en SQL (Silver no las trae): se calculan
                -- una vez aca y las leen latest/temporal.
                SELECT
                    id, snapshot_ts, ingested_at,
                    current_price, market_cap, total_volume,
                    price_change_percentage_24h, market_cap_rank,
                    high_24h, low_24h, circulating_supply,
                    (high_24h - low_24h)                                 AS spread_24h,
                    (high_24h - low_24h) / NULLIF(current_price, 0) * 100 AS spread_pct,
                    circulating_supply / NULLIF(total_supply, 0)          AS supply_ratio,
                    -- ::numeric: sin el cast es division entera (ver build_fact).
                    market_cap::numeric
                        / NULLIF(fully_diluted_valuation, 0)             AS fdv_ratio,
                    ath_change_percentage                                 AS ath_distance_pct,
                    atl_change_percentage                                 AS atl_distance_pct
                FROM silver.crypto_markets
            ),
            latest AS (
                SELECT DISTINCT ON (id)
                    id, current_price, market_cap, total_volume,
                    price_change_percentage_24h, market_cap_rank,
                    high_24h, low_24h, spread_24h, spread_pct,
                    circulating_supply, supply_ratio,
                    ath_distance_pct, atl_distance_pct, fdv_ratio
                FROM enr
                ORDER BY id, snapshot_ts DESC, ingested_at DESC
            ),
            temporal AS (
                SELECT
                    id,
                    avg(current_price)                      AS avg_price,
                    coalesce(stddev_samp(current_price), 0) AS price_std,
                    avg(spread_pct)                         AS avg_spread_pct,
                    count(*)                                AS n_snapshots
                FROM enr
                GROUP BY id
            ),
            base AS (
                SELECT l.*,
                       t.avg_price, t.price_std,
                       t.avg_spread_pct, t.n_snapshots
                FROM latest l
                JOIN temporal t USING (id)
            ){glob_cte}
            SELECT
                b.id,
                b.current_price, b.market_cap, b.total_volume,
                b.price_change_percentage_24h, b.market_cap_rank,
                b.high_24h, b.low_24h, b.spread_24h, b.spread_pct,
                b.circulating_supply, b.supply_ratio,
                b.ath_distance_pct, b.atl_distance_pct, b.fdv_ratio,
                b.avg_price, b.price_std, b.avg_spread_pct, b.n_snapshots,
                b.current_price / NULLIF(b.total_volume, 0)
                                                      AS price_to_volume_ratio,
                round((b.market_cap
                       / NULLIF(SUM(b.market_cap) OVER (), 0) * 100)::numeric, 4)
                                                      AS market_dominance,
                CASE WHEN abs(b.price_change_percentage_24h) < 2 THEN 'baja'
                     WHEN abs(b.price_change_percentage_24h) < 5 THEN 'media'
                     ELSE 'alta' END                  AS volatility_category,
                CASE WHEN b.market_cap_rank <= 10 THEN 'top_10'
                     WHEN b.market_cap_rank <= 25 THEN 'top_25'
                     ELSE 'rest' END                  AS market_cap_tier,
                CASE WHEN b.current_price < 1     THEN 'micro'
                     WHEN b.current_price < 100   THEN 'small'
                     WHEN b.current_price < 10000 THEN 'medium'
                     ELSE 'large' END                 AS price_tier{glob_select},
                now()  AS _processed_at,
                'silver.crypto_markets{' + bronze.global_market' if tiene_global else ''}'
                       AS _source_table
            FROM base b
            {glob_join}
        """)
        print(f"gold.gold_abt_crypto reconstruida (global={'si' if tiene_global else 'no'})")


    # multiple_outputs=False EXPLICITO, y no es cosmetica.
    # TaskFlow INFIERE multiple_outputs=True cuando la funcion esta anotada
    # `-> dict`: en vez de empujar un XCom con el dict entero, empuja UNO POR
    # CLAVE. Y este dict trae `fecha: None` en los caminos de skip -> Airflow 3
    # manda un body vacio al api-server y la task muere con
    # `422 Field required, input: None`, DESPUES de haber impreso el [SKIP].
    # O sea: el camino "saltear elegantemente" era el unico que fallaba, que es
    # justo el que ves hasta que promovas un champion.
    @task(multiple_outputs=False)
    def score_con_champion() -> dict:
        """Carga el champion (si existe) y scorea el ultimo dia de features."""
        import mlflow
        import mlflow.sklearn
        import pandas as pd
        import sqlalchemy
        from mlflow.exceptions import RestException
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

        # --- 1) ¿Hay champion? Si no, saltear con log claro (NO fallar). ---
        # RestException = el server respondio "eso no existe" (modelo o alias).
        # Otra excepcion (server caido, red) NO se atrapa: eso es falla real.
        try:
            mv = MlflowClient().get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
        except RestException as e:
            print(f"[SKIP] Todavia no hay '{MODEL_NAME}@{MODEL_ALIAS}' en el "
                  f"Registry de {MLFLOW_TRACKING_URI}.")
            print("       Corre la seccion 3.3 del notebook de clase06 para "
                  "promover un champion. Este DAG lo va a tomar solo.")
            print(f"       (respuesta del server: {e.error_code})")
            return {"status": "sin_champion", "fecha": None, "rows": []}

        champion_version = str(mv.version)

        # Con QUE ventana se entreno este champion. Se pregunta, no se asume:
        # el run guarda `ventana_dias` y es la unica fuente de verdad sobre
        # que features espera el modelo.
        try:
            params = MlflowClient().get_run(mv.run_id).data.params
            ventana = int(params.get("ventana_dias", VENTANA_DEFAULT))
        except Exception:
            ventana = VENTANA_DEFAULT
        features = columnas_features(ventana)
        print(f"Champion v{champion_version} entrenado con ventana de "
              f"{ventana} dia(s) -> {len(features)} features")

        # --- 2) Las features del ULTIMO DIA CERRADO ---
        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql(features_sql(ventana), engine, parse_dates=["fecha"])
        if df.empty:
            print("[SKIP] silver.crypto_markets sin dias cerrados: el pipeline "
                  "todavia no poblo Silver. Nada que scorear.")
            return {"status": "sin_datos", "fecha": None, "rows": []}
        ultima_fecha = df["fecha"].max()

        # --- 3) Una vez por dia --------------------------------------------
        # La prediccion sale con la corrida que trae el ultimo snapshot del dia
        # (23:45 UTC, las 20:45 en Argentina). Las demas corridas la encuentran
        # y no la repiten. Si se promovio otro champion, la
        # version cambia y se vuelve a predecir con el nuevo.
        #
        # Cuando ya esta, la task se marca SKIPPED (rosa en Airflow) en vez de
        # terminar en verde. Las dos tasks de abajo tambien quedan en rosa:
        # no hay nada que escribir, y las vistas no se pierden entre corridas
        # (son consultas guardadas: muestran los datos nuevos solas). En la grilla del
        # DAG se ve una columna verde por dia -- la que predijo -- y el resto
        # en rosa.
        with engine.connect() as conn:
            hay_tabla = conn.execute(sqlalchemy.text(
                "SELECT to_regclass('gold.predicciones') IS NOT NULL")).scalar()
            ya_esta = hay_tabla and conn.execute(sqlalchemy.text(
                "SELECT count(*) FROM gold.predicciones "
                "WHERE fecha_features = :f AND ventana = :v "
                "AND origen = 'produccion' AND champion_version = :c"),
                {"f": ultima_fecha.date(), "v": ventana, "c": champion_version}).scalar() > 0
        if ya_esta:
            msg = (f"[SKIP] Ya esta la prediccion con el dia {ultima_fecha:%Y-%m-%d} "
                   f"(champion v{champion_version}): sale una vez por dia, cuando "
                   "el dia cierra.")
            print(msg)
            raise AirflowSkipException(msg)

        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
        dia = df[df["fecha"] == ultima_fecha].dropna(subset=features)
        if dia.empty:
            print(f"[SKIP] Features incompletas para {ultima_fecha:%Y-%m-%d}: "
                  f"la ventana de {ventana} dia(s) sigue 'calentando'. "
                  "Nada que scorear todavia.")
            return {"status": "features_incompletas", "fecha": None, "rows": []}

        # --- 4) Scorear ---------------------------------------------------
        # Si el champion fue entrenado con OTRAS features que las que produce el
        # SQL de hoy, sklearn lo detecta y avisa. Es training-serving skew real:
        # el modelo espera una cosa y produccion le manda otra. Se saltea con log
        # claro en vez de romper el DAG -- un modelo viejo no es una falla de
        # infraestructura, es un modelo que hay que volver a entrenar.
        try:
            pred = model.predict(dia[features])
        except Exception as e:
            if "feature names" not in str(e).lower():
                raise
            print("[SKIP] El champion fue entrenado con features distintas a las "
                  "que genera el pipeline hoy.")
            print(f"       Features actuales: {features}")
            print("       Reentrena y promove un champion nuevo desde la seccion "
                  "3.3 del notebook de clase06.")
            print(f"       (sklearn: {str(e)[:120]})")
            return {"status": "features_desactualizadas", "fecha": None, "rows": []}
        proba = (model.predict_proba(dia[features])[:, 1]
                 if hasattr(model, "predict_proba") else [None] * len(pred))

        scored_at = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "fecha_features": str(ultima_fecha.date()),
                "crypto_id": cid,
                "symbol": sym,
                "predijo_alta_vol": int(p),
                "proba_alta_vol": (float(pr) if pr is not None else None),
                "champion_version": champion_version,
                "scored_at": scored_at,
                # La ventana se calculo arriba leyendola del champion: hay que
                # ESCRIBIRLA. Sin esto la fila cae en el default 0 -- una
                # ventana que no existe -- y el tablero la agrupa aparte.
                "origen": "produccion",
                "ventana": ventana,
            }
            for cid, sym, p, pr in zip(dia["crypto_id"], dia["symbol"], pred, proba)
        ]
        print(f"Scoreadas {len(rows)} criptos (features del {ultima_fecha:%Y-%m-%d}) "
              f"con {MODEL_NAME} v{champion_version}")
        return {"status": "ok", "fecha": str(ultima_fecha.date()),
                "ventana": ventana, "rows": rows}

    def _asegurar_tabla(conn):
        """Crea gold.predicciones si no existe. Idempotente, llamable N veces.

        Se llama ANTES del return temprano de write_predicciones: en un stack
        nuevo (sin champion, o con la ventana todavia "calentando") no hay
        nada que escribir, pero la tabla tiene que existir igual, porque
        las vistas de build_vista_aciertos la leen. Es exactamente el
        escenario que el header de este archivo promete que NO tiene que
        fallar.
        """
        import sqlalchemy  # noqa: F401  (el caller ya lo importo)

        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS gold")
        conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS gold.predicciones (
                fecha_features   date             NOT NULL,
                crypto_id        text             NOT NULL,
                symbol           text,
                predijo_alta_vol integer,
                proba_alta_vol   double precision,
                champion_version text,
                scored_at        timestamptz,
                origen           text             DEFAULT 'produccion',
                ventana          integer          NOT NULL,
                -- La ventana entra en la PK: un champion entrenado con otra
                -- ventana escribe filas distintas, no pisa las del anterior.
                PRIMARY KEY (fecha_features, crypto_id, ventana)
            )
        """)
        # La tabla nacio con el target anterior (direccion del precio).
        # RENAME conserva los datos y el IF lo hace idempotente: en una base
        # nueva el CREATE de arriba ya la crea con los nombres correctos.
        for viejo, nuevo in (("pred_sube_manana", "predijo_alta_vol"),
                             ("proba_sube", "proba_alta_vol")):
            conn.exec_driver_sql(f'''
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema = 'gold'
                                 AND table_name   = 'predicciones'
                                 AND column_name  = '{viejo}') THEN
                        ALTER TABLE gold.predicciones
                            RENAME COLUMN {viejo} TO {nuevo};
                    END IF;
                END $$;
            ''')

    @task
    def write_predicciones(payload: dict):
        """Escribe gold.predicciones de forma idempotente (DELETE del dia + INSERT)."""
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        # La tabla se crea SIEMPRE, incluso cuando no hay nada que escribir.
        # Antes esto vivia despues del return de abajo, y en un stack nuevo
        # (sin champion todavia) la tabla no llegaba a existir: la task
        # siguiente arranca con ALTER TABLE y moria con 42P01. Crearla vacia
        # es gratis y deja el pipeline consistente desde la primera corrida.
        with engine.begin() as conn:
            _asegurar_tabla(conn)

        if payload["status"] != "ok" or not payload["rows"]:
            print(f"Sin predicciones para escribir (status={payload['status']}). "
                  "gold.predicciones queda como estaba (vacia si es la primera "
                  "corrida). NO es un error.")
            return

        with engine.begin() as conn:
            # Idempotencia: borra lo que haya de ese dia y esa ventana y lo
            # reescribe (mismo principio que Bronze). Si se promovio otro
            # champion, su prediccion reemplaza a la del anterior.
            conn.execute(
                sqlalchemy.text(
                    "DELETE FROM gold.predicciones "
                    "WHERE fecha_features = :f AND ventana = :v"
                ),
                {"f": payload["fecha"], "v": payload["ventana"]},
            )
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO gold.predicciones
                        (fecha_features, crypto_id, symbol, predijo_alta_vol,
                         proba_alta_vol, champion_version, scored_at,
                         origen, ventana)
                    VALUES (:fecha_features, :crypto_id, :symbol, :predijo_alta_vol,
                            :proba_alta_vol, :champion_version, :scored_at,
                            :origen, :ventana)
                """),
                payload["rows"],
            )
        print(f"gold.predicciones: {len(payload['rows'])} filas escritas "
              f"para {payload['fecha']} (champion v{payload['rows'][0]['champion_version']})")

    @task
    def build_vista_aciertos():
        """gold.v_ml_aciertos: el accuracy REAL, contra lo que efectivamente paso.

        Esta es la unica metrica que no se puede inflar. El accuracy del
        entrenamiento sale de un walk-forward sobre datos que ya existian; este
        sale de predicciones hechas ANTES de conocer el resultado.

        Regla del join: una prediccion hecha con features del dia D apunta a D+1,
        y se corrige contra la MEDIANA de ese dia -- la misma vara que usa
        el target al entrenar.
        Es un INNER JOIN a proposito -- una prediccion sobre un dia que todavia
        no ocurrio NO aparece. No se puede corregir un examen sin respuestas.
        """
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            # DROP + CREATE, no CREATE OR REPLACE: reemplazar una vista solo
            # admite AGREGAR columnas al final. Si se suma una en el medio
            # (como `ventana`), falla con "cannot change name of view column".
            # DROP + CREATE, no CREATE OR REPLACE: reemplazar una vista solo
            # admite AGREGAR columnas al final, y aca cambian varias.
            # ------------------------------------------------------------
            # LA DEFINICION DE "VOLATIL", EN UN SOLO LUGAR.
            #
            # Dos pasos, y ninguno usa un umbral fijo:
            #
            #   1) CUANTO se movio cada cripto ese dia. Se mide con la
            #      dispersion de los precios intradia del dia contra su propio
            #      promedio (coeficiente de variacion). Dividir por el
            #      promedio es lo que lo hace comparable entre monedas: sin
            #      eso, bitcoin a 121.000 dolares "se mueve" mil veces mas
            #      que una moneda de 0,30 solo por la escala del precio.
            #
            #   2) La VARA es el propio mercado de ese dia: la mediana de
            #      todas las vol. Por eso "volatil" es RELATIVO -- en un dia
            #      de panico general no son todas volatiles, siempre hay una
            #      mitad arriba y una abajo.
            #
            # Y por eso el target queda balanceado 50/50 POR CONSTRUCCION.
            # (Por eso la clase mayoritaria acierta la mitad sin mirar un
            #  solo dato.)
            #
            # Este dato SOLO existe porque Silver guarda un snapshot cada
            # 15 minutos. El cierre diario -- un numero por dia -- no tiene
            # dispersion: no hay nada de que tomarle el desvio.
            #
            # Lee Silver y NINGUNA tabla de Gold BI, a proposito: crypto_gold
            # corre en paralelo y reconstruye su hecho y sus dimensiones con
            # DROP TABLE ... CASCADE. Una vista de ML colgada de esas tablas se
            # caeria con cada corrida de Gold. (La categoria de cada cripto
            # vive en gold.dim_crypto: quien la necesite la cruza al consultar.)
            # ------------------------------------------------------------
            conn.exec_driver_sql("DROP VIEW IF EXISTS gold.v_volatilidad_diaria CASCADE")
            conn.exec_driver_sql("""
                CREATE VIEW gold.v_volatilidad_diaria AS
                WITH intra AS (
                    SELECT s.id                           AS crypto_id,
                           max(s.symbol)                  AS symbol,
                           s.snapshot_ts::timestamp::date AS fecha,
                           count(*)                       AS snapshots,
                           avg(s.current_price)           AS precio_medio,
                           stddev_samp(s.current_price)   AS desvio,
                           min(s.current_price)           AS precio_min,
                           max(s.current_price)           AS precio_max,
                           stddev_samp(s.current_price)
                               / NULLIF(avg(s.current_price), 0) * 100 AS vol
                    FROM silver.crypto_markets s
                    -- Solo dias cerrados (la misma regla que las features):
                    -- una prediccion se corrige cuando su dia termino.
                    WHERE s.snapshot_ts::timestamp::date < current_date
                       OR EXISTS (SELECT 1 FROM silver.crypto_markets
                                  WHERE snapshot_ts::timestamp = current_date + time '23:45')
                    GROUP BY s.id, s.snapshot_ts::timestamp::date
                    -- 20 mediciones o menos no describen un dia: un desvio
                    -- sobre 3 puntos es ruido, no volatilidad.
                    HAVING count(*) > 20
                ),
                vara AS (
                    SELECT fecha,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY vol) AS mediana
                    FROM intra GROUP BY fecha
                )
                SELECT i.crypto_id, i.symbol,
                       i.fecha, i.snapshots,
                       round(i.precio_medio::numeric, 6)  AS precio_medio,
                       round(i.desvio::numeric, 6)        AS desvio,
                       round(i.precio_min::numeric, 6)    AS precio_min,
                       round(i.precio_max::numeric, 6)    AS precio_max,
                       round(i.vol::numeric, 3)           AS vol,
                       round(v.mediana::numeric, 3)       AS mediana_del_dia,
                       (i.vol > v.mediana)::int           AS alta_vol
                FROM intra i
                JOIN vara v ON v.fecha = i.fecha
            """)
            conn.exec_driver_sql("DROP VIEW IF EXISTS gold.v_ml_aciertos")
            conn.exec_driver_sql("""
                CREATE VIEW gold.v_ml_aciertos AS
                -- Ya no se recalcula la volatilidad aca: se LEE de
                -- v_volatilidad_diaria. Antes este CTE repetia el mismo
                -- SQL, y dos copias de una definicion son dos definiciones
                -- esperando divergir -- justo en el lugar donde se corrige
                -- el examen. Una sola vara, escrita una sola vez.
                SELECT p.fecha_features                    AS predijo_con_datos_del,
                       p.fecha_features + 1                AS dia_predicho,
                       p.crypto_id,
                       p.symbol,
                       p.predijo_alta_vol,
                       p.proba_alta_vol,
                       p.champion_version,
                       p.ventana,
                       p.origen,
                       v.alta_vol                          AS realmente_alta_vol,
                       v.vol                               AS vol_real,
                       v.mediana_del_dia,
                       (p.predijo_alta_vol = v.alta_vol)   AS acerto
                FROM gold.predicciones p
                JOIN gold.v_volatilidad_diaria v
                  ON v.crypto_id = p.crypto_id
                 AND v.fecha     = p.fecha_features + 1
            """)
            # ------------------------------------------------------------
            # EL VEREDICTO: el modelo al lado de las DOS referencias.
            #
            # 1) CLASE MAYORITARIA: predecir siempre la clase que venia
            #    dominando. Con el target balanceado por construccion,
            #    ronda 0.50.
            # 2) PERSISTENCIA: "manana se repite lo de hoy". Es volatility
            #    clustering hecho regla -- sin features, sin entrenar, sin
            #    MLflow.
            #
            # La vista devuelve las dos al lado del accuracy del modelo.
            # ------------------------------------------------------------
            conn.exec_driver_sql("DROP VIEW IF EXISTS gold.v_ml_veredicto")
            conn.exec_driver_sql("""
                CREATE VIEW gold.v_ml_veredicto AS
                WITH base_pers AS (
                    -- La persistencia, sobre las MISMAS criptos y los MISMOS
                    -- dias que el modelo: para cada prediccion, repetir lo que
                    -- paso el dia de sus features (el anterior al predicho).
                    -- Se cruza por fecha exacta y no con LAG: con un dia sin
                    -- datos en el medio, LAG compararia contra un dia de antes.
                    SELECT a.dia_predicho AS fecha,
                           avg((h.alta_vol = a.realmente_alta_vol)::int) AS acc
                    FROM gold.v_ml_aciertos a
                    JOIN gold.v_volatilidad_diaria h
                      ON h.crypto_id = a.crypto_id
                     AND h.fecha = a.predijo_con_datos_del
                    GROUP BY a.dia_predicho
                ),
                dia AS (
                    SELECT ventana, dia_predicho,
                           avg(acerto::int)                 AS acc,
                           avg(realmente_alta_vol::numeric) AS tasa,
                           count(*)                         AS n
                    FROM gold.v_ml_aciertos
                    GROUP BY ventana, dia_predicho
                ),
                con_pasado AS (
                    -- La mayoritaria se elige con lo que se sabia ANTES del
                    -- dia. Mirar el resultado del propio dia para decidir que
                    -- predecir es leakage: elige el lado ganador despues del
                    -- partido.
                    SELECT d.*,
                           avg(d.tasa) OVER (PARTITION BY d.ventana
                                             ORDER BY d.dia_predicho
                                             ROWS BETWEEN UNBOUNDED PRECEDING
                                                      AND 1 PRECEDING) AS tasa_hist
                    FROM dia d
                )
                SELECT
                    c.ventana,
                    count(*)                            AS dias,
                    sum(c.n)                            AS predicciones,
                    round(avg(c.acc)::numeric * 100, 1) AS accuracy,
                    round(avg(CASE WHEN c.tasa_hist IS NULL THEN NULL
                                   WHEN c.tasa_hist > 0.5 THEN c.tasa
                                   ELSE 1 - c.tasa END)::numeric * 100, 1)
                                                        AS base_mayoritaria,
                    round(avg(b.acc)::numeric * 100, 1) AS base_persistencia
                FROM con_pasado c
                LEFT JOIN base_pers b ON b.fecha = c.dia_predicho
                GROUP BY c.ventana
                ORDER BY c.ventana
            """)
            n = conn.exec_driver_sql(
                "SELECT count(*) FROM gold.v_ml_aciertos"
            ).scalar()
        print(f"gold.v_ml_aciertos lista: {n} prediccion(es) ya verificables.")
        if not n:
            print("  Todavia ninguna: la prediccion de hoy apunta a manana, y "
                  "manana no llego. Aparecen solas en la proxima corrida.")


    # Dos ramas independientes, a proposito: la ABT no alimenta al scoring
    # (el modelo lee los snapshots de Silver), asi que encadenarlas inventaria
    # una dependencia que no existe y haria esperar a una por la otra sin motivo.
    build_abt()
    write_predicciones(score_con_champion()) >> build_vista_aciertos()


crypto_ml()
