"""
DAG: crypto_gold
Clase 05 - Transformacion Silver -> Gold (Star Schema enriquecido + ABT)

Pipeline: silver.crypto_markets + bronze.global_market ->
  - gold.dim_crypto          (datos semi-estaticos por cripto)
  - gold.dim_tiempo          (dimension temporal por dia)
  - gold.fact_crypto_markets (17 metricas por cripto por snapshot)
  - gold.fact_global_market  (mercado total por dia)
  - gold.gold_abt_crypto     (wide table con features derivadas para ML)

=============================================================================
ESTE DAG ES SQL (ELT), NO PANDAS
=============================================================================
Toda la transformacion ocurre DENTRO de Postgres via `CREATE TABLE ... AS
SELECT ...` (pushdown). El DAG solo ORQUESTA SQL: no trae filas a Python,
no usa pandas para transformar, no pasa `records` por XCom. Es el mismo
principio de pushdown que aplicamos en Silver (clase 04): el motor hace el
trabajo pesado (GROUP BY, JOIN, window functions, CASE) sobre los datos
donde viven. Es ELT (Extract-Load-Transform), el patron estandar del
data warehousing moderno.

=============================================================================
GRANO TEMPORAL: snapshot_ts (NO ingested_at)
=============================================================================
Bronze estampa DOS marcas temporales:
  - snapshot_ts: el DIA/momento LOGICO del dato (redondeado al minuto;
                 todas las criptas de una corrida comparten snapshot_ts).
  - ingested_at: cuando la fila se ESCRIBIO fisicamente en la base.

Gold modela el tiempo por `snapshot_ts`, NUNCA por `ingested_at`. Razon:
Silver es incremental y *backfilleable* (`airflow dags backfill`). Si se
reprocesa el dia D, esas filas se reescriben HOY -> su `ingested_at` pasa
a ser hoy, pero su `snapshot_ts` sigue siendo D. Si Gold usara
`ingested_at`, los datos reprocesados de D apareceran bajo "hoy" y se
romperia el "correr para atras". Por eso fecha/fecha_id y los "ultimo
valor por cripta" se derivan de `snapshot_ts` (desempate `ingested_at`).

=============================================================================
FULL-REFRESH: DECISION CONSCIENTE
=============================================================================
Gold se reconstruye COMPLETO en cada corrida (DROP + CREATE TABLE AS desde
TODO Silver). Es una decision deliberada, no un descuido:
  - El modelo dimensional es chico (decenas de criptas x N dias): rebuild
    barato.
  - Siempre consistente: no hay estado parcial que reconciliar.
  - Refleja AUTOMATICAMENTE cualquier backfill de Silver. Para "reprocesar
    Gold del pasado" no hace falta logica incremental: basta re-correr Gold
    una vez y toma el estado actual (ya backfilleado) de Silver.
A diferencia de Silver (incremental por dia), Gold es full-refresh: cada
capa elige la estrategia que le conviene.

=============================================================================
ACOPLE Silver -> Gold (por cron; fragil, documentado)
=============================================================================
Hoy el orden Silver->Gold se logra por OFFSET DE CRON:
  - crypto_silver: @daily            (00:00 UTC)
  - crypto_gold:   "0 3 * * *"       (03:00 UTC, 3h despues)
Es fragil: asume que Silver termina en < 3h y que no reintenta tarde. Si
Silver se atrasa, Gold puede leer Silver a medio actualizar.
Alternativas robustas (NO implementadas aca, se dejan documentadas):
  - Airflow Datasets/Assets: Gold se dispara cuando Silver actualiza
    `silver.crypto_markets` (scheduling data-aware, Airflow 3).
  - DAG de orquestacion (stack/dags/04-orchestration/) que encadene
    bronze -> silver -> gold con dependencias explicitas.

=============================================================================
POR QUE GOLD NO USA EL CONTRATO (Pydantic)
=============================================================================
Silver valida CADA FILA contra `crypto_markets.yaml` (Pydantic) y manda
las invalidas a quarantine. Gold NO revalida fila a fila: la unidad de
validacion cambia de capa. En Gold importa la INTEGRIDAD REFERENCIAL
(que toda FK de la fact apunte a una PK de la dim), que verifica
`verify_integrity()` con LEFT JOIN. Si una fila tenia problemas, era
responsabilidad de Silver (y los atrapo). Gold asume el schema de Silver:
si falta una columna, el DAG falla entero (a proposito: "schema completo").
=============================================================================
"""

from airflow.decorators import dag, task
from datetime import datetime
import os

# Cadena de conexion a PostgreSQL (mismo patron que Bronze y Silver)
DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


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
    dag_id="crypto_gold",
    start_date=datetime(2024, 1, 1),
    # Corre a las 03:00 UTC, 3h DESPUES de crypto_silver (@daily = 00:00).
    # El orden Silver->Gold es por offset de cron (fragil; ver el header del
    # modulo: alternativas robustas = Datasets/Assets o DAG de orquestacion).
    schedule="0 3 * * *",
    catchup=False,
    tags=["prod", "gold", "crypto"],
    doc_md="""
    ## Crypto Gold - Star Schema + ABT (SQL ELT)

    Reconstruye **completo** desde Silver (full-refresh, decision consciente):
    - **BI**: dim_crypto, dim_tiempo, fact_crypto_markets, fact_global_market
    - **ML**: gold_abt_crypto (wide table con features derivadas)

    Toda la transformacion es **SQL en Postgres** (`CREATE TABLE AS SELECT`,
    pushdown / ELT). Grano temporal = `snapshot_ts` (no `ingested_at`), para
    no romper el reproceso/backfill de Silver.

    **Reproceso del pasado**: no hay logica incremental; basta re-correr este
    DAG una vez y toma el estado actual de Silver (ya backfilleado).

    **Acople Silver->Gold**: por offset de cron (Silver 00:00 / Gold 03:00).
    Fragil; alternativas robustas (Datasets/Assets, DAG de orquestacion)
    documentadas en el header del modulo, NO implementadas.
    """,
)
def crypto_gold():

    # ============================================================
    # DIMENSION CRIPTOMONEDAS (datos semi-estaticos)
    # ============================================================
    # DISTINCT ON (id) ... ORDER BY id, snapshot_ts DESC, ingested_at DESC
    # = "una fila por cripta, la del snapshot logico mas reciente"
    # (reemplaza el groupby('id').last() de la version pandas; ordena por
    # snapshot_ts, NO ingested_at -> robusto a backfills).
    @task
    def build_dim_crypto():
        """gold.dim_crypto via SQL (DISTINCT ON por snapshot_ts)."""
        _run_ddl("""
            DROP TABLE IF EXISTS gold.dim_crypto;
            CREATE TABLE gold.dim_crypto AS
            SELECT DISTINCT ON (id)
                   id           AS crypto_id,
                   symbol,
                   name,
                   max_supply,
                   total_supply,
                   ath,
                   ath_date,
                   atl,
                   atl_date
            FROM silver.crypto_markets
            ORDER BY id, snapshot_ts DESC, ingested_at DESC
        """)
        print("gold.dim_crypto reconstruida (DISTINCT ON id, por snapshot_ts)")

    # ============================================================
    # DIMENSION TEMPORAL (una fila por dia con datos)
    # ============================================================
    # fecha_id = YYYYMMDD entero (surrogate key temporal estandar DWH).
    # El dia sale de snapshot_ts::date (dia LOGICO), no de ingested_at.
    @task
    def build_dim_tiempo():
        """gold.dim_tiempo via SQL desde snapshot_ts::date."""
        _run_ddl("""
            DROP TABLE IF EXISTS gold.dim_tiempo;
            CREATE TABLE gold.dim_tiempo AS
            WITH fechas AS (
                SELECT DISTINCT snapshot_ts::date AS fecha
                FROM silver.crypto_markets
            )
            SELECT
                fecha,
                to_char(fecha, 'YYYYMMDD')::int   AS fecha_id,
                EXTRACT(year    FROM fecha)::int  AS anio,
                EXTRACT(month   FROM fecha)::int  AS mes,
                EXTRACT(quarter FROM fecha)::int  AS trimestre,
                trim(to_char(fecha, 'Day'))       AS dia_semana,
                (EXTRACT(dow FROM fecha) IN (0, 6)) AS es_fin_de_semana
            FROM fechas
            ORDER BY fecha
        """)
        print("gold.dim_tiempo reconstruida (snapshot_ts::date)")

    # ============================================================
    # FACT TABLE - CRYPTO MARKETS (17 metricas + 2 FKs)
    # ============================================================
    # Grano: 1 fila por fila de Silver (port fiel de la version pandas).
    # FKs: crypto_id -> dim_crypto.crypto_id ; fecha_id -> dim_tiempo.fecha_id
    # (fecha_id derivado de snapshot_ts, NO ingested_at).
    @task
    def build_fact():
        """gold.fact_crypto_markets via SQL."""
        _run_ddl("""
            DROP TABLE IF EXISTS gold.fact_crypto_markets;
            CREATE TABLE gold.fact_crypto_markets AS
            SELECT
                id                                          AS crypto_id,
                to_char(snapshot_ts::date, 'YYYYMMDD')::int AS fecha_id,
                current_price, high_24h, low_24h, price_change_24h,
                -- Metricas DERIVADAS: Bronze/Silver NO las traen; las calcula
                -- Gold a partir de las columnas base (es trabajo de la capa
                -- analitica). El dashboard las consume (spread_pct, etc.).
                (high_24h - low_24h)                                 AS spread_24h,
                (high_24h - low_24h) / NULLIF(current_price, 0) * 100 AS spread_pct,
                price_change_percentage_24h,
                market_cap_change_percentage_24h,
                market_cap, total_volume, fully_diluted_valuation,
                circulating_supply,
                circulating_supply / NULLIF(total_supply, 0)         AS supply_ratio,
                market_cap_rank,
                market_cap / NULLIF(fully_diluted_valuation, 0)      AS fdv_ratio,
                ath_change_percentage                                AS ath_distance_pct,
                atl_change_percentage                                AS atl_distance_pct,
                now()                   AS _processed_at,
                'silver.crypto_markets' AS _source_table
            FROM silver.crypto_markets
        """)
        print("gold.fact_crypto_markets reconstruida (fecha_id por snapshot_ts)")

    # ============================================================
    # FACT TABLE - GLOBAL MARKET (mercado total por dia)
    # ============================================================
    # Excepcion documentada: lee de bronze.global_market DIRECTO (salta
    # Silver). El dato macro de CoinGecko ya viene agregado/confiable y
    # Silver no agregaria valor. Si la tabla no existe (crypto_bronze no
    # corrio aun), se saltea sin romper el DAG (to_regclass guard).
    @task
    def build_fact_global():
        """gold.fact_global_market via SQL (si existe bronze.global_market)."""
        if not _tabla_existe("bronze.global_market"):
            print("bronze.global_market no existe -> se saltea fact_global_market")
            return
        _run_ddl("""
            DROP TABLE IF EXISTS gold.fact_global_market;
            CREATE TABLE gold.fact_global_market AS
            SELECT DISTINCT ON (snapshot_ts::date)
                to_char(snapshot_ts::date, 'YYYYMMDD')::int AS fecha_id,
                total_market_cap_usd, total_volume_usd,
                btc_dominance, eth_dominance,
                active_cryptocurrencies, markets,
                market_cap_change_pct_24h,
                now()                  AS _processed_at,
                'bronze.global_market' AS _source_table
            FROM bronze.global_market
            ORDER BY snapshot_ts::date, ingested_at DESC
        """)
        print("gold.fact_global_market reconstruida (1 fila por dia, snapshot_ts)")

    # ============================================================
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
    @task
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
            DROP TABLE IF EXISTS gold.gold_abt_crypto;
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
                    market_cap / NULLIF(fully_diluted_valuation, 0)       AS fdv_ratio,
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

    # ============================================================
    # VERIFICAR INTEGRIDAD REFERENCIAL + RESUMEN
    # ============================================================
    # Integridad = toda FK de la fact apunta a una PK existente en la dim.
    # Se mide con LEFT JOIN + WHERE d.crypto_id IS NULL (huerfanos).
    # Nota: silver.global_market NO se lista: por diseno el dato macro
    # salta Silver (queda en bronze.global_market).
    @task
    def verify_integrity():
        """Resumen del pipeline + chequeo de integridad referencial (SQL)."""
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        tablas = [
            ("bronze", "crypto_markets", "Bronze"),
            ("bronze", "global_market", "Bronze global"),
            ("silver", "crypto_markets", "Silver"),
            ("silver", "quarantine_crypto_markets", "Quarantine"),
            ("gold", "dim_crypto", "Gold dim"),
            ("gold", "dim_tiempo", "Gold dim"),
            ("gold", "fact_crypto_markets", "Gold fact"),
            ("gold", "fact_global_market", "Gold fact global"),
            ("gold", "gold_abt_crypto", "Gold ABT"),
        ]
        print("=== Pipeline Medallion - Resumen ===")
        with engine.connect() as conn:
            for schema, tabla, capa in tablas:
                try:
                    n = conn.execute(
                        sqlalchemy.text(f"SELECT COUNT(*) FROM {schema}.{tabla}")
                    ).scalar()
                    print(f"  {capa:16s} | {schema}.{tabla:28s} | {n:>7} filas")
                except Exception:
                    print(f"  {capa:16s} | {schema}.{tabla:28s} | NO ENCONTRADA")

            try:
                huerfanos = conn.execute(sqlalchemy.text("""
                    SELECT COUNT(*)
                    FROM gold.fact_crypto_markets f
                    LEFT JOIN gold.dim_crypto d ON f.crypto_id = d.crypto_id
                    WHERE d.crypto_id IS NULL
                """)).scalar()
                print(f"\nIntegridad referencial (huerfanos fact->dim): "
                      f"{huerfanos} (esperado: 0)")
            except Exception as e:
                print(f"\nError verificando integridad: {e}")

    # ============================================================
    # FLUJO: 5 construcciones en paralelo -> verificacion final
    # ============================================================
    # Cada build_* corre su propio SQL contra Postgres (independientes).
    # verify_integrity() espera a que las 5 terminen.
    dim_c = build_dim_crypto()
    dim_t = build_dim_tiempo()
    fact = build_fact()
    fact_g = build_fact_global()
    abt = build_abt()

    [dim_c, dim_t, fact, fact_g, abt] >> verify_integrity()


# Instanciacion: obligatoria para que Airflow descubra el DAG.
crypto_gold()
