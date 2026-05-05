"""
DAG: crypto_gold
Clase 05 - Transformacion Silver a Gold (Star Schema enriquecido + ABT)

Pipeline: silver.crypto_markets + silver.global_market →
  - dim_crypto (9 cols: id, symbol, name, supply, ATH/ATL)
  - dim_tiempo (7 cols: fecha, anio, mes, trimestre, dia, fin_de_semana)
  - fact_crypto_markets (17 metricas por cripto por fecha)
  - fact_global_market (datos del mercado total por fecha)
  - gold_abt_crypto (wide table con features derivadas para ML)
"""

# =============================================================================
# CAPA GOLD EN LA ARQUITECTURA MEDALLION
# =============================================================================
#
# La capa Gold es la ULTIMA capa de la Arquitectura Medallion:
#
#   Bronze (crudo) --> Silver (limpio) --> *** Gold (analítico) ***
#
# Es la capa "lista para consumir". Los datos aqui estan:
#   - Modelados: organizados en un esquema optimizado para consultas (Star Schema)
#   - Enriquecidos: con atributos derivados, categorias, y metricas calculadas
#   - Listos para dos audiencias:
#       1. Analistas de BI/Negocio: usan el Star Schema para dashboards y reportes
#       2. Data Scientists: usan la ABT (Analytical Base Table) para modelos de ML
#
# Gold NUNCA lee de Bronze directamente. Siempre lee de Silver.
# Esto garantiza que trabajamos con datos ya validados y limpios.
#
# =============================================================================
# STAR SCHEMA: CONCEPTOS FUNDAMENTALES
# =============================================================================
#
# El Star Schema (Esquema Estrella) es un modelo de datos para analytics.
# Se llama "estrella" porque visualmente tiene una tabla central (fact)
# rodeada de tablas satelite (dimensiones):
#
#                    dim_crypto
#                        |
#   dim_tiempo --- fact_crypto_markets
#
# TABLAS DE DIMENSIONES (dim_*):
#   - Describen las ENTIDADES del negocio (el "quien", "que", "cuando")
#   - Tienen pocas filas y cambian lentamente (o nunca)
#   - Contienen atributos descriptivos (nombre, categoria, fecha)
#   - Ejemplo: dim_crypto tiene 50 filas (una por criptomoneda)
#
# TABLAS DE HECHOS (fact_*):
#   - Contienen las METRICAS NUMERICAS del negocio (el "cuanto")
#   - Tienen MUCHAS filas (una por evento/medicion)
#   - Contienen Foreign Keys (FKs) que apuntan a las dimensiones
#   - Ejemplo: fact_crypto_markets tiene 50 criptos x N dias = muchas filas
#
# FOREIGN KEYS (FKs - Claves Foraneas):
#   - Son columnas en la fact table que "apuntan" a la Primary Key (PK)
#     de una dimension.
#   - Permiten hacer JOIN entre tablas para enriquecer la consulta.
#   - Ejemplo: fact.crypto_id --> dim_crypto.crypto_id
#              fact.fecha_id  --> dim_tiempo.fecha_id
#
# Una consulta tipica de Star Schema:
#   SELECT d.name, t.dia_semana, f.current_price, f.market_cap
#   FROM gold.fact_crypto_markets f
#   JOIN gold.dim_crypto d ON f.crypto_id = d.crypto_id
#   JOIN gold.dim_tiempo t ON f.fecha_id = t.fecha_id
#   WHERE t.trimestre = 1 AND d.symbol = 'BTC'
#
# =============================================================================
# FLUJO DE TAREAS EN ESTE DAG
# =============================================================================
#
#                        /--> build_dim_crypto ------\
#   read_silver() ------+--> build_dim_tiempo -------\
#                        +--> build_fact -------------+--> verify_integrity()
#   read_silver_global()-+--> build_fact_global ------/
#                        \--> build_abt ------------/
#
# Son 5 tareas de construccion ejecutandose EN PARALELO, todas convergiendo
# en verify_integrity() que valida la integridad referencial del resultado.
# =============================================================================

from airflow.decorators import dag, task
from datetime import datetime
import math
import os


# Cadena de conexion a PostgreSQL (mismo patron que Bronze y Silver)
DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


# =============================================================================
# FUNCION AUXILIAR: _clean_records
# =============================================================================
# Esta funcion es CRITICA para que los datos puedan viajar entre tareas
# de Airflow via XCom. XCom serializa los datos a JSON, y JSON no soporta:
#   - NaN (Not a Number): valor especial de float que indica "sin dato"
#   - inf / -inf: infinito positivo/negativo (ej: division por cero)
#   - pd.Timestamp: tipo de dato de Pandas para fechas (no es JSON nativo)
#   - datetime/date de Python: tampoco son JSON nativos
#   - pd.NaT: "Not a Time", el equivalente de NaN para fechas en Pandas
#
# Sin esta limpieza, XCom lanza un error de serializacion y el DAG falla.
# La solucion es convertir todo a tipos JSON-compatibles:
#   - NaN/inf -> None (que en JSON es null)
#   - Timestamp/datetime -> string ISO 8601 (ej: "2026-03-02T15:30:00")
#   - NaT -> None
# =============================================================================
def _clean_records(records):
    """Limpiar NaN/inf/Timestamp/datetime de records para que XCom (JSON) no explote."""
    import pandas as pd
    from datetime import date, datetime as dt
    for row in records:
        for k, v in row.items():
            # Caso 1: float que es NaN o infinito -> convertir a None (null en JSON)
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
            # Caso 2: pd.Timestamp (tipo nativo de Pandas) -> string ISO
            elif isinstance(v, (pd.Timestamp,)):
                row[k] = v.isoformat() if pd.notna(v) else None
            # Caso 3: datetime o date de Python -> string ISO
            elif isinstance(v, (dt, date)):
                row[k] = v.isoformat()
            # Caso 4: pd.NaT (Not a Time) -> None
            elif v is pd.NaT:
                row[k] = None
    return records


# =============================================================================
# DEFINICION DEL DAG
# =============================================================================
@dag(
    dag_id="crypto_gold",
    start_date=datetime(2024, 1, 1),
    # schedule=None: este DAG se ejecuta manualmente.
    # En produccion podria ser triggerado automaticamente por el DAG de Silver
    # usando TriggerDagRunOperator, o tener un schedule como "@daily".
    schedule="@daily",
    catchup=False,
    tags=["prod", "gold", "crypto"],
    doc_md="""
    ## Crypto Gold - Star Schema enriquecido + ABT
    Lee datos limpios de Silver y reconstruye:
    - **BI**: dim_crypto, dim_tiempo, fact_crypto_markets, fact_global_market
    - **ML**: gold_abt_crypto (Wide Table con 20+ features)

    El Star Schema tiene 17 metricas en la fact table (vs 5 del original)
    y una nueva tabla de hechos del mercado global.
    """,
)
def crypto_gold():

    # ============================================================
    # TAREA 1a: LEER DATOS DE SILVER (crypto_markets)
    # ============================================================
    @task
    def read_silver():
        """Leer todos los datos de silver.crypto_markets."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        # Leemos TODOS los registros de Silver (todos los snapshots acumulados).
        # Gold siempre lee de Silver (nunca de Bronze) - principio Medallion.
        df = pd.read_sql("SELECT * FROM silver.crypto_markets", engine)

        # Contamos snapshots unicos para saber cuantos "cortes temporales"
        # tenemos. Con mas snapshots, las features temporales de la ABT
        # (avg_price, price_std) son mas significativas estadisticamente.
        snapshots = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 1
        print(f"Leidos {len(df)} registros de Silver ({snapshots} snapshots, {df['id'].nunique()} criptos, {df.shape[1]} cols)")
        return _clean_records(df.to_dict(orient="records"))

    # ============================================================
    # TAREA 1b: LEER DATOS DE SILVER (global_market)
    # ============================================================
    # Esta es una fuente de datos NUEVA respecto al DAG simplificado.
    # silver.global_market contiene datos del mercado cripto en su totalidad:
    # market cap total, dominancia de BTC/ETH, cantidad de exchanges, etc.
    # Estos datos permiten CONTEXTUALIZAR cada criptomoneda individual
    # dentro del mercado global (ej: "Bitcoin representa el 52% del mercado total").
    @task
    def read_silver_global():
        """Leer silver.global_market."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        try:
            df = pd.read_sql("SELECT * FROM silver.global_market", engine)
            print(f"Leidos {len(df)} registros de silver.global_market")
            return _clean_records(df.to_dict(orient="records"))
        except Exception as e:
            # Si la tabla no existe (porque el DAG de ingesta global no se corrio),
            # retornamos lista vacia. Las tareas downstream manejan este caso.
            print(f"silver.global_market no disponible: {e}")
            return []

    # ============================================================
    # TAREA 2: DIMENSION DE CRIPTOMONEDAS (ENRIQUECIDA - 9 columnas)
    # ============================================================
    # A diferencia de la version simplificada (3 columnas: id, symbol, name),
    # esta dimension tiene 9 COLUMNAS con datos SEMI-ESTATICOS:
    #
    # 1. crypto_id   - Identificador unico (ej: "bitcoin", "ethereum")
    # 2. symbol      - Ticker corto (ej: "BTC", "ETH")
    # 3. name        - Nombre completo (ej: "Bitcoin", "Ethereum")
    # 4. max_supply  - Oferta maxima posible (ej: Bitcoin = 21 millones)
    # 5. total_supply- Oferta total actual (incluye monedas no circulantes)
    # 6. ath         - All-Time High: precio maximo historico en USD
    # 7. ath_date    - Fecha del ATH (cuando alcanzo su maximo)
    # 8. atl         - All-Time Low: precio minimo historico en USD
    # 9. atl_date    - Fecha del ATL (cuando alcanzo su minimo)
    #
    # Estos datos son "semi-estaticos": cambian muy pocas veces.
    # max_supply de Bitcoin NUNCA cambia (siempre 21M), pero ath/atl
    # cambian cuando se rompe un record historico (evento poco frecuente).
    # Por eso usamos .groupby("id").last() - tomamos el snapshot mas reciente
    # que tendra los valores mas actualizados de ATH/ATL.
    # ============================================================
    @task
    def build_dim_crypto(records: list):
        """Crear dimension de criptomonedas con datos semi-estaticos."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)

        # Tomar el snapshot mas reciente por cripto.
        # sort_values("ingested_at") ordena cronologicamente,
        # .groupby("id").last() toma la ultima fila de cada grupo.
        # Asi obtenemos los datos mas actualizados de cada cripto.
        df = df.sort_values("ingested_at").groupby("id").last().reset_index()

        # Las 9 columnas que forman la dimension enriquecida
        dim_cols = ["id", "symbol", "name", "max_supply", "total_supply",
                     "ath", "ath_date", "atl", "atl_date"]
        # Filtramos solo las columnas que existen en el DataFrame
        # (por si alguna no esta disponible en los datos de Silver)
        dim = df[[c for c in dim_cols if c in df.columns]].copy()

        # Renombramos "id" -> "crypto_id" para que sea una PK descriptiva
        # y coincida con la FK en la fact table
        dim = dim.rename(columns={"id": "crypto_id"})

        engine = sqlalchemy.create_engine(DB_URI)
        dim.to_sql("dim_crypto", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.dim_crypto: {len(dim)} filas, {dim.shape[1]} columnas")

    # ============================================================
    # TAREA 3: DIMENSION TEMPORAL (7 columnas)
    # ============================================================
    # La dimension de tiempo tiene 7 columnas derivadas de cada fecha:
    #
    # 1. fecha         - La fecha como datetime (ej: 2026-03-02)
    # 2. fecha_id      - Entero YYYYMMDD (ej: 20260302) - es la PK
    # 3. anio          - Anio (ej: 2026)
    # 4. mes           - Mes numerico (ej: 3)
    # 5. trimestre     - Trimestre (1-4)
    # 6. dia_semana    - Nombre del dia (ej: "Monday")
    # 7. es_fin_de_semana - Boolean: True si es sabado o domingo
    #
    # ¿Por que fecha_id es un ENTERO con formato YYYYMMDD?
    # - Es mas eficiente para JOINs y filtros que un string o datetime
    # - Es legible por humanos (20260302 = 2 de marzo de 2026)
    # - Es un patron estandar en Data Warehousing (surrogate key temporal)
    #
    # ¿Por que tener una dimension de tiempo separada?
    # Porque permite hacer consultas de negocio sin funciones de fecha:
    #   - "Ventas por trimestre" -> WHERE t.trimestre = 1
    #   - "Comportamiento en fines de semana" -> WHERE t.es_fin_de_semana = true
    #   - "Comparacion anio a anio" -> GROUP BY t.anio
    # Sin esta dimension, cada query tendria que usar EXTRACT(), DATE_PART(), etc.
    # ============================================================
    @task
    def build_dim_tiempo(records: list):
        """Crear dimension temporal desde fechas reales en los datos."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)

        # .dt.normalize() trunca la hora (deja solo la fecha: 2026-03-02 00:00:00)
        # Esto agrupa todos los snapshots del mismo dia en una sola fecha.
        df["_fecha"] = pd.to_datetime(df["ingested_at"]).dt.normalize()
        fechas_unicas = sorted(df["_fecha"].unique())

        # Construimos la dimension con una fila por cada dia que tiene datos
        dim = pd.DataFrame({"fecha": fechas_unicas})
        dim["fecha"] = pd.to_datetime(dim["fecha"])

        # fecha_id: PK en formato YYYYMMDD como entero
        # strftime("%Y%m%d") convierte datetime -> string "20260302"
        # .astype(int) convierte string -> entero 20260302
        dim["fecha_id"] = dim["fecha"].dt.strftime("%Y%m%d").astype(int)

        # Atributos derivados: extraemos informacion util de cada fecha
        dim["anio"] = dim["fecha"].dt.year                # Ej: 2026
        dim["mes"] = dim["fecha"].dt.month                # Ej: 3 (marzo)
        dim["trimestre"] = dim["fecha"].dt.quarter        # Ej: 1 (Q1)
        dim["dia_semana"] = dim["fecha"].dt.day_name()    # Ej: "Monday"
        dim["es_fin_de_semana"] = dim["fecha"].dt.dayofweek >= 5  # 5=Sab, 6=Dom

        engine = sqlalchemy.create_engine(DB_URI)
        dim.to_sql("dim_tiempo", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.dim_tiempo: {len(dim)} filas (dias de datos)")

    # ============================================================
    # TAREA 4: FACT TABLE - CRYPTO MARKETS (17 metricas!)
    # ============================================================
    # Esta es la tabla de hechos PRINCIPAL del Star Schema.
    # A diferencia de la version simplificada (5 metricas), esta version
    # tiene 17 METRICAS agrupadas por categoria:
    #
    # FOREIGN KEYS (2):
    #   - crypto_id: FK a dim_crypto (que cripto es)
    #   - fecha_id:  FK a dim_tiempo (que dia es)
    #
    # PRECIOS (4 metricas):
    #   - current_price:   precio actual en USD
    #   - high_24h:        precio maximo en las ultimas 24 horas
    #   - low_24h:         precio minimo en las ultimas 24 horas
    #   - price_change_24h: cambio absoluto de precio en 24h (en USD)
    #
    # SPREADS (2 metricas - calculadas en Silver):
    #   - spread_24h:  diferencia high_24h - low_24h (rango de precio)
    #   - spread_pct:  spread como % del precio (volatilidad intradía)
    #
    # CAMBIOS PORCENTUALES (2 metricas):
    #   - price_change_percentage_24h:      cambio % del precio en 24h
    #   - market_cap_change_percentage_24h: cambio % del market cap en 24h
    #
    # MARKET CAP Y VOLUMEN (3 metricas):
    #   - market_cap:               capitalizacion de mercado (precio x supply)
    #   - total_volume:             volumen de trading en 24h
    #   - fully_diluted_valuation:  market cap si TODA la supply estuviera circulando
    #
    # SUPPLY (2 metricas):
    #   - circulating_supply: monedas actualmente en circulacion
    #   - supply_ratio:       circulating / total (que % esta circulando)
    #
    # POSICION Y RATIOS (3 metricas):
    #   - market_cap_rank:   posicion en el ranking por market cap (1=Bitcoin)
    #   - fdv_ratio:         market_cap / fully_diluted_valuation
    #   - ath_distance_pct:  distancia porcentual al All-Time High
    #
    # Total: 2 FKs + 17 metricas + 1 metadata (_loaded_at) = 20 columnas
    # ============================================================
    @task
    def build_fact(records: list):
        """Crear tabla de hechos con 17 metricas + FKs."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)

        # Crear las Foreign Keys que conectan la fact con las dimensiones
        df["crypto_id"] = df["id"]  # FK -> dim_crypto.crypto_id
        df["fecha_id"] = pd.to_datetime(df["ingested_at"]).dt.strftime("%Y%m%d").astype(int)  # FK -> dim_tiempo.fecha_id

        # Las 17 metricas organizadas por categoria
        fact_cols = [
            "crypto_id", "fecha_id",
            # Precios (4)
            "current_price", "high_24h", "low_24h", "price_change_24h",
            # Spread derivado en Silver (2)
            "spread_24h", "spread_pct",
            # Cambios porcentuales (2)
            "price_change_percentage_24h", "market_cap_change_percentage_24h",
            # Market cap y volumen (3)
            "market_cap", "total_volume", "fully_diluted_valuation",
            # Supply (2)
            "circulating_supply", "supply_ratio",
            # Posicion y ratios (3)
            "market_cap_rank", "fdv_ratio", "ath_distance_pct",
        ]
        # Solo incluimos columnas que existen en el DataFrame
        # (proteccion contra datos faltantes)
        fact = df[[c for c in fact_cols if c in df.columns]].copy()

        # Metadata de auditoria: cuando se cargo esta tabla
        fact["_loaded_at"] = datetime.now().isoformat()

        engine = sqlalchemy.create_engine(DB_URI)
        fact.to_sql("fact_crypto_markets", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.fact_crypto_markets: {len(fact)} filas, {fact.shape[1]} columnas")

    # ============================================================
    # TAREA 5: FACT TABLE - GLOBAL MARKET (TABLA NUEVA!)
    # ============================================================
    # Esta es una tabla de hechos NUEVA que no existia en la version
    # simplificada. Contiene datos del mercado cripto GLOBAL:
    #
    #   - fecha_id:                 FK a dim_tiempo
    #   - total_market_cap_usd:     market cap total de TODAS las criptos
    #   - total_volume_usd:         volumen total de TODAS las criptos
    #   - btc_dominance:            % del mercado que es Bitcoin (~50-55%)
    #   - eth_dominance:            % del mercado que es Ethereum (~15-18%)
    #   - active_cryptocurrencies:  cuantas criptos existen (~15,000+)
    #   - markets:                  cuantos exchanges hay
    #   - market_cap_change_pct_24h: cambio % del mercado total en 24h
    #
    # ¿Para que sirve esta tabla?
    # Permite CONTEXTUALIZAR los datos de cada criptomoneda individual:
    #   - "Bitcoin bajo 5%, pero el mercado total bajo 7%"
    #     -> Bitcoin se comporto MEJOR que el mercado
    #   - "Ethereum tiene el 16% de dominancia"
    #     -> Podemos comparar con la dominancia calculada en la ABT
    #
    # Es el equivalente a tener el "indice del mercado" (como el S&P500
    # para acciones) para poder comparar contra activos individuales.
    # ============================================================
    @task
    def build_fact_global(global_records: list):
        """Crear tabla de hechos del mercado global."""
        import pandas as pd
        import sqlalchemy

        # Si no hay datos globales (la tabla silver.global_market no existe),
        # simplemente saltamos esta tarea. El DAG sigue funcionando sin ella.
        if not global_records:
            print("Sin datos globales, saltando fact_global_market")
            return

        df = pd.DataFrame(global_records)
        df["fecha_id"] = pd.to_datetime(df["ingested_at"]).dt.strftime("%Y%m%d").astype(int)

        fact_cols = [
            "fecha_id", "total_market_cap_usd", "total_volume_usd",
            "btc_dominance", "eth_dominance",
            "active_cryptocurrencies", "markets",
            "market_cap_change_pct_24h",
        ]
        fact = df[[c for c in fact_cols if c in df.columns]].copy()

        # Si hay multiples snapshots en el mismo dia, nos quedamos con el
        # ULTIMO (el mas reciente). drop_duplicates con keep="last" conserva
        # la ultima fila de cada grupo de fecha_id duplicado.
        fact = fact.sort_values("fecha_id").drop_duplicates(subset=["fecha_id"], keep="last")
        fact["_loaded_at"] = datetime.now().isoformat()

        engine = sqlalchemy.create_engine(DB_URI)
        fact.to_sql("fact_global_market", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.fact_global_market: {len(fact)} filas")

    # ============================================================
    # TAREA 6: ABT (Analytical Base Table - Wide Table para ML)
    # ============================================================
    # La ABT es una tabla "ancha" (wide) donde:
    #   - Cada FILA es una criptomoneda (1 fila por coin)
    #   - Cada COLUMNA es un feature (atributo) para Machine Learning
    #
    # La ABT SIEMPRE agrega por crypto_id (1 fila por moneda), sin importar
    # cuantos snapshots temporales haya. Usa .groupby("id").agg(**dict)
    # con NAMED AGGREGATION para crear columnas con nombres descriptivos.
    #
    # Tipos de features en la ABT:
    #
    # A) FEATURES DIRECTAS (ultimo snapshot):
    #    current_price, market_cap, total_volume, etc.
    #    Usan la agregacion "last" = ultimo valor cronologico.
    #
    # B) FEATURES TEMPORALES (solo con multiples snapshots):
    #    - avg_price:      promedio del precio a lo largo del tiempo
    #    - price_std:      desviacion estandar (variabilidad del precio)
    #    - avg_spread_pct: promedio del spread porcentual
    #    Estas features solo tienen sentido con 2+ snapshots. Con 1 solo
    #    snapshot, avg_price = current_price y price_std = 0 (sin variacion).
    #
    # C) FEATURES DERIVADAS (calculadas):
    #    - price_to_volume_ratio: precio / volumen (indicador de liquidez)
    #    - market_dominance: market_cap / sum(market_cap) * 100
    #    - volatility_category: categorica (baja/media/alta) via pd.cut()
    #    - market_cap_tier: categorica (top_10/top_25/rest) via pd.cut()
    #    - price_tier: categorica (micro/small/medium/large) via pd.cut()
    #
    # D) CONTEXTO GLOBAL (inyectado desde fact_global_market):
    #    - global_total_market_cap: market cap de TODO el mercado
    #    - global_btc_dominance: dominancia de Bitcoin en el mercado
    #    - global_market_change_24h: cambio % del mercado total
    #    - real_market_share: market_cap_individual / market_cap_total * 100
    #      (la "verdadera" participacion de mercado de cada cripto)
    # ============================================================
    @task
    def build_abt(records: list, global_records: list):
        """Crear ABT con features derivadas para ML, incluyendo contexto global."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)
        n_records_per_crypto = len(df) / max(df["id"].nunique(), 1)

        # =============================================================
        # NAMED AGGREGATION con .groupby().agg(**dict)
        # =============================================================
        # La sintaxis de Named Aggregation en Pandas es:
        #   df.groupby("columna").agg(
        #       nombre_resultado=("columna_fuente", "funcion_agregacion")
        #   )
        #
        # El diccionario agg_dict define 18 agregaciones:
        #   - Clave del dict: nombre de la columna resultante
        #   - Valor: tupla (columna_fuente, funcion)
        #
        # Funciones de agregacion usadas:
        #   "last":  ultimo valor (el mas reciente cronologicamente)
        #   "mean":  promedio (para features temporales)
        #   "std":   desviacion estandar (para medir volatilidad)
        #   "count": cantidad de observaciones
        # =============================================================

        # --- Siempre agregar por cripto (1 fila por cripto) ---
        agg_dict = {
            # Features directas: tomamos el ultimo valor de cada metrica
            "current_price": ("current_price", "last"),
            "market_cap": ("market_cap", "last"),
            "total_volume": ("total_volume", "last"),
            "price_change_percentage_24h": ("price_change_percentage_24h", "last"),
            "market_cap_rank": ("market_cap_rank", "last"),
            "high_24h": ("high_24h", "last"),
            "low_24h": ("low_24h", "last"),
            "spread_24h": ("spread_24h", "last"),
            "spread_pct": ("spread_pct", "last"),
            "circulating_supply": ("circulating_supply", "last"),
            "supply_ratio": ("supply_ratio", "last"),
            "ath_distance_pct": ("ath_distance_pct", "last"),
            "atl_distance_pct": ("atl_distance_pct", "last"),
            "fdv_ratio": ("fdv_ratio", "last"),
            # Features TEMPORALES: solo significativas con multiples snapshots
            # Con 1 snapshot: avg_price == current_price, price_std == NaN (-> 0)
            "avg_price": ("current_price", "mean"),       # Promedio historico del precio
            "price_std": ("current_price", "std"),        # Desvio estandar (volatilidad)
            "avg_spread_pct": ("spread_pct", "mean"),     # Promedio del spread %
            "n_snapshots": ("current_price", "count"),    # Cuantas observaciones tenemos
        }
        # Solo usamos columnas que realmente existen en el DataFrame
        # (proteccion contra datos faltantes en Silver)
        valid_aggs = {k: v for k, v in agg_dict.items() if v[0] in df.columns}
        abt = df.groupby("id").agg(**valid_aggs).reset_index()

        # Con 1 solo snapshot, std() retorna NaN. Lo reemplazamos por 0
        # porque "sin variacion" es mas correcto que "dato faltante".
        abt["price_std"] = abt["price_std"].fillna(0)
        print(f"ABT: {len(abt)} criptos, ~{n_records_per_crypto:.0f} snapshots por cripto")

        # =============================================================
        # FEATURES DERIVADAS: calculadas a partir de las existentes
        # =============================================================

        # price_to_volume_ratio: precio / volumen
        # Un ratio alto indica baja liquidez (poco volumen relativo al precio).
        # Un ratio bajo indica alta liquidez (mucho volumen relativo al precio).
        abt["price_to_volume_ratio"] = abt["current_price"] / abt["total_volume"]

        # market_dominance: que % del market cap total representa cada cripto
        # Se calcula como: market_cap_individual / sum(market_cap_todas) * 100
        # Bitcoin suele tener ~50-55% de dominancia.
        abt["market_dominance"] = (abt["market_cap"] / abt["market_cap"].sum() * 100).round(4)

        # =============================================================
        # pd.cut(): crear CATEGORIAS a partir de valores continuos
        # =============================================================
        # pd.cut() divide un rango numerico en "bins" (intervalos) y asigna
        # una etiqueta a cada intervalo. Es como crear "buckets" categoricos.
        #
        # Sintaxis: pd.cut(serie, bins=[limites], labels=[etiquetas])
        # - bins: lista de limites de los intervalos
        # - labels: nombre de cada intervalo
        # - include_lowest=True: incluye el valor minimo del primer bin
        #
        # Ejemplo: pd.cut([1, 3, 7], bins=[0, 2, 5, inf], labels=["bajo", "medio", "alto"])
        #   -> ["bajo", "medio", "alto"]
        # =============================================================

        # volatility_category: clasificacion por volatilidad
        #   |cambio_24h| < 2%   -> "baja"  (stablecoins, criptos grandes estables)
        #   2% <= |cambio| < 5% -> "media" (movimiento normal del mercado)
        #   |cambio| >= 5%      -> "alta"  (altcoins volatiles, memecoins)
        abt["volatility_category"] = pd.cut(
            abt["price_change_percentage_24h"].abs(),
            bins=[0, 2, 5, float("inf")],
            labels=["baja", "media", "alta"],
            include_lowest=True,
        ).astype(str)  # .astype(str) para evitar problemas con tipo Categorical en JSON

        # market_cap_tier: clasificacion por ranking de market cap
        #   Rank 1-10:  "top_10" (BTC, ETH, USDT, BNB, SOL, XRP, etc.)
        #   Rank 11-25: "top_25" (criptos grandes pero no dominantes)
        #   Rank 26+:   "rest"   (el resto del mercado)
        abt["market_cap_tier"] = pd.cut(
            abt["market_cap_rank"],
            bins=[0, 10, 25, float("inf")],
            labels=["top_10", "top_25", "rest"],
        ).astype(str)

        # price_tier: clasificacion por rango de precio en USD
        #   $0 - $1:       "micro"  (fracciones de dolar, memecoins como SHIB, PEPE)
        #   $1 - $100:     "small"  (altcoins medianas como ADA, DOT, MATIC)
        #   $100 - $10000: "medium" (ETH, BNB, SOL)
        #   $10000+:       "large"  (Bitcoin)
        abt["price_tier"] = pd.cut(
            abt["current_price"],
            bins=[0, 1, 100, 10000, float("inf")],
            labels=["micro", "small", "medium", "large"],
            include_lowest=True,
        ).astype(str)

        # =============================================================
        # INYECCION DE CONTEXTO GLOBAL
        # =============================================================
        # Si tenemos datos del mercado global (de silver.global_market),
        # los "inyectamos" en la ABT para contextualizar cada cripto.
        # Esto agrega columnas que relacionan cada moneda con el mercado total.
        # =============================================================
        if global_records:
            gdf = pd.DataFrame(global_records)
            # Tomar el snapshot mas reciente del mercado global
            latest = gdf.sort_values("ingested_at").iloc[-1]

            # Inyectar metricas globales como columnas constantes en toda la ABT
            # (todas las filas tienen el mismo valor porque es dato global)
            abt["global_total_market_cap"] = latest.get("total_market_cap_usd")
            abt["global_btc_dominance"] = latest.get("btc_dominance")
            abt["global_market_change_24h"] = latest.get("market_cap_change_pct_24h")

            # real_market_share: participacion REAL de cada cripto en el mercado total
            # A diferencia de market_dominance (que usa solo las 50 criptos de nuestro dataset),
            # real_market_share usa el market cap TOTAL reportado por CoinGecko.
            # Ejemplo: Bitcoin market_cap / total_market_cap_global * 100
            if latest.get("total_market_cap_usd") and latest["total_market_cap_usd"] > 0:
                abt["real_market_share"] = (
                    abt["market_cap"] / latest["total_market_cap_usd"] * 100
                ).round(6)

        # Metadata de auditoria
        abt["_created_at"] = datetime.now().isoformat()

        engine = sqlalchemy.create_engine(DB_URI)
        abt.to_sql("gold_abt_crypto", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.gold_abt_crypto: {len(abt)} filas, {len(abt.columns)} columnas")

    # ============================================================
    # TAREA 7: VERIFICAR INTEGRIDAD REFERENCIAL
    # ============================================================
    # La integridad referencial es la garantia de que TODA Foreign Key
    # en la fact table apunta a un registro que EXISTE en la dimension.
    #
    # Si fact_crypto_markets tiene crypto_id = "bitcoin", entonces
    # dim_crypto DEBE tener una fila con crypto_id = "bitcoin".
    # Si no la tiene, ese registro es un "huerfano" y algo salio mal.
    #
    # La verificacion usa un LEFT JOIN + WHERE ... IS NULL:
    #
    #   SELECT COUNT(*)
    #   FROM fact f
    #   LEFT JOIN dim d ON f.crypto_id = d.crypto_id
    #   WHERE d.crypto_id IS NULL   <-- solo filas sin match en dim
    #
    # LEFT JOIN devuelve TODAS las filas de la tabla izquierda (fact),
    # y NULL en las columnas de la tabla derecha (dim) cuando no hay match.
    # Si el WHERE IS NULL devuelve 0 filas, la integridad es correcta.
    # ============================================================
    @task
    def verify_integrity():
        """Verificar integridad referencial y resumen de tablas."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        # Recorremos TODAS las tablas del pipeline Medallion completo
        # (Bronze, Silver, Gold) para dar un resumen end-to-end
        tablas = [
            ("bronze", "crypto_markets", "Bronze"),
            ("bronze", "global_market", "Bronze global"),
            ("silver", "crypto_markets", "Silver"),
            ("silver", "quarantine_crypto_markets", "Quarantine"),
            ("silver", "global_market", "Silver global"),
            ("gold", "dim_crypto", "Gold dim"),
            ("gold", "dim_tiempo", "Gold dim"),
            ("gold", "fact_crypto_markets", "Gold fact"),
            ("gold", "fact_global_market", "Gold fact global"),
            ("gold", "gold_abt_crypto", "Gold ABT"),
        ]

        print("=== Pipeline Medallion - Resumen ===")
        for schema, tabla, capa in tablas:
            try:
                count = pd.read_sql(f"SELECT COUNT(*) as n FROM {schema}.{tabla}", engine)["n"][0]
                print(f"  {capa:15s} | {schema}.{tabla:30s} | {count:>6} filas")
            except Exception:
                print(f"  {capa:15s} | {schema}.{tabla:30s} | NO ENCONTRADA")

        # Verificacion de integridad referencial: buscar "huerfanos"
        # (registros en fact cuyo crypto_id no existe en dim)
        try:
            huerfanos = pd.read_sql("""
                SELECT COUNT(*) as n
                FROM gold.fact_crypto_markets f
                LEFT JOIN gold.dim_crypto d ON f.crypto_id = d.crypto_id
                WHERE d.crypto_id IS NULL
            """, engine)["n"][0]
            print(f"\nIntegridad referencial (huerfanos fact->dim): {huerfanos} (esperado: 0)")
        except Exception as e:
            print(f"\nError verificando integridad: {e}")

    # ============================================================
    # DEFINICION DEL FLUJO (ORQUESTACION)
    # ============================================================
    # Aqui definimos el orden de ejecucion de las tareas.
    # El flujo tiene 3 fases:
    #
    # FASE 1: Lectura (2 tareas en paralelo)
    #   read_silver() y read_silver_global() se ejecutan al mismo tiempo
    #   porque son independientes (leen tablas diferentes).
    #
    # FASE 2: Construccion (5 tareas en paralelo)
    #   dim_c, dim_t, fact, fact_g y abt se ejecutan en paralelo.
    #   Cada una construye una tabla de Gold independientemente.
    #   - dim_c, dim_t, fact dependen de silver_data
    #   - fact_g depende de global_data
    #   - abt depende de AMBOS (silver_data + global_data)
    #
    # FASE 3: Verificacion (1 tarea)
    #   verify_integrity() se ejecuta SOLO cuando las 5 tareas de fase 2
    #   terminaron. Usa el operador >> con una lista:
    #
    #   [dim_c, dim_t, fact, fact_g, abt] >> verify_integrity()
    #
    #   El operador >> significa "despues de". Con una lista a la izquierda,
    #   significa "despues de que TODAS estas terminen".
    #   Airflow ejecuta las 5 tareas en paralelo y espera a que todas
    #   finalicen antes de lanzar verify_integrity().
    # ============================================================
    silver_data = read_silver()
    global_data = read_silver_global()

    dim_c = build_dim_crypto(silver_data)
    dim_t = build_dim_tiempo(silver_data)
    fact = build_fact(silver_data)
    fact_g = build_fact_global(global_data)
    abt = build_abt(silver_data, global_data)

    # 5 tareas en paralelo >> 1 tarea de verificacion final
    [dim_c, dim_t, fact, fact_g, abt] >> verify_integrity()


# =============================================================================
# INSTANCIACION DEL DAG
# =============================================================================
# Esta llamada es OBLIGATORIA. Sin ella, Airflow no detecta el DAG.
# La funcion decorada con @dag retorna un objeto DAG cuando se invoca.
# Airflow escanea todos los .py en /dags/ buscando objetos DAG en el
# scope global del modulo.
# =============================================================================
crypto_gold()
