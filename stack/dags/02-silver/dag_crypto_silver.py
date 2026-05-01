"""
DAG: crypto_silver
Clase 10 - Transformacion Bronze a Silver con calidad, derivaciones y quarantine

Pipeline:
  bronze.crypto_markets → validar → limpiar → derivar columnas → silver.crypto_markets + silver.quarantine
  bronze.global_market → validar → dedup → silver.global_market

Silver agrega 6 columnas derivadas que NO existen en Bronze:
  spread_24h, spread_pct, ath_distance_pct, atl_distance_pct, supply_ratio, fdv_ratio
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
    dag_id="crypto_silver",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["silver", "crypto"],
    doc_md="""
    ## Crypto Silver - Transformacion y Calidad
    Lee TODOS los datos acumulados de Bronze, aplica:
    - Deduplicacion, validacion de rangos, parseo de fechas
    - **6 columnas derivadas** (spread, ATH distance, supply ratio, etc.)
    - Separacion Silver/Quarantine con reglas reales

    Idempotente: reconstruye Silver completo en cada corrida (replace).
    """,
)
def crypto_silver():

    # ============================================================
    # LEER BRONZE
    # ============================================================
    @task
    def read_bronze():
        """Leer todos los datos acumulados de bronze.crypto_markets."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql("SELECT * FROM bronze.crypto_markets", engine)
        snapshots = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 1
        print(f"Leidos {len(df)} registros de Bronze ({snapshots} snapshots, {df.shape[1]} cols)")
        return _clean_records(df.to_dict(orient="records"))

    @task
    def read_bronze_global():
        """Leer todos los datos acumulados de bronze.global_market."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        try:
            df = pd.read_sql("SELECT * FROM bronze.global_market", engine)
            print(f"Leidos {len(df)} registros de bronze.global_market")
            return _clean_records(df.to_dict(orient="records"))
        except Exception as e:
            print(f"bronze.global_market no existe aun: {e}")
            return []

    # ============================================================
    # EVALUAR CALIDAD
    # ============================================================
    @task
    def evaluate_quality(records: list):
        """Evaluar calidad: nulls, duplicados, rangos."""
        import pandas as pd

        df = pd.DataFrame(records)

        completitud = (1 - df.isnull().sum() / len(df)) * 100
        duplicados = df.duplicated(subset=["id", "snapshot_ts"]).sum()

        quality_score = completitud.mean()
        print("=== Reporte de Calidad ===")
        print(f"Completitud promedio: {quality_score:.1f}%")
        print(f"Duplicados (id+snapshot_ts): {duplicados}")
        print(f"Columnas con >10% nulls: {list(completitud[completitud < 90].index)}")

        if quality_score >= 95:
            print("-> PROCESS_TO_SILVER")
        elif quality_score >= 85:
            print("-> PROCESS_WITH_WARNING")
        else:
            print("-> HALT_AND_ALERT")

        return records

    # ============================================================
    # LIMPIAR, DERIVAR y SEPARAR
    # ============================================================
    @task
    def clean_and_enrich(records: list):
        """Deduplicar, validar, derivar columnas, separar Silver/Quarantine."""
        import pandas as pd

        df = pd.DataFrame(records)

        # --- 1. Deduplicar por (id, snapshot_ts) ---
        df = df.sort_values("ingested_at").drop_duplicates(
            subset=["id", "snapshot_ts"], keep="last"
        )
        n_after_dedup = len(df)

        # --- 2. Normalizar strings ---
        df["symbol"] = df["symbol"].str.strip().str.upper()
        df["name"] = df["name"].str.strip().str.title()

        # --- 3. Parsear fechas ISO (ath_date, atl_date, last_updated) ---
        for date_col in ["ath_date", "atl_date", "last_updated"]:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

        # --- 4. COLUMNAS DERIVADAS (6 nuevas que NO existen en Bronze) ---

        # Spread intradía: diferencia entre máximo y mínimo de 24h
        df["spread_24h"] = df["high_24h"] - df["low_24h"]

        # Spread como porcentaje del mínimo (volatilidad intradía)
        df["spread_pct"] = (df["spread_24h"] / df["low_24h"] * 100).round(4)

        # Distancia al ATH (All-Time High): cuanto bajo desde su maximo historico
        df["ath_distance_pct"] = ((df["current_price"] - df["ath"]) / df["ath"] * 100).round(4)

        # Distancia al ATL (All-Time Low): cuanto subio desde su minimo historico
        df["atl_distance_pct"] = ((df["current_price"] - df["atl"]) / df["atl"] * 100).round(4)

        # Supply ratio: que % del supply maximo esta en circulacion
        df["supply_ratio"] = (df["circulating_supply"] / df["max_supply"] * 100).round(4)

        # FDV ratio: fully diluted valuation / market cap actual
        df["fdv_ratio"] = (df["fully_diluted_valuation"] / df["market_cap"]).round(4)

        # --- 5. VALIDACION: reglas de negocio reales ---
        df["_is_valid"] = (
            # Basicas (no nulls en campos criticos)
            df["id"].notna()
            & df["symbol"].notna()
            & df["current_price"].notna()
            & (df["current_price"] >= 0)
            & df["market_cap_rank"].notna()
            # Reglas de rango (datos internamente consistentes)
            & (df["high_24h"].isna() | (df["high_24h"] >= df["low_24h"]))
            & (df["spread_24h"].isna() | (df["spread_24h"] >= 0))
        )

        df_silver = df[df["_is_valid"]].drop(columns=["_is_valid"]).copy()
        df_quarantine = df[~df["_is_valid"]].drop(columns=["_is_valid"]).copy()

        # --- 6. Metadata de trazabilidad ---
        now = datetime.now().isoformat()
        for d in [df_silver, df_quarantine]:
            d["_processed_at"] = now
            d["_source_table"] = "bronze.crypto_markets"

        s, q = len(df_silver), len(df_quarantine)
        print(f"Dedup: {n_after_dedup} | Silver: {s} | Quarantine: {q} | Tasa: {s / max(s + q, 1) * 100:.1f}%")
        print(f"Columnas derivadas agregadas: spread_24h, spread_pct, ath_distance_pct, atl_distance_pct, supply_ratio, fdv_ratio")

        return {
            "silver": _clean_records(df_silver.to_dict(orient="records")),
            "quarantine": _clean_records(df_quarantine.to_dict(orient="records")),
        }

    # ============================================================
    # LIMPIAR GLOBAL
    # ============================================================
    @task
    def clean_global(records: list):
        """Deduplicar y validar bronze.global_market → silver.global_market."""
        import pandas as pd
        import sqlalchemy

        if not records:
            print("Sin datos globales, saltando.")
            return

        df = pd.DataFrame(records)

        # Dedup por snapshot_ts
        df = df.sort_values("ingested_at").drop_duplicates(subset=["snapshot_ts"], keep="last")

        # Validar
        df = df[
            (df["total_market_cap_usd"].notna())
            & (df["total_market_cap_usd"] > 0)
            & (df["btc_dominance"].notna())
            & (df["btc_dominance"].between(0, 100))
        ]

        df["_processed_at"] = datetime.now().isoformat()

        engine = sqlalchemy.create_engine(DB_URI)
        df.to_sql("global_market", engine, schema="silver", if_exists="replace", index=False)
        print(f"silver.global_market: {len(df)} registros")

    # ============================================================
    # CARGAR SILVER
    # ============================================================
    @task
    def load_silver(split_data: dict):
        """Cargar silver.crypto_markets (replace completo)."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(split_data["silver"])
        engine = sqlalchemy.create_engine(DB_URI)
        df.to_sql("crypto_markets", engine, schema="silver", if_exists="replace", index=False)

        snapshots = df["snapshot_ts"].nunique() if "snapshot_ts" in df.columns else 1
        print(f"silver.crypto_markets: {len(df)} registros ({snapshots} snapshots, {df.shape[1]} cols)")

    @task
    def load_quarantine(split_data: dict):
        """Cargar silver.quarantine_crypto_markets (replace completo)."""
        import pandas as pd
        import sqlalchemy

        df = pd.DataFrame(split_data["quarantine"])
        engine = sqlalchemy.create_engine(DB_URI)
        df.to_sql("quarantine_crypto_markets", engine, schema="silver", if_exists="replace", index=False)
        print(f"silver.quarantine_crypto_markets: {len(df)} registros")

    @task
    def log_summary(split_data: dict):
        """Imprimir resumen final del pipeline Silver."""
        s = len(split_data["silver"])
        q = len(split_data["quarantine"])
        total = s + q
        tasa = s / max(total, 1) * 100
        print("=== Resumen Pipeline Silver ===")
        print(f"Silver: {s} | Quarantine: {q} | Tasa de exito: {tasa:.1f}%")
        if s > 0:
            import pandas as pd
            df = pd.DataFrame(split_data["silver"])
            cols_derivadas = ["spread_24h", "spread_pct", "ath_distance_pct",
                              "atl_distance_pct", "supply_ratio", "fdv_ratio"]
            for col in cols_derivadas:
                if col in df.columns:
                    non_null = df[col].notna().sum()
                    print(f"  {col}: {non_null}/{s} no-null ({non_null/s*100:.0f}%)")

    # ============================================================
    # FLUJO
    # ============================================================
    bronze_data = read_bronze()
    bronze_global = read_bronze_global()

    evaluated = evaluate_quality(bronze_data)
    split = clean_and_enrich(evaluated)

    load_s = load_silver(split)
    load_q = load_quarantine(split)
    clean_g = clean_global(bronze_global)

    [load_s, load_q, clean_g] >> log_summary(split)


crypto_silver()
