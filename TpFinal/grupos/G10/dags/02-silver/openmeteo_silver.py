import json
import pandas as pd
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text


DB_URI = "postgresql+psycopg2://airflow:airflow@postgres:5432/airflow_db"


def _get_engine():
    return create_engine(DB_URI)


def _safe_float(value):
    """Convierte a float o retorna None si es inválido."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def transformar_silver():

    engine = _get_engine()

    # ─────────────────────────────────────────────
    # 1. LEER BRONZE
    # ─────────────────────────────────────────────
    query = text("""
        SELECT ciudad, api_response, ingested_at
        FROM bronze.weather_raw
        WHERE ingested_at >= NOW() - INTERVAL '6 hours'
        ORDER BY ingested_at DESC
    """)

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    if not rows:
        print("No hay datos nuevos en bronze.weather_raw")
        return

    print(f"Registros bronze a procesar: {len(rows)}")

    # ─────────────────────────────────────────────
    # 2. TRANSFORMACIÓN / FLATTEN JSON
    # ─────────────────────────────────────────────
    registros_silver = []

    for row in rows:

        ciudad = row.ciudad
        ingested_at = row.ingested_at

        try:
            payload = json.loads(row.api_response)
        except Exception as e:
            print(f"[WARN] JSON inválido en {ciudad}: {e}")
            continue

        daily = payload.get("daily", {})

        fechas = daily.get("time", [])
        if not fechas:
            print(f"[WARN] Sin fechas en {ciudad}")
            continue

        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        precip   = daily.get("precipitation_sum", [])

        for i, fecha in enumerate(fechas):

            try:
                obs_date = datetime.strptime(fecha, "%Y-%m-%d").date()
            except ValueError:
                print(f"[WARN] Fecha inválida {fecha} en {ciudad}")
                continue

            tmax = _safe_float(temp_max[i] if i < len(temp_max) else None)
            tmin = _safe_float(temp_min[i] if i < len(temp_min) else None)
            prcp = _safe_float(precip[i] if i < len(precip) else None)

            # filtro básico de calidad
            if tmax is None and tmin is None:
                continue

            registros_silver.append({
                "city": ciudad,
                "observation_time": obs_date,
                "temperature_max": tmax,
                "temperature_min": tmin,
                "precipitation": prcp,
                "ingested_at": ingested_at
            })

    if not registros_silver:
        print("No se generaron registros silver válidos")
        return

    df = pd.DataFrame(registros_silver)

    # ─────────────────────────────────────────────
    # 3. DEDUPLICADO
    # ─────────────────────────────────────────────
    df = df.drop_duplicates(
        subset=["city", "observation_time"],
        keep="first"
    )

    # ─────────────────────────────────────────────
    # 4. ESCRITURA EN SILVER
    # ─────────────────────────────────────────────
    df.to_sql(
        name="weather",
        schema="silver",
        con=engine,
        if_exists="append",
        index=False
    )

    print(f"Se insertaron {len(df)} registros en silver.weather")


# ─────────────────────────────────────────────
# DAG
# ─────────────────────────────────────────────
with DAG(
    dag_id="openmeteo_silver",
    start_date=datetime(2026, 6, 1),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
    doc_md="""
    ### SILVER - OpenMeteo Weather Pipeline

    Transforma datos desde `bronze.weather_raw`:

    - Parseo de JSON
    - Flatten de daily forecast
    - Conversión de fechas
    - Casting seguro a float
    - Eliminación de registros inválidos
    - Deduplicación por ciudad + fecha
    """,
) as dag:

    transformar_silver_task = PythonOperator(
        task_id="transformar_silver",
        python_callable=transformar_silver,
    )