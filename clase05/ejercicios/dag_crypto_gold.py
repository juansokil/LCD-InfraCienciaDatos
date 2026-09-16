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
ACOPLE Silver -> Gold (data-aware, por Assets)
=============================================================================
La cadena entera se encadena por DATOS, no por reloj:

  crypto_bronze   cron 0,15,30,45          --emite-->  BRONZE_CRYPTO
  crypto_silver   schedule=[BRONZE_CRYPTO] --emite-->  SILVER_CRYPTO
  crypto_gold     schedule=[SILVER_CRYPTO] --emite-->  GOLD_STAR + GOLD_ABT
  crypto_ml       schedule=[GOLD_ABT]

Bronze conserva cron porque es el BORDE (consulta una API externa, no tiene
nada aguas arriba que esperar). Nadie mas adivina tiempos.

Antes esto se resolvia con CRON ESCALONADO (bronze :00, silver :05, gold :10).
El colchon era de 5 minutos: si Silver se atrasaba, Gold leia Silver a medio
actualizar y publicaba igual. Un pipeline que "anda" mientras miente.

Los dos assets que emite este DAG tienen consumidores distintos -- eso es
FAN-OUT real, no un ejemplo de juguete:
  GOLD_STAR -> el dashboard (las vistas gold.v_* ya estan)
  GOLD_ABT  -> crypto_ml, que scorea la ABT recien construida

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
from datetime import datetime, timedelta
import os
import sys

# Hacemos visible el paquete `common` (los assets se definen una sola vez ahi:
# si cada DAG construyera su propio Asset(...), un typo rompe el encadenado
# en silencio).
sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_ABT, GOLD_STAR, SILVER_CRYPTO  # noqa: E402

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
    # SELF-HEAL: si una task falla por una razon transitoria (Postgres ocupado,
    # deadlock), REINTENTA en vez de dejar el dia en rojo. Con el disparo por
    # asset el caso "upstream todavia vacio" ya no existe -- Gold no arranca
    # hasta que Silver escribio -- pero el retry sigue siendo barato.
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    start_date=datetime(2024, 1, 1),
    # ARRANCA SOLO (ver nota en crypto_bronze).
    is_paused_upon_creation=False,

    # DATA-AWARE: sin cron. Arranca EXACTAMENTE cuando load_silver termina y
    # emite SILVER_CRYPTO. Si Silver falla, Gold no corre -- que es lo correcto:
    # mejor Gold viejo y visible que Gold "fresco" construido sobre nada.
    #
    # Gold hace full-refresh (DROP + CREATE TABLE AS), asi que re-correrlo es
    # idempotente: dispararlo a mano desde la UI reconstruye el estado actual.
    schedule=[SILVER_CRYPTO],
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

    **Acople Silver->Gold**: data-aware. Este DAG no tiene cron: arranca cuando
    `crypto_silver` emite el asset `silver_crypto_markets`. A su vez emite
    `gold_star` (capa semantica lista, la consume el dashboard) y `gold_abt`
    (la consume `crypto_ml`).
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
        """gold.dim_crypto via SQL (DISTINCT ON por snapshot_ts).

        Ademas de los datos semi-estaticos, la dimension trae `categoria`:
        stablecoin / memecoin / commodity / bitcoin / altcoin.

        PARA QUE SIRVE. Es lo que vuelve util al star schema: con esta
        columna, CUALQUIER metrica de la fact se puede cortar por familia de
        moneda sin tocar la fact -- exactamente como `dia_semana` en
        `dim_tiempo` deja cortarla por dia. Sin la dimension, la pregunta
        "como se movieron las memecoins esta semana" no tiene respuesta:
        los hechos solos no saben que es una memecoin.

        POR QUE UNA COLUMNA Y NO UNA TABLA APARTE. Un star schema mantiene
        las dimensiones DESNORMALIZADAS a proposito: `categoria` es un
        atributo de la cripto, igual que `symbol`. Sacarla a una
        `dim_categoria` con FK seria un copo de nieve (snowflake): suma un
        JOIN a cada consulta para ahorrar unos bytes en cinco valores.
        Mismo criterio por el que `dim_tiempo` guarda `dia_semana` como
        texto en vez de apuntar a una tabla de dias.

        DE DONDE SALE EL MAPEO. De la taxonomia de CoinGecko
        (`/coins/categories`), consultada el 2026-09-15. Va como dato de
        REFERENCIA aca en Gold y no como ingesta: la familia de una moneda
        cambia cada muchos anos, no cada 15 minutos, y pedirsela a la API en
        cada corrida seria gastar cuota para traer siempre lo mismo (el tier
        gratuito responde 429 enseguida). Lo que NO esta en la lista cae en
        `altcoin`, asi que una cripto nueva en el top 50 no rompe nada.
        """
        _run_ddl("""
            DROP TABLE IF EXISTS gold.dim_crypto CASCADE;
            CREATE TABLE gold.dim_crypto AS
            WITH mapa_categoria (crypto_id, categoria) AS (
                VALUES
                    ('dai', 'stablecoin'),
                    ('ethena-usde', 'stablecoin'),
                    ('global-dollar', 'stablecoin'),
                    ('paypal-usd', 'stablecoin'),
                    ('ripple-usd', 'stablecoin'),
                    ('tether', 'stablecoin'),
                    ('usd-coin', 'stablecoin'),
                    ('usd1-wlfi', 'stablecoin'),
                    ('usds', 'stablecoin'),
                    ('dogecoin', 'memecoin'),
                    ('memecore', 'memecoin'),
                    ('pump-fun', 'memecoin'),
                    ('shiba-inu', 'memecoin'),
                    ('pax-gold', 'commodity'),
                    ('tether-gold', 'commodity'),
                    -- Dolares tokenizados que CoinGecko NO archiva bajo
                    -- "Stablecoins" (son fondos y treasuries tokenizados),
                    -- pero cotizan clavados al dolar: volatilidad 0,000.
                    -- La taxonomia del proveedor esta hecha para su negocio,
                    -- no para este analisis; se la valida contra el dato y se
                    -- corrige, dejando dicho por que.
                    ('blackrock-usd-institutional-digital-liquidity-fund', 'stablecoin'),
                    ('hashnote-usyc', 'stablecoin'),
                    ('ondo-us-dollar-yield', 'stablecoin')
            )
            SELECT DISTINCT ON (s.id)
                   s.id           AS crypto_id,
                   s.symbol,
                   s.name,
                   s.max_supply,
                   s.total_supply,
                   s.ath,
                   s.ath_date,
                   s.atl,
                   s.atl_date,
                   -- Bitcoin va aparte: es su propia categoria en cualquier
                   -- analisis cripto, y meterlo entre las altcoins
                   -- (literalmente "las que no son bitcoin") seria un error.
                   CASE WHEN s.id = 'bitcoin' THEN 'bitcoin'
                        ELSE COALESCE(m.categoria, 'altcoin')
                   END            AS categoria
            FROM silver.crypto_markets s
            LEFT JOIN mapa_categoria m ON m.crypto_id = s.id
            ORDER BY s.id, s.snapshot_ts DESC, s.ingested_at DESC
        """)
        print("gold.dim_crypto reconstruida (DISTINCT ON id, por snapshot_ts)")

    # ============================================================
    # DIMENSION TEMPORAL (una fila por dia con datos)
    # ============================================================
    # fecha_id = YYYYMMDD entero (surrogate key temporal estandar DWH).
    # El dia sale de snapshot_ts::date (dia LOGICO), no de ingested_at.
    @task
    def build_dim_tiempo():
        """gold.dim_tiempo DENSA via generate_series.

        Una dimension de fecha se construye DENSA a proposito: tiene una fila
        por dia del rango, haya habido datos o no. Antes esto era un
        `SELECT DISTINCT snapshot_ts::date` sobre Silver -- o sea, la dimension
        salia de los hechos.

        La diferencia importa el dia que el pipeline se cae: con una dimension
        derivada, un dia sin ingesta simplemente NO EXISTE, y el agujero es
        invisible (nadie puede echar de menos una fila que nunca estuvo). Con
        una dimension densa, ese dia esta en la dimension, el LEFT JOIN contra
        la fact devuelve NULL, y el hueco SE VE.

        Es la misma idea que el calendario de una planilla: las filas de los
        dias existen antes que los datos.
        """
        _run_ddl("""
            DROP TABLE IF EXISTS gold.dim_tiempo CASCADE;
            CREATE TABLE gold.dim_tiempo AS
            WITH rango AS (
                SELECT min(snapshot_ts::date) AS desde,
                       max(snapshot_ts::date) AS hasta
                FROM silver.crypto_markets
            ),
            fechas AS (
                SELECT generate_series(desde, hasta, interval '1 day')::date AS fecha
                FROM rango
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
    # GRANO EXPLICITO: 1 fila = 1 cripto x 1 snapshot (crypto_id, snapshot_ts).
    # Declarar el grano ANTES de crear la fact es la regla de oro de Gold:
    # sin snapshot_ts, con el cron de 15' se acumulan ~96 filas/cripto/dia
    # indistinguibles -> KPIs inflados y "ultimo precio" arbitrario.
    # FKs: crypto_id -> dim_crypto.crypto_id ; fecha_id -> dim_tiempo.fecha_id
    # (fecha_id derivado de snapshot_ts, NO ingested_at).
    @task
    def build_fact():
        """gold.fact_crypto_markets via SQL."""
        _run_ddl("""
            -- CASCADE: las vistas gold.v_* dependen de esta tabla; se
            -- recrean en build_views(), despues de que todas las tablas
            -- estan. (Y drop_views() las baja ANTES de todo: ver el flujo.)
            DROP TABLE IF EXISTS gold.fact_crypto_markets CASCADE;
            CREATE TABLE gold.fact_crypto_markets AS
            SELECT
                id                                          AS crypto_id,
                -- snapshot_ts llega como TEXT desde bronze (strftime del DAG);
                -- Gold lo tipa: los consumidores hacen aritmetica de tiempo.
                snapshot_ts::timestamp                      AS snapshot_ts,
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
                -- ::numeric a proposito: los dos operandos son bigint y sin el cast
                -- Postgres hace division ENTERA -> la columna solo valdria 0 o 1.
                market_cap::numeric
                    / NULLIF(fully_diluted_valuation, 0)             AS fdv_ratio,
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
        # GRANO: 1 fila = 1 SNAPSHOT (no 1 por dia).
        # Antes habia aca un `DISTINCT ON (snapshot_ts::date)` que dejaba una
        # sola fila por dia: con 211 snapshots ingestados, la tabla tenia 3
        # filas. Es el mismo error de grano que ya se corrigio en
        # fact_crypto_markets -- y el que obligaba al dashboard a dibujar un
        # sparkline de 3 puntos.
        #
        # Guardar el grano fino es barato y NO se puede deshacer despues:
        # de snapshots se puede agregar a dias cuando quieras (lo hace
        # v_kpis_mercado); de un promedio diario no se puede recuperar el
        # intradia. La regla: la fact guarda el grano mas fino disponible,
        # las vistas agregan.
        _run_ddl("""
            DROP TABLE IF EXISTS gold.fact_global_market CASCADE;
            CREATE TABLE gold.fact_global_market AS
            SELECT DISTINCT ON (snapshot_ts)
                to_char(snapshot_ts::date, 'YYYYMMDD')::int AS fecha_id,
                snapshot_ts::timestamp AS snapshot_ts,
                total_market_cap_usd, total_volume_usd,
                btc_dominance, eth_dominance,
                active_cryptocurrencies, markets,
                market_cap_change_pct_24h,
                now()                  AS _processed_at,
                'bronze.global_market' AS _source_table
            FROM bronze.global_market
            ORDER BY snapshot_ts, ingested_at DESC
        """)
        print("gold.fact_global_market reconstruida (1 fila por SNAPSHOT)")

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

    # ============================================================
    # VERIFICAR INTEGRIDAD REFERENCIAL + RESUMEN
    # ============================================================
    # Integridad = toda FK de la fact apunta a una PK existente en la dim.
    # Se mide con LEFT JOIN + WHERE d.crypto_id IS NULL (huerfanos).
    # Nota: silver.global_market NO se lista: por diseno el dato macro
    # salta Silver (queda en bronze.global_market).

    # ============================================================
    # VISTAS SEMANTICAS - la "API publica" de Gold
    # ============================================================
    # El dashboard y el modelo NO consultan las tablas fisicas: consumen
    # estas vistas. Asi los KPIs se definen UNA vez, en SQL, dentro del
    # warehouse (capa semantica) -- no en cada pagina de la BI tool.
    # Se recrean en cada corrida porque los DROP ... CASCADE de arriba
    # las tiran junto con las tablas.
    @task
    def drop_views():
        """Baja la capa semantica ANTES de reconstruir las tablas.

        Sin esto, las 5 construcciones paralelas se deadlockean entre si: cada
        una hace DROP TABLE ... CASCADE, y desde que las vistas cruzan la fact
        con las dimensiones, el CASCADE de una task alcanza objetos que otra
        esta tirando al mismo tiempo.

        Se desarma de arriba hacia abajo (vistas -> tablas) y se arma de abajo
        hacia arriba (tablas -> vistas).
        """
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            vistas = [r[0] for r in conn.exec_driver_sql(
                "SELECT viewname FROM pg_views WHERE schemaname = 'gold'"
            )]
            for v in vistas:
                conn.exec_driver_sql(f"DROP VIEW IF EXISTS gold.{v} CASCADE")
        print(f"capa semantica desarmada: {len(vistas)} vistas")

    @task(outlets=[GOLD_STAR])
    def build_views():
        """La capa semantica: que SIGNIFICA cada metrica, definido una sola vez.

        =====================================================================
        LAS TRES CAPAS, Y POR QUE NO SON LA MISMA
        =====================================================================
        Es facil meter todo en un balde llamado "vistas". Son tres cosas:

        1. MODELO DIMENSIONAL  -- gold.dim_* + gold.fact_*
           Como se representa el negocio: grano, claves, atributos. Responde
           "de que se puede hablar". Cambia poco y cuesta cambiarlo.

        2. CAPA SEMANTICA      -- gold.v_*  (esta task)
           Que SIGNIFICA cada metrica. "Dominancia BTC" se define aca, una vez,
           y todos los consumidores leen la misma definicion. Son metricas
           GOBERNADAS: no dependen de quien pregunta ni de cuando.

        3. CONSUMO             -- SQL en la pagina / el notebook
           La pregunta puntual de hoy: "correlacion entre ESTAS seis criptas
           que acabo de elegir". Es ad-hoc, parametrizada, y vive con quien
           pregunta.

        La linea entre (2) y (3) es la que mas se borronea, y hay una prueba
        simple: **si la consulta depende de lo que el usuario eligio, no es
        capa semantica.** Una matriz de correlacion de 2.601 pares
        precalculados no define ninguna metrica -- materializa la estructura de
        datos de un heatmap. Eso va en (3).

        El costo de confundirlas es real: todo lo que entra en (2) se vuelve
        contrato publico, y cada consumidor nuevo que lo usa lo vuelve mas
        caro de cambiar. Una capa semantica que acumula las queries de cada
        pantalla deja de ser una capa semantica y pasa a ser una carpeta.
        """
        _run_ddl("""
            -- El "ahora" de cada cripto: la ultima foto disponible.
            CREATE OR REPLACE VIEW gold.v_ultimo_snapshot AS
            SELECT DISTINCT ON (f.crypto_id)
                   f.*,
                   d.symbol, d.name, d.categoria
            FROM gold.fact_crypto_markets f
            JOIN gold.dim_crypto d USING (crypto_id)
            ORDER BY f.crypto_id, f.snapshot_ts DESC;
        """)
        _run_ddl("""
            -- 1 fila = 1 cripto x 1 dia (el CIERRE: ultimo snapshot del dia)
            -- + retorno diario via LAG(). Base de toda serie temporal honesta.
            CREATE OR REPLACE VIEW gold.v_series_diaria AS
            WITH cierre AS (
                SELECT DISTINCT ON (crypto_id, snapshot_ts::date)
                       crypto_id,
                       snapshot_ts::date AS fecha,
                       snapshot_ts       AS snapshot_cierre,
                       current_price, market_cap, total_volume, market_cap_rank
                FROM gold.fact_crypto_markets
                ORDER BY crypto_id, snapshot_ts::date, snapshot_ts DESC
            )
            SELECT c.*,
                   d.symbol, d.name, d.categoria,
                   t.dia_semana, t.es_fin_de_semana,
                   (c.current_price
                    / NULLIF(LAG(c.current_price) OVER w, 0) - 1) * 100
                       AS retorno_diario_pct
            FROM cierre c
            JOIN gold.dim_crypto d USING (crypto_id)
            -- El star completo: la fact al centro, las DOS dimensiones colgando.
            JOIN gold.dim_tiempo t ON t.fecha = c.fecha
            WINDOW w AS (PARTITION BY c.crypto_id ORDER BY c.fecha);
        """)
        if _tabla_existe("gold.fact_global_market"):
            _run_ddl("""
                -- KPIs del mercado completo, con el delta vs el dia anterior
                -- YA calculado en SQL (el dashboard solo los muestra).
                CREATE OR REPLACE VIEW gold.v_kpis_mercado AS
                -- La fact ahora guarda 1 fila por SNAPSHOT, pero estos KPIs
                -- comparan contra el dia anterior. Por eso la vista colapsa a
                -- diario ella misma (cierre = ultimo snapshot del dia) antes
                -- del LAG: el delta sigue significando "vs ayer" y no "vs hace
                -- 15 minutos". La salida de la vista no cambio.
                WITH cierre_diario AS (
                    SELECT DISTINCT ON (fecha_id) *
                    FROM gold.fact_global_market
                    ORDER BY fecha_id, snapshot_ts DESC
                ),
                serie AS (
                    SELECT *,
                           LAG(total_market_cap_usd) OVER w AS mcap_prev,
                           LAG(total_volume_usd)     OVER w AS vol_prev,
                           LAG(btc_dominance)        OVER w AS btc_dom_prev,
                           LAG(eth_dominance)        OVER w AS eth_dom_prev
                    FROM cierre_diario
                    WINDOW w AS (ORDER BY fecha_id)
                )
                SELECT fecha_id, snapshot_ts,
                       total_market_cap_usd,
                       (total_market_cap_usd / NULLIF(mcap_prev, 0) - 1) * 100
                           AS mcap_delta_pct,
                       total_volume_usd,
                       (total_volume_usd / NULLIF(vol_prev, 0) - 1) * 100
                           AS vol_delta_pct,
                       btc_dominance,
                       btc_dominance - btc_dom_prev AS btc_dom_delta,
                       eth_dominance,
                       eth_dominance - eth_dom_prev AS eth_dom_delta,
                       active_cryptocurrencies, markets,
                       -- "cuantos activos suben" es un KPI de mercado y por lo
                       -- tanto se define ACA, no en la pagina. Ojo con el
                       -- significado: usa el campo de 24h que reporta la API
                       -- (ventana movil). NO es lo mismo que el `suben` de
                       -- v_amplitud_mercado, que compara cierre contra cierre
                       -- del dia anterior. Dos preguntas parecidas y distintas:
                       -- por eso llevan nombres distintos.
                       (SELECT count(*) FROM gold.v_ultimo_snapshot
                         WHERE price_change_percentage_24h > 0)  AS activos_en_alza_24h,
                       (SELECT count(*) FROM gold.v_ultimo_snapshot)
                                                                 AS activos_totales
                FROM serie
                ORDER BY fecha_id DESC
                LIMIT 1;
            """)
        _run_ddl("""
            -- VELA DIARIA (OHLC): apertura / maximo / minimo / cierre por dia.
            -- Se puede construir SOLO porque la fact guarda snapshot_ts: la
            -- vela sale de agrupar los ~96 snapshots del dia. Si la fact
            -- guardara una fila por dia, no habria ni maximo ni minimo.
            -- Esta vista es el STAR SCHEMA en uso: la fact en el centro, y las
            -- DOS dimensiones colgando por sus claves (crypto_id y fecha_id).
            -- Antes derivaba la fecha con `snapshot_ts::date` y dejaba
            -- `dim_tiempo` sin consumir: la FK existia y nadie la seguia.
            CREATE OR REPLACE VIEW gold.v_ohlc_diario AS
            SELECT
                f.crypto_id,
                d.symbol, d.name, d.categoria,
                t.fecha,
                t.dia_semana, t.es_fin_de_semana,
                count(*)                                                   AS snapshots,
                (array_agg(f.current_price ORDER BY f.snapshot_ts))[1]     AS apertura,
                max(f.current_price)                                       AS maximo,
                min(f.current_price)                                       AS minimo,
                (array_agg(f.current_price ORDER BY f.snapshot_ts DESC))[1] AS cierre,
                (array_agg(f.total_volume ORDER BY f.snapshot_ts DESC))[1]  AS volumen,
                -- Rango intradia: proxy de volatilidad que YA sirve con 1 solo
                -- dia de historia (no necesita serie, sale de la propia vela).
                (max(f.current_price) - min(f.current_price))
                    / NULLIF((array_agg(f.current_price ORDER BY f.snapshot_ts DESC))[1], 0) * 100
                                                                           AS rango_pct
            FROM gold.fact_crypto_markets f
            JOIN gold.dim_crypto  d USING (crypto_id)
            JOIN gold.dim_tiempo  t USING (fecha_id)
            GROUP BY f.crypto_id, d.symbol, d.name, d.categoria,
                     t.fecha, t.dia_semana, t.es_fin_de_semana;
        """)
        _run_ddl("""
            -- METRICAS DE RIESGO por cripto, sobre la serie de cierres diarios.
            -- Todo en SQL con window functions: stddev (volatilidad), max()
            -- acumulado (drawdown) y first/last (retorno del periodo).
            CREATE OR REPLACE VIEW gold.v_metricas_riesgo AS
            WITH serie AS (
                SELECT crypto_id, symbol, name, fecha, cierre,
                       (cierre / NULLIF(LAG(cierre) OVER w, 0) - 1) * 100 AS ret_pct,
                       max(cierre) OVER (PARTITION BY crypto_id
                                         ORDER BY fecha
                                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                                                                          AS pico,
                       rango_pct
                FROM gold.v_ohlc_diario
                WINDOW w AS (PARTITION BY crypto_id ORDER BY fecha)
            )
            SELECT
                crypto_id, symbol, name,
                count(*)                                   AS dias,
                -- Volatilidad: desvio de los retornos diarios. Con menos de
                -- 3 dias devuelve NULL: el dashboard muestra "acumulando".
                stddev_samp(ret_pct)                       AS volatilidad_pct,
                avg(rango_pct)                             AS rango_medio_pct,
                ((array_agg(cierre ORDER BY fecha DESC))[1]
                 / NULLIF((array_agg(cierre ORDER BY fecha))[1], 0) - 1) * 100
                                                           AS retorno_periodo_pct,
                -- Drawdown: peor caida desde un maximo previo (riesgo real
                -- que el retorno promedio esconde).
                min((cierre / NULLIF(pico, 0) - 1) * 100)   AS max_drawdown_pct,
                (array_agg(cierre ORDER BY fecha DESC))[1]  AS ultimo_cierre
            FROM serie
            GROUP BY crypto_id, symbol, name;
        """)
        _run_ddl("""
            -- AMPLITUD DE MERCADO (breadth): cuantos activos suben y cuantos
            -- bajan cada dia. Un mercado que sube con pocos activos es fragil.
            CREATE OR REPLACE VIEW gold.v_amplitud_mercado AS
            WITH ret AS (
                SELECT fecha,
                       (cierre / NULLIF(LAG(cierre) OVER (PARTITION BY crypto_id
                                                          ORDER BY fecha), 0) - 1) AS r
                FROM gold.v_ohlc_diario
            )
            SELECT fecha,
                   count(*) FILTER (WHERE r > 0)  AS suben,
                   count(*) FILTER (WHERE r < 0)  AS bajan,
                   count(*) FILTER (WHERE r = 0)  AS planos,
                   round((count(*) FILTER (WHERE r > 0))::numeric
                         / NULLIF(count(r), 0) * 100, 1) AS pct_alza
            FROM ret
            WHERE r IS NOT NULL
            GROUP BY fecha
            ORDER BY fecha;
        """)
        _run_ddl("""
            -- SERIE MACRO COMPLETA, a nivel snapshot (cada 15 minutos).
            -- v_kpis_mercado da la FOTO (una fila, la ultima); esta da la
            -- PELICULA. Son preguntas distintas y por eso son vistas distintas:
            -- una tarjeta de KPI no necesita 211 filas, y un sparkline no
            -- necesita deltas.
            CREATE OR REPLACE VIEW gold.v_global_serie AS
            SELECT
                snapshot_ts, fecha_id,
                total_market_cap_usd, total_volume_usd,
                btc_dominance, eth_dominance,
                100 - btc_dominance - eth_dominance AS resto_dominance,
                active_cryptocurrencies, markets
            FROM gold.fact_global_market
            ORDER BY snapshot_ts;
        """)
        _run_ddl("""
            -- INTRADIA: 1 fila = 1 cripto x 1 snapshot.
            -- Es la vista que le devuelve al dashboard la resolucion que el
            -- pipeline ya venia recolectando. Con 3 dias de historia, un
            -- analisis diario tiene 3 puntos por cripto; este tiene ~200.
            --
            -- El retorno se calcula ACA, en SQL, y no en la pagina: si cada
            -- consumidor lo calculara por su cuenta, tendriamos varias
            -- definiciones de "retorno" conviviendo (que es justo lo que pasaba
            -- con "activos en alza", que significaba dos cosas distintas segun
            -- la pagina).
            CREATE OR REPLACE VIEW gold.v_intradia AS
            SELECT
                f.crypto_id, d.symbol, d.name, d.categoria,
                f.snapshot_ts,
                f.current_price, f.market_cap, f.total_volume, f.market_cap_rank,
                f.spread_pct, f.ath_distance_pct,
                (f.current_price / NULLIF(LAG(f.current_price) OVER w, 0) - 1) * 100
                    AS retorno_pct,
                LAG(f.market_cap_rank) OVER w - f.market_cap_rank
                    AS rank_delta
            FROM gold.fact_crypto_markets f
            JOIN gold.dim_crypto d USING (crypto_id)
            WINDOW w AS (PARTITION BY f.crypto_id ORDER BY f.snapshot_ts);
        """)
        _run_ddl("""
            -- EL STAR EN ACCION: cortar por un ATRIBUTO de la dimension.
            -- Para esto existe una dimension. No para traer `symbol` (eso es un
            -- lookup): para que puedas preguntar "¿rinde distinto el fin de
            -- semana que un dia habil?" sin que esa categoria este en la fact.
            --
            -- El atributo vive en dim_tiempo, la medida en la fact, y el JOIN
            -- por fecha_id los une. Si manana queres cortar por trimestre o por
            -- dia de la semana, la fact NO se toca: ya esta todo en la dimension.
            CREATE OR REPLACE VIEW gold.v_estacionalidad AS
            SELECT
                t.es_fin_de_semana,
                t.dia_semana,
                count(DISTINCT t.fecha)                        AS dias,
                count(*)                                       AS observaciones,
                round(avg(o.rango_pct)::numeric, 3)            AS rango_medio_pct,
                round(avg((o.cierre / NULLIF(o.apertura, 0) - 1) * 100)::numeric, 3)
                                                               AS retorno_medio_pct,
                round(stddev_samp((o.cierre / NULLIF(o.apertura, 0) - 1) * 100)::numeric, 3)
                                                               AS desvio_pct
            FROM gold.v_ohlc_diario o
            JOIN gold.dim_tiempo   t USING (fecha)
            GROUP BY t.es_fin_de_semana, t.dia_semana
            ORDER BY t.es_fin_de_semana, t.dia_semana;
        """)
        _run_ddl("""
            -- LA MISMA PREGUNTA, POR LA OTRA DIMENSION.
            -- v_estacionalidad corta por un atributo de dim_tiempo (cuando);
            -- esta corta por uno de dim_crypto (quien). Mismas metricas, para
            -- que las dos se puedan leer una al lado de la otra.
            --
            -- Y agrega una que la temporal no puede dar: cuanto PESA cada
            -- familia en el mercado. Son dos cosas distintas -- las
            -- stablecoins son muchas monedas y casi nada de capitalizacion.
            -- (Ojo: nada de escribir el signo de porcentaje en estos
            --  comentarios; psycopg2 lo lee como placeholder de parametro.)
            CREATE OR REPLACE VIEW gold.v_por_categoria AS
            WITH mcap AS (
                -- El peso se mide sobre la foto mas reciente, no sobre el
                -- promedio historico: "cuanto pesa hoy", no "cuanto peso".
                SELECT categoria,
                       sum(market_cap)                                    AS mcap,
                       sum(market_cap) / NULLIF(sum(sum(market_cap)) OVER (), 0) * 100
                                                                          AS part_pct
                FROM gold.v_ultimo_snapshot
                GROUP BY categoria
            )
            SELECT
                o.categoria,
                count(DISTINCT o.crypto_id)                    AS criptos,
                count(*)                                       AS observaciones,
                round(avg(o.rango_pct)::numeric, 3)            AS rango_medio_pct,
                round(avg((o.cierre / NULLIF(o.apertura, 0) - 1) * 100)::numeric, 3)
                                                               AS retorno_medio_pct,
                round(stddev_samp((o.cierre / NULLIF(o.apertura, 0) - 1) * 100)::numeric, 3)
                                                               AS desvio_pct,
                round(max(m.part_pct)::numeric, 2)             AS participacion_mcap_pct
            FROM gold.v_ohlc_diario o
            LEFT JOIN mcap m USING (categoria)
            WHERE o.categoria IS NOT NULL
            GROUP BY o.categoria
            ORDER BY rango_medio_pct DESC;
        """)
        # NOTA: aca vivia `gold.v_correlacion_intradia`, y se retiro a
        # proposito. Una matriz de correlacion depende de que activos elige
        # quien mira: es una consulta AD-HOC, no una metrica gobernada. Vive en
        # la pagina que la pregunta (5_Gold_Analisis.py), como SQL parametrizado
        # -- sigue calculandose en Postgres con corr(), pero del lado del
        # consumidor. Ver la explicacion de las tres capas en el docstring.
        _run_ddl("""
            -- CONCENTRACION del mercado (1 fila).
            -- HHI = suma de los cuadrados de las participaciones porcentuales.
            -- (Ojo: nada de escribir el signo de porcentaje en estos comentarios.
            --  _run_ddl usa exec_driver_sql, que manda el SQL crudo a psycopg2, y
            --  psycopg2 lo lee como placeholder de parametro -> TypeError.)
            -- Es el
            -- indice que usan los reguladores de competencia: >2500 se
            -- considera un mercado concentrado. Dice algo que el market cap
            -- total no dice -- si el mercado ES btc o es un mercado.
            --
            -- Tambien estaba en pandas en la pagina de Analisis.
            CREATE OR REPLACE VIEW gold.v_concentracion AS
            WITH ult AS (
                SELECT
                    symbol,
                    market_cap::numeric
                        / NULLIF(SUM(market_cap) OVER (), 0) * 100 AS share_pct,
                    ROW_NUMBER() OVER (ORDER BY market_cap DESC)   AS pos
                FROM gold.v_ultimo_snapshot
                WHERE market_cap IS NOT NULL AND market_cap > 0
            )
            SELECT
                round(SUM(share_pct * share_pct))                  AS hhi,
                round(SUM(share_pct) FILTER (WHERE pos <= 5), 1)   AS top5_pct,
                round(SUM(share_pct) FILTER (WHERE pos <= 10), 1)  AS top10_pct,
                count(*)                                           AS activos
            FROM ult;
        """)
        print("capa semantica lista (gold.v_*): ultimo snapshot, serie diaria,")
        print("   KPIs, OHLC, riesgo, amplitud, serie macro, intradia,")
        print("   estacionalidad, concentracion")

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
    # FLUJO: bajar las vistas -> 5 construcciones en paralelo -> rehacer
    #        las vistas -> verificacion final
    # ============================================================
    # Las 5 construcciones corren EN PARALELO y cada una empieza con un
    # DROP TABLE ... CASCADE. Eso funcionaba mientras ninguna vista cruzaba
    # dos tablas. Cuando la capa semantica empezo a JOINear la fact con las
    # dimensiones, dos tasks paralelas pasaron a pelear por los mismos objetos
    # -- el CASCADE de dim_tiempo intenta tirar una vista que depende de la
    # fact, justo cuando otra task esta tirando la fact. Postgres lo resuelve
    # como corresponde: DEADLOCK, y una de las dos muere.
    #
    # La solucion no es serializar las construcciones (perderiamos el
    # paralelismo por un problema que no es de las tablas): es sacar la capa
    # dependiente ANTES, de una sola vez. Con las vistas ya abajo, los CASCADE
    # de cada build_* no tienen nada que arrastrar y dejan de cruzarse.
    #
    # Es el orden de siempre para un full-refresh con capa semantica encima:
    # se desarma de arriba hacia abajo y se arma de abajo hacia arriba.
    #
    # DONDE se emite cada asset importa: build_abt declara GOLD_ABT y
    # build_views declara GOLD_STAR, o sea en la tarea que ESCRIBE el dato, no
    # al final del DAG. Lo que se publica es "el dato existe", no "el DAG
    # termino". Por eso crypto_ml puede arrancar apenas la ABT esta lista,
    # sin esperar a verify_integrity().
    dim_c = build_dim_crypto()
    dim_t = build_dim_tiempo()
    fact = build_fact()
    fact_g = build_fact_global()
    abt = build_abt()

    drop_views() >> [dim_c, dim_t, fact, fact_g, abt] >> build_views() >> verify_integrity()


# Instanciacion: obligatoria para que Airflow descubra el DAG.
crypto_gold()
