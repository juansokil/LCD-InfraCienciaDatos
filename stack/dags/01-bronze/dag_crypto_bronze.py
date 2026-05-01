"""
DAG: crypto_bronze
Clase 09 - Ingesta desde API CoinGecko a Capa Bronze

Pipeline: API CoinGecko → DataFrame → bronze.crypto_markets + bronze.global_market
Dos endpoints en paralelo:
  - /coins/markets → top 50 criptos (datos por moneda)
  - /global → datos agregados del mercado crypto total

Corre cada 5 minutos, acumulando snapshots con precios en tiempo real.
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
    """Limpiar NaN/inf de records para que XCom (JSON) no explote."""
    for row in records:
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
    return records


@dag(
    dag_id="crypto_bronze",
    start_date=datetime(2024, 1, 1),
    schedule="*/5 * * * *",
    catchup=False,
    tags=["bronze", "crypto"],
    doc_md="""
    ## Crypto Bronze - Ingesta cada 5 minutos
    Consulta **dos endpoints** de CoinGecko en paralelo:
    - Top 50 criptomonedas por market cap → `bronze.crypto_markets`
    - Datos globales del mercado crypto → `bronze.global_market`

    Cada corrida genera un snapshot unico (los precios cambian constantemente).
    """,
)
def crypto_bronze():

    # ============================================================
    # ENDPOINT 1: /coins/markets (datos por cripto)
    # ============================================================
    @task
    def fetch_markets():
        """Consultar CoinGecko API - Top 50 criptomonedas."""
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

    # ============================================================
    # ENDPOINT 2: /global (datos del mercado total)
    # ============================================================
    @task(retries=2, retry_delay=10)
    def fetch_global():
        """Consultar CoinGecko API - Datos globales del mercado."""
        import requests
        import time

        # Esperar para no exceder rate limit de CoinGecko free tier (~10-30 req/min)
        time.sleep(5)

        url = "https://api.coingecko.com/api/v3/global"

        print("Consultando CoinGecko /global ...")
        response = requests.get(url)
        response.raise_for_status()

        data = response.json()["data"]
        print(f"Mercado global: {data.get('active_cryptocurrencies', '?')} criptos activas")
        return data

    # ============================================================
    # TRANSFORM: markets
    # ============================================================
    @task
    def transform_markets(data: list):
        """Seleccionar columnas, tipar y agregar metadata."""
        import pandas as pd

        df = pd.DataFrame(data)

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
        df = df[columnas_bronze].copy()

        # Type coercion para columnas numericas
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

        # Metadata: timestamp completo (cada snapshot es unico)
        now = datetime.now()
        df["ingested_at"] = now.isoformat()
        df["snapshot_ts"] = now.strftime("%Y-%m-%d %H:%M")

        print(f"Snapshot: {df['snapshot_ts'].iloc[0]} | {df.shape[0]} registros, {df.shape[1]} columnas")
        return _clean_records(df.to_dict(orient="records"))

    # ============================================================
    # TRANSFORM + LOAD: global
    # ============================================================
    @task
    def load_global(data: dict):
        """Transformar y cargar datos globales en bronze.global_market."""
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

        df.to_sql("crypto_markets", engine, schema="bronze", if_exists="append", index=False)

        total = pd.read_sql("SELECT COUNT(*) as n FROM bronze.crypto_markets", engine)["n"][0]
        snapshots = pd.read_sql(
            "SELECT COUNT(DISTINCT snapshot_ts) as n FROM bronze.crypto_markets", engine
        )["n"][0]

        print(f"+{len(df)} registros ({df.shape[1]} cols) | Total: {total} ({snapshots} snapshots)")

    # ============================================================
    # FLUJO: markets primero, luego global (evita rate limit CoinGecko)
    # ============================================================
    raw_markets = fetch_markets()
    transformed = transform_markets(raw_markets)
    loaded = load_markets(transformed)

    # Global despues de markets para no exceder rate limit
    raw_global = fetch_global()
    load_global(raw_global)


crypto_bronze()
