"""
DAG: crypto_pipeline_completo
Pipeline Medallion completo: API → Bronze → Silver → Gold

Ejecuta las 3 capas en secuencia con TaskGroups.
Se puede correr manualmente o programar con schedule.

Incluye 2 endpoints de CoinGecko (/markets + /global),
6 columnas derivadas en Silver, y Star Schema enriquecido en Gold.
"""

from airflow.decorators import dag, task, task_group
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
    dag_id="crypto_pipeline_completo",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze", "silver", "gold", "crypto", "pipeline"],
    doc_md="""
    ## Pipeline Medallion Completo
    Ejecuta las 3 capas en un solo DAG con TaskGroups:

    ```
    CoinGecko API (/markets + /global) → Bronze → Silver → Gold → Verificacion
    ```

    - **Bronze**: 2 tablas (crypto_markets: 24 cols, global_market: 9 cols)
    - **Silver**: 6 columnas derivadas (spread, ATH distance, supply ratio, etc.)
    - **Gold**: Star Schema (17 metricas) + fact_global + ABT (20+ features)
    """,
)
def crypto_pipeline_completo():

    # =========================================================================
    # BRONZE (Clase 09)
    # =========================================================================
    @task_group(group_id="bronze")
    def bronze_layer():

        @task
        def fetch_markets():
            """Consultar CoinGecko /coins/markets - Top 50."""
            import requests

            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 50,
                "page": 1,
                "sparkline": False,
            }

            print("Consultando CoinGecko /coins/markets ...")
            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            print(f"Registros obtenidos: {len(data)}")
            return data

        @task
        def fetch_global():
            """Consultar CoinGecko /global."""
            import requests

            url = "https://api.coingecko.com/api/v3/global"
            print("Consultando CoinGecko /global ...")
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()["data"]
            print(f"Mercado global: {data.get('active_cryptocurrencies', '?')} criptos activas")
            return data

        @task
        def transform_markets(data: list):
            """Seleccionar 22 columnas, tipar y agregar metadata."""
            import pandas as pd

            df = pd.DataFrame(data)
            columnas = [
                "id", "symbol", "name",
                "current_price", "high_24h", "low_24h", "price_change_24h",
                "price_change_percentage_24h",
                "market_cap_change_24h", "market_cap_change_percentage_24h",
                "market_cap", "market_cap_rank", "fully_diluted_valuation", "total_volume",
                "circulating_supply", "total_supply", "max_supply",
                "ath", "ath_change_percentage", "ath_date",
                "atl", "atl_change_percentage", "atl_date",
                "last_updated",
            ]
            df = df[columnas].copy()

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

            now = datetime.now()
            df["ingested_at"] = now.isoformat()
            df["snapshot_ts"] = now.strftime("%Y-%m-%d %H:%M")

            print(f"Bronze markets: {df.shape[0]} registros, {df.shape[1]} columnas")
            return _clean_records(df.to_dict(orient="records"))

        @task
        def load_markets(records: list):
            """Acumular en bronze.crypto_markets."""
            import pandas as pd
            import sqlalchemy

            df = pd.DataFrame(records)
            engine = sqlalchemy.create_engine(DB_URI)
            df.to_sql("crypto_markets", engine, schema="bronze", if_exists="append", index=False)

            total = pd.read_sql("SELECT COUNT(*) as n FROM bronze.crypto_markets", engine)["n"][0]
            snapshots = pd.read_sql("SELECT COUNT(DISTINCT snapshot_ts) as n FROM bronze.crypto_markets", engine)["n"][0]
            print(f"+{len(df)} registros | Total: {total} ({snapshots} snapshots)")
            return records

        @task
        def load_global(data: dict):
            """Cargar datos globales en bronze.global_market."""
            import pandas as pd
            import sqlalchemy

            now = datetime.now()
            row = {
                "active_cryptocurrencies": data.get("active_cryptocurrencies"),
                "markets": data.get("markets"),
                "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
                "total_volume_usd": data.get("total_volume", {}).get("usd"),
                "btc_dominance": data.get("market_cap_percentage", {}).get("btc"),
                "eth_dominance": data.get("market_cap_percentage", {}).get("eth"),
                "market_cap_change_pct_24h": data.get("market_cap_change_percentage_24h_usd"),
                "ingested_at": now.isoformat(),
                "snapshot_ts": now.strftime("%Y-%m-%d %H:%M"),
            }
            df = pd.DataFrame([row])
            engine = sqlalchemy.create_engine(DB_URI)
            df.to_sql("global_market", engine, schema="bronze", if_exists="append", index=False)
            print(f"bronze.global_market: +1 registro | BTC dom: {row['btc_dominance']:.1f}%")

        raw_markets = fetch_markets()
        raw_global = fetch_global()
        transformed = transform_markets(raw_markets)
        load_markets(transformed)
        load_global(raw_global)

    # =========================================================================
    # SILVER (Clase 10)
    # =========================================================================
    @task_group(group_id="silver")
    def silver_layer():

        @task
        def read_all_bronze():
            """Leer TODO Bronze acumulado."""
            import pandas as pd
            import sqlalchemy

            engine = sqlalchemy.create_engine(DB_URI)
            df = pd.read_sql("SELECT * FROM bronze.crypto_markets", engine)
            print(f"Bronze total: {len(df)} registros, {df.shape[1]} cols")
            return _clean_records(df.to_dict(orient="records"))

        @task
        def read_bronze_global():
            """Leer bronze.global_market."""
            import pandas as pd
            import sqlalchemy

            engine = sqlalchemy.create_engine(DB_URI)
            try:
                df = pd.read_sql("SELECT * FROM bronze.global_market", engine)
                print(f"Bronze global: {len(df)} registros")
                return _clean_records(df.to_dict(orient="records"))
            except Exception:
                print("bronze.global_market no existe aun")
                return []

        @task
        def clean_and_enrich(records: list):
            """Deduplicar, validar, derivar 6 columnas, separar Silver/Quarantine."""
            import pandas as pd

            df = pd.DataFrame(records)

            # Dedup
            df = df.sort_values("ingested_at").drop_duplicates(
                subset=["id", "snapshot_ts"], keep="last"
            )

            # Normalizar
            df["symbol"] = df["symbol"].str.strip().str.upper()
            df["name"] = df["name"].str.strip().str.title()

            # Parsear fechas
            for date_col in ["ath_date", "atl_date", "last_updated"]:
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

            # 6 columnas derivadas
            df["spread_24h"] = df["high_24h"] - df["low_24h"]
            df["spread_pct"] = (df["spread_24h"] / df["low_24h"] * 100).round(4)
            df["ath_distance_pct"] = ((df["current_price"] - df["ath"]) / df["ath"] * 100).round(4)
            df["atl_distance_pct"] = ((df["current_price"] - df["atl"]) / df["atl"] * 100).round(4)
            df["supply_ratio"] = (df["circulating_supply"] / df["max_supply"] * 100).round(4)
            df["fdv_ratio"] = (df["fully_diluted_valuation"] / df["market_cap"]).round(4)

            # Validacion
            df["_is_valid"] = (
                df["id"].notna()
                & df["symbol"].notna()
                & df["current_price"].notna()
                & (df["current_price"] >= 0)
                & df["market_cap_rank"].notna()
                & (df["high_24h"].isna() | (df["high_24h"] >= df["low_24h"]))
            )

            df_silver = df[df["_is_valid"]].drop(columns=["_is_valid"]).copy()
            df_quarantine = df[~df["_is_valid"]].drop(columns=["_is_valid"]).copy()

            now = datetime.now().isoformat()
            for d in [df_silver, df_quarantine]:
                d["_processed_at"] = now
                d["_source_table"] = "bronze.crypto_markets"

            s, q = len(df_silver), len(df_quarantine)
            print(f"Silver: {s} | Quarantine: {q} | Cols derivadas: 6")

            return {
                "silver": _clean_records(df_silver.to_dict(orient="records")),
                "quarantine": _clean_records(df_quarantine.to_dict(orient="records")),
            }

        @task
        def load_silver(split_data: dict):
            """Cargar silver.crypto_markets."""
            import pandas as pd
            import sqlalchemy

            df = pd.DataFrame(split_data["silver"])
            engine = sqlalchemy.create_engine(DB_URI)
            df.to_sql("crypto_markets", engine, schema="silver", if_exists="replace", index=False)
            print(f"silver.crypto_markets: {len(df)} registros, {df.shape[1]} cols")

        @task
        def load_quarantine(split_data: dict):
            """Cargar silver.quarantine_crypto_markets."""
            import pandas as pd
            import sqlalchemy

            df = pd.DataFrame(split_data["quarantine"])
            engine = sqlalchemy.create_engine(DB_URI)
            df.to_sql("quarantine_crypto_markets", engine, schema="silver", if_exists="replace", index=False)
            print(f"silver.quarantine_crypto_markets: {len(df)} registros")

        @task
        def clean_global(records: list):
            """Limpiar y cargar silver.global_market."""
            import pandas as pd
            import sqlalchemy

            if not records:
                print("Sin datos globales")
                return

            df = pd.DataFrame(records)
            df = df.sort_values("ingested_at").drop_duplicates(subset=["snapshot_ts"], keep="last")
            df = df[
                (df["total_market_cap_usd"].notna())
                & (df["total_market_cap_usd"] > 0)
            ]
            df["_processed_at"] = datetime.now().isoformat()

            engine = sqlalchemy.create_engine(DB_URI)
            df.to_sql("global_market", engine, schema="silver", if_exists="replace", index=False)
            print(f"silver.global_market: {len(df)} registros")

        all_bronze = read_all_bronze()
        bronze_global = read_bronze_global()
        split = clean_and_enrich(all_bronze)
        load_silver(split)
        load_quarantine(split)
        clean_global(bronze_global)

    # =========================================================================
    # GOLD (Clase 11)
    # =========================================================================
    @task_group(group_id="gold")
    def gold_layer():

        @task
        def read_silver():
            """Leer silver.crypto_markets."""
            import pandas as pd
            import sqlalchemy

            engine = sqlalchemy.create_engine(DB_URI)
            df = pd.read_sql("SELECT * FROM silver.crypto_markets", engine)
            print(f"Silver: {len(df)} registros, {df.shape[1]} cols")
            return _clean_records(df.to_dict(orient="records"))

        @task
        def read_silver_global():
            """Leer silver.global_market."""
            import pandas as pd
            import sqlalchemy

            engine = sqlalchemy.create_engine(DB_URI)
            try:
                df = pd.read_sql("SELECT * FROM silver.global_market", engine)
                print(f"Silver global: {len(df)} registros")
                return _clean_records(df.to_dict(orient="records"))
            except Exception:
                return []

        @task
        def build_dim_crypto(records: list):
            """Crear dim_crypto enriquecida."""
            import pandas as pd
            import sqlalchemy

            df = pd.DataFrame(records)
            df = df.sort_values("ingested_at").groupby("id").last().reset_index()

            dim_cols = ["id", "symbol", "name", "max_supply", "total_supply",
                         "ath", "ath_date", "atl", "atl_date"]
            dim = df[[c for c in dim_cols if c in df.columns]].copy()
            dim = dim.rename(columns={"id": "crypto_id"})

            engine = sqlalchemy.create_engine(DB_URI)
            dim.to_sql("dim_crypto", engine, schema="gold", if_exists="replace", index=False)
            print(f"gold.dim_crypto: {len(dim)} filas, {dim.shape[1]} cols")

        @task
        def build_dim_tiempo(records: list):
            """Crear dimension temporal."""
            import pandas as pd
            import sqlalchemy

            df = pd.DataFrame(records)
            df["_fecha"] = pd.to_datetime(df["ingested_at"]).dt.normalize()
            fechas = sorted(df["_fecha"].unique())

            dim = pd.DataFrame({"fecha": fechas})
            dim["fecha"] = pd.to_datetime(dim["fecha"])
            dim["fecha_id"] = dim["fecha"].dt.strftime("%Y%m%d").astype(int)
            dim["anio"] = dim["fecha"].dt.year
            dim["mes"] = dim["fecha"].dt.month
            dim["trimestre"] = dim["fecha"].dt.quarter
            dim["dia_semana"] = dim["fecha"].dt.day_name()
            dim["es_fin_de_semana"] = dim["fecha"].dt.dayofweek >= 5

            engine = sqlalchemy.create_engine(DB_URI)
            if sqlalchemy.inspect(engine).has_table("dim_tiempo", schema="gold"):
                existing = pd.read_sql("SELECT fecha_id FROM gold.dim_tiempo", engine)
                dim = dim[~dim["fecha_id"].isin(existing["fecha_id"])]
                if dim.empty:
                    print("gold.dim_tiempo: sin fechas nuevas")
                    return
            dim.to_sql("dim_tiempo", engine, schema="gold", if_exists="append", index=False)
            print(f"gold.dim_tiempo: {len(dim)} fechas nuevas")

        @task
        def build_fact(records: list):
            """Crear fact_crypto_markets con 17 metricas. Delete-insert por dia."""
            import pandas as pd
            import sqlalchemy
            from sqlalchemy import text

            df = pd.DataFrame(records)
            df["crypto_id"] = df["id"]
            df["fecha_id"] = pd.to_datetime(df["ingested_at"]).dt.strftime("%Y%m%d").astype(int)

            fact_cols = [
                "crypto_id", "fecha_id",
                "current_price", "high_24h", "low_24h", "price_change_24h",
                "spread_24h", "spread_pct",
                "price_change_percentage_24h", "market_cap_change_percentage_24h",
                "market_cap", "total_volume", "fully_diluted_valuation",
                "circulating_supply", "supply_ratio",
                "market_cap_rank", "fdv_ratio", "ath_distance_pct",
            ]
            fact = df[[c for c in fact_cols if c in df.columns]].copy()
            fact["_loaded_at"] = datetime.now().isoformat()

            today_id = int(datetime.now().strftime("%Y%m%d"))
            engine = sqlalchemy.create_engine(DB_URI)
            if not sqlalchemy.inspect(engine).has_table("fact_crypto_markets", schema="gold"):
                fact.to_sql("fact_crypto_markets", engine, schema="gold", if_exists="append", index=False)
            else:
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM gold.fact_crypto_markets WHERE fecha_id = {today_id}"))
                fact.to_sql("fact_crypto_markets", engine, schema="gold", if_exists="append", index=False)
            print(f"gold.fact_crypto_markets: {len(fact)} filas para fecha_id={today_id}")

        @task
        def build_fact_global(global_records: list):
            """Crear fact_global_market. Delete-insert por dia."""
            import pandas as pd
            import sqlalchemy
            from sqlalchemy import text

            if not global_records:
                print("Sin datos globales, saltando")
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
            fact = fact.drop_duplicates(subset=["fecha_id"], keep="last")
            fact["_loaded_at"] = datetime.now().isoformat()

            today_id = int(datetime.now().strftime("%Y%m%d"))
            engine = sqlalchemy.create_engine(DB_URI)
            if not sqlalchemy.inspect(engine).has_table("fact_global_market", schema="gold"):
                fact.to_sql("fact_global_market", engine, schema="gold", if_exists="append", index=False)
            else:
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM gold.fact_global_market WHERE fecha_id = {today_id}"))
                fact.to_sql("fact_global_market", engine, schema="gold", if_exists="append", index=False)
            print(f"gold.fact_global_market: {len(fact)} filas para fecha_id={today_id}")

        @task
        def build_abt(records: list, global_records: list):
            """Crear ABT con 20+ features para ML. Delete-insert por dia."""
            import pandas as pd
            import sqlalchemy
            from sqlalchemy import text

            df = pd.DataFrame(records)
            n_records_per_crypto = len(df) / max(df["id"].nunique(), 1)

            # Siempre agregar por cripto (1 fila por cripto)
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
            valid_aggs = {k: v for k, v in agg_dict.items() if v[0] in df.columns}
            abt = df.groupby("id").agg(**valid_aggs).reset_index()
            abt["price_std"] = abt["price_std"].fillna(0)
            print(f"ABT: {len(abt)} criptos, ~{n_records_per_crypto:.0f} snapshots por cripto")

            abt["price_to_volume_ratio"] = abt["current_price"] / abt["total_volume"]
            abt["market_dominance"] = (abt["market_cap"] / abt["market_cap"].sum() * 100).round(4)

            abt["volatility_category"] = pd.cut(
                abt["price_change_percentage_24h"].abs(),
                bins=[0, 2, 5, float("inf")], labels=["baja", "media", "alta"],
                include_lowest=True,
            ).astype(str)

            abt["market_cap_tier"] = pd.cut(
                abt["market_cap_rank"],
                bins=[0, 10, 25, float("inf")], labels=["top_10", "top_25", "rest"],
            ).astype(str)

            abt["price_tier"] = pd.cut(
                abt["current_price"],
                bins=[0, 1, 100, 10000, float("inf")],
                labels=["micro", "small", "medium", "large"],
                include_lowest=True,
            ).astype(str)

            # Contexto global
            if global_records:
                gdf = pd.DataFrame(global_records)
                latest = gdf.sort_values("ingested_at").iloc[-1]
                abt["global_total_market_cap"] = latest.get("total_market_cap_usd")
                abt["global_btc_dominance"] = latest.get("btc_dominance")
                abt["global_market_change_24h"] = latest.get("market_cap_change_pct_24h")
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
            print(f"gold.gold_abt_crypto: {len(abt)} filas para fecha_id={today_id}")

        silver_data = read_silver()
        global_data = read_silver_global()
        build_dim_crypto(silver_data)
        build_dim_tiempo(silver_data)
        build_fact(silver_data)
        build_fact_global(global_data)
        build_abt(silver_data, global_data)

    # =========================================================================
    # VERIFICACION FINAL
    # =========================================================================
    @task
    def verify_pipeline():
        """Verificar el pipeline completo: todas las tablas y su integridad."""
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

        print("=" * 65)
        print("  PIPELINE MEDALLION COMPLETO - RESUMEN")
        print("=" * 65)
        for schema, tabla, capa in tablas:
            try:
                n = pd.read_sql(f"SELECT COUNT(*) as n FROM {schema}.{tabla}", engine)["n"][0]
                print(f"  {capa:15s} | {schema}.{tabla:30s} | {n:>6} filas")
            except Exception:
                print(f"  {capa:15s} | {schema}.{tabla:30s} | NO ENCONTRADA")

        try:
            h = pd.read_sql("""
                SELECT COUNT(*) as n
                FROM gold.fact_crypto_markets f
                LEFT JOIN gold.dim_crypto d ON f.crypto_id = d.crypto_id
                WHERE d.crypto_id IS NULL
            """, engine)["n"][0]
            print(f"\n  Integridad referencial (huerfanos): {h} (esperado: 0)")
        except Exception as e:
            print(f"\n  Error verificando integridad: {e}")
        print("=" * 65)

    # =========================================================================
    # ORQUESTACION: Bronze >> Silver >> Gold >> Verificacion
    # =========================================================================
    bronze_layer() >> silver_layer() >> gold_layer() >> verify_pipeline()


crypto_pipeline_completo()
