from datetime import datetime, timezone
import json
import os
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

# El Asset que publica Bronze (lo escucha para arrancar)
BRONZE_ASSET = Asset(name="g09_bronze_open_meteo_raw")
# El Asset que va a publicar Silver (para que arranque Gold)
SILVER_ASSET = Asset(name="g09_silver_open_meteo_clean")

def get_database_engine():
    database_url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ.get("SOURCE_DB_USER", "admin"),
        password=os.environ.get("SOURCE_DB_PASS", "admin"),
        host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
        port=int(os.getenv("SOURCE_DB_PORT", "5432")),
        database=os.environ.get("SOURCE_DB_NAME", "InfraCienciaDatos"),
    )
    return create_engine(database_url, pool_pre_ping=True)

@dag(
    dag_id="g09_silver_open_meteo",
    description="Limpieza y aplanado de datos Open-Meteo",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[BRONZE_ASSET], # <-- Se despierta solo cuando Bronze termina
    catchup=False,
    tags=["g09", "silver"],
)
def g09_silver_open_meteo():

    @task(outlets=[SILVER_ASSET]) # <-- Al terminar, dispara Gold
    def clean_daily_data():
        engine = get_database_engine()

        # 1. Leer Bronze
        print("Leyendo datos crudos de Bronze...")
        query = "SELECT city, region_type, response_payload FROM bronze.open_meteo_raw"
        df_raw = pd.read_sql(query, engine)

        registros = []
        for _, row in df_raw.iterrows():
            payload = row['response_payload'] if isinstance(row['response_payload'], dict) else json.loads(row['response_payload'])
            
            # Tu compañero guarda datos diarios en el JSON
            daily = payload.get('daily', {})
            times = daily.get('time', [])

            # Armamos una fila por cada día
            for i in range(len(times)):
                registros.append({
                    'ciudad': row['city'],
                    'region': row['region_type'],
                    'fecha': times[i],
                    'temp_media_c': daily.get('temperature_2m_mean', [None]*len(times))[i],
                    'temp_max_c': daily.get('temperature_2m_max', [None]*len(times))[i],
                    'temp_min_c': daily.get('temperature_2m_min', [None]*len(times))[i],
                    'lluvia_mm': daily.get('precipitation_sum', [None]*len(times))[i],
                    'viento_kmh': daily.get('wind_speed_10m_mean', [None]*len(times))[i],
                })

        df_clean = pd.DataFrame(registros)
        
        # Convertimos a fecha real de SQL
        if not df_clean.empty:
            df_clean['fecha'] = pd.to_datetime(df_clean['fecha']).dt.date

            # 2. Guardar en Silver
            print(f"Guardando {len(df_clean)} registros en Silver...")
            with engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
                # Usamos if_exists='replace' para no duplicar si corremos de nuevo
                df_clean.to_sql('clima_diario_clean', engine, schema='silver', if_exists='replace', index=False)

        engine.dispose()
        print("¡Capa Silver completada!")

    clean_daily_data()

g09_silver_open_meteo()