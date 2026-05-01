"""
DAG: crypto_gold
Clase 11 - Transformacion Silver a Gold (Star Schema enriquecido + ABT)

Pipeline: silver.crypto_markets + silver.global_market →
  - dim_crypto (9 cols: id, symbol, name, supply, ATH/ATL)
  - dim_tiempo (7 cols: fecha, anio, mes, trimestre, dia, fin_de_semana)
  - fact_crypto_markets (17 metricas por cripto por fecha)
  - fact_global_market (datos del mercado total por fecha)
  - gold_abt_crypto (wide table con features derivadas para ML)
"""

from airflow.decorators import dag, task
from datetime import datetime
import math
import os


DB_URI = (
    f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER')}:{os.getenv('SOURCE_DB_PASS')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME')}"
)


def _clean_records(records):
    """Limpiar NaN/inf/Timestamp/datetime de records para que XCom (JSON) no explote."""
    import pandas as pd
    from datetime import date, datetime as dt
    for row in records:
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
            elif isinstance(v, (pd.Timestamp,)):
                row[k] = v.isoformat() if pd.notna(v) else None
            elif isinstance(v, (dt, date)):
                row[k] = v.isoformat()
            elif v is pd.NaT:
                row[k] = None
    return records


@dag(
    dag_id="crypto_gold",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["gold", "crypto"],
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
    # LEER SILVER
    # ============================================================
    @task
    def read_silver():
        """Leer todos los datos de silver.crypto_markets."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql("SELECT * FROM silver.crypto_markets", engine)
        snapshots = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 1
        print(f"Leidos {len(df)} registros de Silver ({snapshots} snapshots, {df['id'].nunique()} criptos, {df.shape[1]} cols)")
        return _clean_records(df.to_dict(orient="records"))

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
            print(f"silver.global_market no disponible: {e}")
            return []

    # ============================================================
    # DIMENSION: CRIPTOMONEDAS (enriquecida)
    # ============================================================
    @task
    def build_dim_crypto(records: list):
        """Crear dimension de criptomonedas con datos semi-estaticos."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)

        # Tomar el snapshot mas reciente por cripto
        df = df.sort_values("ingested_at").groupby("id").last().reset_index()

        dim_cols = ["id", "symbol", "name", "max_supply", "total_supply",
                     "ath", "ath_date", "atl", "atl_date"]
        dim = df[[c for c in dim_cols if c in df.columns]].copy()
        dim = dim.rename(columns={"id": "crypto_id"})

        engine = sqlalchemy.create_engine(DB_URI)
        dim.to_sql("dim_crypto", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.dim_crypto: {len(dim)} filas, {dim.shape[1]} columnas")

    # ============================================================
    # DIMENSION: TIEMPO
    # ============================================================
    @task
    def build_dim_tiempo(records: list):
        """Crear dimension temporal desde fechas reales en los datos."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(records)
        df["_fecha"] = pd.to_datetime(df["ingested_at"]).dt.normalize()
        fechas_unicas = sorted(df["_fecha"].unique())

        dim = pd.DataFrame({"fecha": fechas_unicas})
        dim["fecha"] = pd.to_datetime(dim["fecha"])
        dim["fecha_id"] = dim["fecha"].dt.strftime("%Y%m%d").astype(int)
        dim["anio"] = dim["fecha"].dt.year
        dim["mes"] = dim["fecha"].dt.month
        dim["trimestre"] = dim["fecha"].dt.quarter
        dim["dia_semana"] = dim["fecha"].dt.day_name()
        dim["es_fin_de_semana"] = dim["fecha"].dt.dayofweek >= 5

        engine = sqlalchemy.create_engine(DB_URI)
        if sqlalchemy.inspect(engine).has_table("dim_tiempo", schema="gold"):
            import pandas as pd
            existing = pd.read_sql("SELECT fecha_id FROM gold.dim_tiempo", engine)
            dim = dim[~dim["fecha_id"].isin(existing["fecha_id"])]
            if dim.empty:
                print("gold.dim_tiempo: sin fechas nuevas que agregar")
                return
        dim.to_sql("dim_tiempo", engine, schema="gold", if_exists="append", index=False)
        print(f"gold.dim_tiempo: {len(dim)} fechas nuevas agregadas")

    # ============================================================
    # FACT TABLE: CRYPTO MARKETS (17 metricas)
    # Estrategia: delete-insert por dia (idempotente, acumula historico)
    # ============================================================
    @task
    def build_fact(records: list):
        """Crear tabla de hechos con 17 metricas + FKs."""
        import pandas as pd
        import sqlalchemy
        from sqlalchemy import text

        df = pd.DataFrame(records)
        df["crypto_id"] = df["id"]
        df["fecha_id"] = pd.to_datetime(df["ingested_at"]).dt.strftime("%Y%m%d").astype(int)

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
        fact = df[[c for c in fact_cols if c in df.columns]].copy()
        fact["_loaded_at"] = datetime.now().isoformat()

        today_id = int(datetime.now().strftime("%Y%m%d"))

        engine = sqlalchemy.create_engine(DB_URI)
        # Crear tabla si no existe (primer run)
        if not sqlalchemy.inspect(engine).has_table("fact_crypto_markets", schema="gold"):
            fact.to_sql("fact_crypto_markets", engine, schema="gold", if_exists="append", index=False)
        else:
            # Borrar datos del dia actual y reinsertar
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM gold.fact_crypto_markets WHERE fecha_id = {today_id}"))
            fact.to_sql("fact_crypto_markets", engine, schema="gold", if_exists="append", index=False)
        print(f"gold.fact_crypto_markets: {len(fact)} filas insertadas para fecha_id={today_id}")

    # ============================================================
    # FACT TABLE: GLOBAL MARKET
    # Estrategia: delete-insert por dia
    # ============================================================
    @task
    def build_fact_global(global_records: list):
        """Crear tabla de hechos del mercado global."""
        import pandas as pd
        import sqlalchemy
        from sqlalchemy import text

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
        fact = fact.sort_values("fecha_id").drop_duplicates(subset=["fecha_id"], keep="last")
        fact["_loaded_at"] = datetime.now().isoformat()

        today_id = int(datetime.now().strftime("%Y%m%d"))

        engine = sqlalchemy.create_engine(DB_URI)
        if not sqlalchemy.inspect(engine).has_table("fact_global_market", schema="gold"):
            fact.to_sql("fact_global_market", engine, schema="gold", if_exists="append", index=False)
        else:
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM gold.fact_global_market WHERE fecha_id = {today_id}"))
            fact.to_sql("fact_global_market", engine, schema="gold", if_exists="append", index=False)
        print(f"gold.fact_global_market: {len(fact)} filas insertadas para fecha_id={today_id}")

    # ============================================================
    # ABT (Wide Table para ML)
    # ============================================================
    @task
    def build_abt(records: list, global_records: list):
        """Crear ABT con features derivadas para ML, incluyendo contexto global."""
        import pandas as pd
        import sqlalchemy
        from sqlalchemy import text

        df = pd.DataFrame(records)
        n_records_per_crypto = len(df) / max(df["id"].nunique(), 1)

        # --- Siempre agregar por cripto (1 fila por cripto) ---
        agg_dict = {
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
            "avg_price": ("current_price", "mean"),
            "price_std": ("current_price", "std"),
            "avg_spread_pct": ("spread_pct", "mean"),
            "n_snapshots": ("current_price", "count"),
        }
        # Solo agregar columnas que existen
        valid_aggs = {k: v for k, v in agg_dict.items() if v[0] in df.columns}
        abt = df.groupby("id").agg(**valid_aggs).reset_index()
        abt["price_std"] = abt["price_std"].fillna(0)
        print(f"ABT: {len(abt)} criptos, ~{n_records_per_crypto:.0f} snapshots por cripto")

        # --- Features derivadas ---
        abt["price_to_volume_ratio"] = abt["current_price"] / abt["total_volume"]
        abt["market_dominance"] = (abt["market_cap"] / abt["market_cap"].sum() * 100).round(4)

        abt["volatility_category"] = pd.cut(
            abt["price_change_percentage_24h"].abs(),
            bins=[0, 2, 5, float("inf")],
            labels=["baja", "media", "alta"],
            include_lowest=True,
        ).astype(str)

        abt["market_cap_tier"] = pd.cut(
            abt["market_cap_rank"],
            bins=[0, 10, 25, float("inf")],
            labels=["top_10", "top_25", "rest"],
        ).astype(str)

        abt["price_tier"] = pd.cut(
            abt["current_price"],
            bins=[0, 1, 100, 10000, float("inf")],
            labels=["micro", "small", "medium", "large"],
            include_lowest=True,
        ).astype(str)

        # --- Contexto global (si disponible) ---
        if global_records:
            gdf = pd.DataFrame(global_records)
            # Tomar el snapshot mas reciente
            latest = gdf.sort_values("ingested_at").iloc[-1]
            abt["global_total_market_cap"] = latest.get("total_market_cap_usd")
            abt["global_btc_dominance"] = latest.get("btc_dominance")
            abt["global_market_change_24h"] = latest.get("market_cap_change_pct_24h")
            # Dominancia real vs mercado total
            if latest.get("total_market_cap_usd") and latest["total_market_cap_usd"] > 0:
                abt["real_market_share"] = (
                    abt["market_cap"] / latest["total_market_cap_usd"] * 100
                ).round(6)

        today_id = int(datetime.now().strftime("%Y%m%d"))
        abt["fecha_id"] = today_id
        abt["_created_at"] = datetime.now().isoformat()

        engine = sqlalchemy.create_engine(DB_URI)
        if not sqlalchemy.inspect(engine).has_table("gold_abt_crypto", schema="gold"):
            abt.to_sql("gold_abt_crypto", engine, schema="gold", if_exists="append", index=False)
        else:
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM gold.gold_abt_crypto WHERE fecha_id = {today_id}"))
            abt.to_sql("gold_abt_crypto", engine, schema="gold", if_exists="append", index=False)
        print(f"gold.gold_abt_crypto: {len(abt)} filas insertadas para fecha_id={today_id}")

    # ============================================================
    # VERIFICAR INTEGRIDAD
    # ============================================================
    @task
    def verify_integrity():
        """Verificar integridad referencial y resumen de tablas."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

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
    # FLUJO
    # ============================================================
    silver_data = read_silver()
    global_data = read_silver_global()

    dim_c = build_dim_crypto(silver_data)
    dim_t = build_dim_tiempo(silver_data)
    fact = build_fact(silver_data)
    fact_g = build_fact_global(global_data)
    abt = build_abt(silver_data, global_data)

    [dim_c, dim_t, fact, fact_g, abt] >> verify_integrity()


crypto_gold()
