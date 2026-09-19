"""
DAG: crypto_ml
Clase 06 - Scoring (inferencia batch) con el modelo @champion del Registry

Pipeline:  gold.fact_crypto_markets + MLflow Registry  ->  gold.predicciones

Es la 4ta capa del pipeline productivo (SERVING) y el ultimo eslabon de la
cadena data-aware: se dispara POR DATO (asset GOLD_ABT), no por reloj.

    crypto_bronze  cron 0,15,30,45          --emite--> BRONZE_CRYPTO
    crypto_silver  schedule=[BRONZE_CRYPTO] --emite--> SILVER_CRYPTO
    crypto_gold    schedule=[SILVER_CRYPTO] --emite--> GOLD_STAR + GOLD_ABT
    crypto_ml      schedule=[GOLD_ABT]                 <-- este DAG

GOLD_ABT lo emite `crypto_gold` en la task `build_abt`, o sea en el momento en
que la ABT queda escrita -- no al final del DAG. Por eso el scoring arranca sin
esperar a que Gold termine de verificar integridad.

=============================================================================
DEPLOY
=============================================================================
Este archivo vive en clase06/ejercicios/ como material de la clase. Para
activarlo se copia a los DAGs del stack (el scheduler lo descubre solo, y
nace despausado: is_paused_upon_creation=False, modo produccion):

    cp clase06/ejercicios/dag_crypto_ml.py stack/dags/

=============================================================================
ESTE DAG NO ENTRENA: SOLO CONSUME EL CHAMPION
=============================================================================
El entrenamiento y la ELECCION del champion se hacen en el notebook de
clase06 (model zoo -> comparar runs -> alias @champion). Eso involucra
criterio humano y es la leccion de la clase: no se automatiza.

Este DAG toma el champion VIGENTE por alias
(`models:/crypto_volatilidad_{W}d@champion`, uno por ventana): cuando promuevas otra version
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
- MLflow server caido o Postgres caido -> eso SI es falla real: el task
  falla y se ve en rojo (con retries por si fue un parpadeo).

Salida: gold.predicciones, IDEMPOTENTE por dia de features
(CREATE TABLE IF NOT EXISTS + DELETE del dia + INSERT): re-correr el DAG
el mismo dia reescribe ese dia, nunca duplica.
"""

from airflow.decorators import dag, task
from datetime import datetime, timedelta, timezone
import os
import sys

# El asset se importa desde common/ (definido una sola vez, igual que el resto
# de la cadena: si cada DAG construyera su propio Asset(...), un typo lo rompe
# en silencio):
# productor y consumidor tienen que referirse al MISMO Asset, definido UNA vez.
sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_ABT  # noqa: E402

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
# Un modelo registrado POR VENTANA: cada uno tiene su propio @champion.
# Asi se pueden promover y comparar por separado, que es el punto de la clase.
# El Registry tiene un modelo POR VENTANA (crypto_volatilidad_1d/3d/7d),
# cada uno con su alias @champion. Pero este DAG sirve UNO SOLO: el de la
# ventana mas larga, que es la que mas historia mira.
#
# No es un olvido: servir los tres significaria escribir tres predicciones
# por cripto y por dia, y la tabla ya tiene la ventana en la PK para
# soportarlo -- pero la decision de que modelo va a produccion es humana y
# se toma promoviendo el alias, no multiplicando el scoring.
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

# Las tres ventanas que la clase compara. El historico se reconstruye para
# TODAS: la gracia es ver los tres modelos prediciendo el mismo dia distinto.
VENTANAS = [1, 3, 7]


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
    De los ~66 snapshots por cripto por dia que `fact_crypto_markets` acumula y
    que el cierre diario tira. La volatilidad intradiaria los usa: el pipeline ya
    los venia juntando, faltaba la pregunta que los aprovechara.

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
    SELECT crypto_id,
           snapshot_ts::date                                          AS fecha,
           stddev_samp(current_price) / NULLIF(avg(current_price), 0) * 100 AS vol,
           (max(current_price) - min(current_price))
               / NULLIF(avg(current_price), 0) * 100                  AS rango,
           avg(total_volume)                                          AS volumen,
           count(*)                                                   AS n_snaps,
           max(market_cap_rank)                                       AS market_cap_rank
    FROM gold.fact_crypto_markets
    GROUP BY 1, 2
    HAVING count(*) > 10
),
mediana AS (
    -- La vara del dia: la volatilidad tipica del mercado.
    SELECT fecha, percentile_cont(0.5) WITHIN GROUP (ORDER BY vol) AS med
    FROM intra GROUP BY fecha
),
serie AS (
    -- El symbol vive en la DIMENSION, no en la tabla de hechos: ese es el punto
    -- del star schema. Se trae con un join, no se duplica en el fact.
    SELECT i.*, m.med AS mediana_vol_del_dia, d.symbol
    FROM intra i
    JOIN mediana m ON m.fecha = i.fecha
    LEFT JOIN gold.dim_crypto d ON d.crypto_id = i.crypto_id
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
        (LEAD(vol) OVER w_hist > LEAD(mediana_vol_del_dia) OVER w_hist)::int
                                                                  AS target_alta_vol
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


@dag(
    dag_id="crypto_ml",
    start_date=datetime(2024, 1, 1),
    # DATA-AWARE: corre cuando `crypto_gold` termina de escribir la ABT y
    # emite GOLD_ABT. Sin cron: el scoring no tiene sentido "a las y cinco",
    # tiene sentido cuando hay features nuevas para scorear.
    schedule=[GOLD_ABT],
    catchup=False,
    is_paused_upon_creation=False,  # modo produccion: nace prendido
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["prod", "ml", "serving", "crypto"],
    doc_md="""
    ## crypto_ml - Scoring con el @champion (serving)

    Consume el asset **`gold_abt`**: cuando `crypto_gold` termina de construir
    la ABT, carga `models:/crypto_volatilidad_{W}d@champion` del MLflow del stack
    (`http://mlflow:5000`), reconstruye las features del ultimo dia con la
    MISMA query SQL del notebook y escribe **`gold.predicciones`**
    (idempotente por dia).

    **No entrena.** Si no hay champion o falta historia, saltea con un log
    claro (no falla). Ver el header del archivo.
    """,
)
def crypto_ml():

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
        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")

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

        # --- 2) Reconstruir las features del ULTIMO dia disponible ---
        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql(features_sql(ventana), engine, parse_dates=["fecha"])
        if df.empty:
            print("[SKIP] gold.fact_crypto_markets sin filas: el pipeline todavia "
                  "no poblo Gold. Nada que scorear.")
            return {"status": "sin_datos", "fecha": None, "rows": []}

        ultima_fecha = df["fecha"].max()
        hoy = df[df["fecha"] == ultima_fecha].dropna(subset=features)
        if hoy.empty:
            print(f"[SKIP] Features incompletas para {ultima_fecha:%Y-%m-%d}: "
                  f"la ventana de {ventana} dia(s) sigue 'calentando'. "
                  "Nada que scorear todavia.")
            return {"status": "features_incompletas", "fecha": None, "rows": []}

        # --- 3) Scorear ---------------------------------------------------
        # Si el champion fue entrenado con OTRAS features que las que produce el
        # SQL de hoy, sklearn lo detecta y avisa. Es training-serving skew real:
        # el modelo espera una cosa y produccion le manda otra. Se saltea con log
        # claro en vez de romper el DAG -- un modelo viejo no es una falla de
        # infraestructura, es un modelo que hay que volver a entrenar.
        try:
            pred = model.predict(hoy[features])
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
        proba = (model.predict_proba(hoy[features])[:, 1]
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
            for cid, sym, p, pr in zip(hoy["crypto_id"], hoy["symbol"], pred, proba)
        ]
        print(f"Scoreadas {len(rows)} criptos (features del {ultima_fecha:%Y-%m-%d}) "
              f"con {MODEL_NAME} v{champion_version}")
        return {"status": "ok", "fecha": str(ultima_fecha.date()),
                "ventana": ventana, "rows": rows}

    def _asegurar_tabla(conn):
        """Crea gold.predicciones si no existe. Idempotente, llamable N veces.

        Vive aca afuera y no adentro de write_predicciones porque
        `completar_historico` TAMBIEN la necesita: esa task empieza con
        cuatro ALTER TABLE, y `ADD COLUMN IF NOT EXISTS` protege la columna
        pero NO la tabla -- un ALTER sobre una relacion inexistente es error
        42P01, no un no-op.

        El caso se da solo en un stack nuevo: sin champion (o con las
        ventanas todavia "calentando") write_predicciones saltea con un
        return temprano, la tabla nunca se creaba, y la task siguiente
        moria. Es exactamente el escenario que el header de este archivo
        promete que NO tiene que fallar.
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
                -- La ventana entra en la PK: las tres (1/3/7) predicen la
                -- misma cripto el mismo dia, y son filas distintas.
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
            # Idempotencia: si el DAG corre dos veces el mismo dia,
            # borra ese dia y lo reescribe (mismo principio que Bronze).
            conn.execute(
                sqlalchemy.text(
                    "DELETE FROM gold.predicciones "
                    "WHERE fecha_features = :f AND origen = 'produccion'"
                ),
                {"f": payload["fecha"]},
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
    def completar_historico():
        """Predicciones historicas para CADA ventana, no solo una.

        La gracia didactica es ver los tres modelos prediciendo el mismo dia y
        diferir entre si: uno mira el retorno de ayer, otro resume 3 dias, otro
        7. Guardar solo el "mejor" escondería justamente lo que hay que mostrar.

        Cada prediccion se entrena SOLO con fechas anteriores a la que predice
        (walk-forward). Un modelo entrenado con todo el historico y aplicado
        hacia atras daria un accuracy inflado: habria visto en entrenamiento los
        dias que despues "predice". Es la trampa que la clase enseña a detectar.
        """
        import pandas as pd
        import sqlalchemy
        from sklearn.ensemble import RandomForestClassifier

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            # Antes que los ALTER: si la tabla no existe, `ADD COLUMN IF NOT
            # EXISTS` NO la crea -- falla con 42P01. write_predicciones ya la
            # asegura, pero repetirlo aca cuesta nada y vuelve a esta task
            # independiente del camino que haya tomado la anterior.
            _asegurar_tabla(conn)
            conn.exec_driver_sql(
                "ALTER TABLE gold.predicciones "
                "ADD COLUMN IF NOT EXISTS origen text DEFAULT 'produccion'")
            conn.exec_driver_sql(
                "ALTER TABLE gold.predicciones "
                "ADD COLUMN IF NOT EXISTS ventana integer DEFAULT 0")
            # La PK pasa a incluir la ventana: el mismo dia y la misma cripto
            # tienen ahora una prediccion POR MODELO.
            conn.exec_driver_sql(
                "ALTER TABLE gold.predicciones DROP CONSTRAINT IF EXISTS predicciones_pkey")
            conn.exec_driver_sql(
                "ALTER TABLE gold.predicciones "
                "ADD PRIMARY KEY (fecha_features, crypto_id, ventana)")

        ya = pd.read_sql("SELECT DISTINCT fecha_features, ventana FROM gold.predicciones",
                         engine, parse_dates=["fecha_features"])
        hechas = {(r.fecha_features.date(), int(r.ventana)) for r in ya.itertuples()}

        filas, resumen = [], {}
        for W in VENTANAS:
            df = pd.read_sql(features_sql(W), engine, parse_dates=["fecha"])
            cols = columnas_features(W)
            df = df.dropna(subset=cols + ["target_alta_vol"]).copy()
            if df.empty:
                resumen[W] = 0
                continue
            df["target_alta_vol"] = df["target_alta_vol"].astype(int)
            n_w = 0
            for f in sorted(df["fecha"].unique()):
                d = pd.Timestamp(f).date()
                if (d, W) in hechas:
                    continue
                train = df[df["fecha"] < f]       # SOLO el pasado
                test = df[df["fecha"] == f]
                if len(train) < 10 or test.empty:
                    continue
                m = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
                m.fit(train[cols], train["target_alta_vol"])
                proba = m.predict_proba(test[cols])[:, 1]
                for (_, r), pr in zip(test.iterrows(), proba):
                    filas.append({
                        "fecha_features": str(d), "crypto_id": r["crypto_id"],
                        "symbol": r["symbol"], "predijo_alta_vol": int(pr > 0.5),
                        "proba_alta_vol": float(pr), "champion_version": f"wf_v{W}",
                        "scored_at": datetime.now(timezone.utc).isoformat(),
                        "origen": "reconstruido", "ventana": int(W),
                    })
                    n_w += 1
            resumen[W] = n_w

        print(f"Predicciones nuevas por ventana: {resumen}")
        if not filas:
            print("Sin huecos: cada ventana ya tiene sus fechas.")
            return

        with engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO gold.predicciones
                        (fecha_features, crypto_id, symbol, predijo_alta_vol,
                         proba_alta_vol, champion_version, scored_at, origen, ventana)
                    VALUES (:fecha_features, :crypto_id, :symbol, :predijo_alta_vol,
                            :proba_alta_vol, :champion_version, :scored_at,
                            :origen, :ventana)
                    ON CONFLICT (fecha_features, crypto_id, ventana) DO NOTHING
                """),
                filas,
            )
        print(f"Insertadas {len(filas)} predicciones reconstruidas.")


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
            #      dispersion de los ~66 precios intradia contra su propio
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
            # (Que es justo lo que vuelve inutil al baseline mayoritario:
            #  adivinar siempre la misma clase acierta la mitad sin mirar
            #  un solo dato. La vara honesta es la persistencia.)
            #
            # Este dato SOLO existe porque la fact guarda un snapshot cada
            # 15 minutos. El cierre diario -- un numero por dia -- no tiene
            # dispersion: no hay nada de que tomarle el desvio.
            # ------------------------------------------------------------
            conn.exec_driver_sql("DROP VIEW IF EXISTS gold.v_volatilidad_diaria CASCADE")
            conn.exec_driver_sql("""
                CREATE VIEW gold.v_volatilidad_diaria AS
                WITH intra AS (
                    SELECT f.crypto_id,
                           f.snapshot_ts::date            AS fecha,
                           count(*)                       AS snapshots,
                           avg(f.current_price)           AS precio_medio,
                           stddev_samp(f.current_price)   AS desvio,
                           min(f.current_price)           AS precio_min,
                           max(f.current_price)           AS precio_max,
                           stddev_samp(f.current_price)
                               / NULLIF(avg(f.current_price), 0) * 100 AS vol
                    FROM gold.fact_crypto_markets f
                    GROUP BY 1, 2
                    -- Menos de 10 mediciones no describen un dia: un desvio
                    -- sobre 3 puntos es ruido, no volatilidad.
                    HAVING count(*) > 10
                ),
                vara AS (
                    SELECT fecha,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY vol) AS mediana
                    FROM intra GROUP BY fecha
                )
                SELECT i.crypto_id, d.symbol, d.name, d.categoria,
                       i.fecha, i.snapshots,
                       round(i.precio_medio::numeric, 6)  AS precio_medio,
                       round(i.desvio::numeric, 6)        AS desvio,
                       round(i.precio_min::numeric, 6)    AS precio_min,
                       round(i.precio_max::numeric, 6)    AS precio_max,
                       round(i.vol::numeric, 3)           AS vol,
                       round(v.mediana::numeric, 3)       AS mediana_del_dia,
                       (i.vol > v.mediana)::int           AS alta_vol
                FROM intra i
                JOIN vara v          ON v.fecha = i.fecha
                LEFT JOIN gold.dim_crypto d USING (crypto_id)
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
            # EL VEREDICTO: el modelo contra las DOS varas.
            #
            # 1) MAYORITARIA: predecir siempre la clase que venia dominando.
            #    Con el target balanceado por construccion ronda 0.50: es la
            #    vara FACIL, y contra ella casi cualquier cosa "gana".
            # 2) PERSISTENCIA: "manana se repite lo de hoy". Es volatility
            #    clustering hecho regla -- sin features, sin entrenar, sin
            #    MLflow. Es la vara que de verdad hay que superar: si el
            #    modelo no le gana, entrenar no compro nada.
            #
            # Que la vista devuelva las DOS es deliberado. Elegir la vara
            # facil y declarar victoria es el error mas comun del oficio, y se
            # comete sin mala fe. Aca queda a la vista.
            # ------------------------------------------------------------
            conn.exec_driver_sql("DROP VIEW IF EXISTS gold.v_ml_veredicto")
            conn.exec_driver_sql("""
                CREATE VIEW gold.v_ml_veredicto AS
                WITH real AS (
                    -- La verdad observada: una fila por cripta y dia.
                    -- DISTINCT porque v_ml_aciertos repite el dia por ventana.
                    SELECT DISTINCT crypto_id, dia_predicho AS fecha,
                           realmente_alta_vol AS alta
                    FROM gold.v_ml_aciertos
                ),
                persistencia AS (
                    SELECT crypto_id, fecha, alta,
                           LAG(alta) OVER (PARTITION BY crypto_id
                                           ORDER BY fecha) AS alta_ayer
                    FROM real
                ),
                base_pers AS (
                    -- Acierto de la regla trivial: lo de ayer, aplicado a hoy.
                    SELECT fecha, avg((alta = alta_ayer)::int) AS acc
                    FROM persistencia
                    WHERE alta_ayer IS NOT NULL
                    GROUP BY fecha
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


    write_predicciones(score_con_champion()) >> completar_historico() >> build_vista_aciertos()


crypto_ml()
