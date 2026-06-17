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
    """Convierte a float o retorna None si el valor es inválido."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def transformar_silver():
    engine = _get_engine()

    # ── 1. Leer los registros bronze que todavía no fueron procesados ──────────
    # Usamos ingested_at para traer solo la última carga (la de hoy).
    # Si querés reprocesar todo, quitá el WHERE.
    query = text("""
        SELECT id, ciudad, api_response, ingested_at
        FROM bronze.weather_raw
        WHERE DATE(ingested_at) = CURRENT_DATE
        ORDER BY ingested_at DESC
    """)

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    if not rows:
        print("No hay registros nuevos en bronze.weather_raw para hoy. Saliendo.")
        return

    print(f"Registros bronze a procesar: {len(rows)}")

    # ── 2. Parsear y aplanar ───────────────────────────────────────────────────
    registros_silver = []

    for row in rows:
        ciudad = row.ciudad
        ingested_at = row.ingested_at

        try:
            payload = json.loads(row.api_response)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"[WARN] No se pudo parsear JSON para {ciudad}: {e}")
            continue

        daily = payload.get("daily", {})
        fechas = daily.get("time", [])

        if not fechas:
            print(f"[WARN] Sin fechas en la respuesta de {ciudad}. Se omite.")
            continue

        temp_max_list  = daily.get("temperature_2m_max", [None] * len(fechas))
        temp_min_list  = daily.get("temperature_2m_min", [None] * len(fechas))
        precip_list    = daily.get("precipitation_sum",  [None] * len(fechas))
        wind_list      = daily.get("windspeed_10m_max",  [None] * len(fechas))

        # Humedad: puede venir como diario o como promedio horario calculado aparte
        humid_list     = daily.get("relativehumidity_2m_mean", [None] * len(fechas))

        for i, fecha_str in enumerate(fechas):
            # Validación: descartamos filas donde temp_max Y temp_min son nulos
            t_max = _safe_float(temp_max_list[i] if i < len(temp_max_list) else None)
            t_min = _safe_float(temp_min_list[i] if i < len(temp_min_list) else None)

            if t_max is None and t_min is None:
                print(f"[WARN] Fila sin temperatura para {ciudad} en {fecha_str}. Se omite.")
                continue

            try:
                observation_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                print(f"[WARN] Fecha inválida '{fecha_str}' para {ciudad}. Se omite.")
                continue

            registros_silver.append({
                "city":             ciudad,
                "observation_time": observation_date,
                "temperature_max":  t_max,
                "temperature_min":  t_min,
                "precipitation":    _safe_float(precip_list[i] if i < len(precip_list) else None),
                "humidity":         _safe_float(humid_list[i]  if i < len(humid_list)  else None),
                "wind_speed":       _safe_float(wind_list[i]   if i < len(wind_list)   else None),
                "ingested_at":      ingested_at,
            })

    if not registros_silver:
        print("No se generaron registros silver válidos.")
        return

    df = pd.DataFrame(registros_silver)

    # ── 3. Eliminar duplicados dentro del mismo batch ─────────────────────────
    # En caso de que bronze tenga varias cargas del mismo día, nos quedamos con
    # la primera ocurrencia por (city, observation_time).
    df = df.drop_duplicates(subset=["city", "observation_time"], keep="first")

    # ── 4. Eliminar de silver los registros que vamos a reemplazar ────────────
    # Evita duplicados si el DAG se re-ejecuta en el mismo día.
    ciudades     = df["city"].unique().tolist()
    fechas_unicas = df["observation_time"].unique().tolist()

    with engine.connect() as conn:
        conn.execute(
            text("""
                DELETE FROM silver.weather
                WHERE city = ANY(:ciudades)
                  AND observation_time = ANY(:fechas)
            """),
            {"ciudades": ciudades, "fechas": [str(f) for f in fechas_unicas]},
        )
        conn.commit()

    # ── 5. Insertar en silver ─────────────────────────────────────────────────
    df.to_sql(
        name="weather",
        con=engine,
        schema="silver",
        if_exists="append",
        index=False,
    )

    print(f"Se insertaron {len(df)} registros en silver.weather")
    print(df[["city", "observation_time", "temperature_max", "temperature_min"]].to_string(index=False))


# ── DAG ───────────────────────────────────────────────────────────────────────
with DAG(
    dag_id="openmeteo_silver",
    start_date=datetime(2026, 6, 1),
    schedule="@daily",
    catchup=False,
    is_paused_upon_creation=False,
    doc_md="""
    ### Silver – Open-Meteo
    Lee `bronze.weather_raw`, parsea el JSON, limpia y normaliza los datos,
    y escribe el resultado en `silver.weather`.

    **Transformaciones aplicadas**
    - Extracción de campos desde el JSON (`daily.*`)
    - Conversión de fechas a `DATE`
    - Casteo seguro a `FLOAT` (valores inválidos → NULL)
    - Eliminación de filas sin temperatura
    - Deduplicación por `(city, observation_time)` antes de insertar
    """,
) as dag:

    transformar_datos = PythonOperator(
        task_id="transformar_silver",
        python_callable=transformar_silver,
    )