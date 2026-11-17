from datetime import datetime, timezone
import json
import os
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

# Asset que publica Bronze (lo escucha para arrancar)
BRONZE_ASSET = Asset(name="g09_bronze_open_meteo_raw")
# Asset que publica Silver (para que arranque Gold)
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
    description="Limpieza, separacion de actual/forecast y normalizacion",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[BRONZE_ASSET], # Se despierta solo cuando Bronze termina
    catchup=False,
    tags=["g09", "silver"],
)
def g09_silver_open_meteo():

    @task(outlets=[SILVER_ASSET]) # Al terminar, dispara Gold
    def clean_and_split_data():
        engine = get_database_engine()

        # 1. Leer de Bronze. (Traemos las ultimas 2 horas para no reprocesar todo el historial en cada corrida)
        print("Leyendo datos crudos de Bronze...")
        query = """
            SELECT city, region_type, response_payload, ingested_at 
            FROM bronze.open_meteo_raw 
            WHERE ingested_at >= NOW() - INTERVAL '2 hours'
        """
        df_raw = pd.read_sql(query, engine)
        
        if df_raw.empty:
            print("No hay datos nuevos en Bronze. Saliendo...")
            return

        registros_actual = []
        registros_pronostico = []

        # 2. Procesar cada JSON
        for _, row in df_raw.iterrows():
            payload = row['response_payload'] if isinstance(row['response_payload'], dict) else json.loads(row['response_payload'])
            hora_ingesta = row['ingested_at']

            # A. Separar CLIMA ACTUAL (Medicion Real)
            current = payload.get('current', {})
            if current:
                registros_actual.append({
                    'ciudad': row['city'],
                    'region': row['region_type'],
                    'fecha_hora_ingesta': hora_ingesta,
                    'temp_actual_c': current.get('temperature_2m'),
                    'viento_actual_kmh': current.get('wind_speed_10m'),
                    'lluvia_actual_mm': current.get('precipitation')
                })

            # B. Separar PRONOSTICO (Forecast 7 dias)
            daily = payload.get('daily', {})
            times = daily.get('time', [])
            for i in range(len(times)):
                registros_pronostico.append({
                    'ciudad': row['city'],
                    'region': row['region_type'],
                    'fecha_pronostico': times[i],
                    'temp_media_c': daily.get('temperature_2m_mean', [None]*len(times))[i],
                    'temp_max_c': daily.get('temperature_2m_max', [None]*len(times))[i],
                    'temp_min_c': daily.get('temperature_2m_min', [None]*len(times))[i],
                    'lluvia_mm': daily.get('precipitation_sum', [None]*len(times))[i],
                    'viento_kmh': daily.get('wind_speed_10m_mean', [None]*len(times))[i],
                    'fecha_hora_ingesta': hora_ingesta
                })

        # 3. Guardar en tablas (usando APPEND)
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
            
            if registros_actual:
                df_actual = pd.DataFrame(registros_actual)
                df_actual.to_sql('clima_actual', engine, schema='silver', if_exists='append', index=False)
                print(f"Guardados {len(df_actual)} registros en silver.clima_actual")

            if registros_pronostico:
                df_pronostico = pd.DataFrame(registros_pronostico)
                df_pronostico['fecha_pronostico'] = pd.to_datetime(df_pronostico['fecha_pronostico']).dt.date
                df_pronostico.to_sql('clima_pronostico', engine, schema='silver', if_exists='append', index=False)
                print(f"Guardados {len(df_pronostico)} registros en silver.clima_pronostico")

        print("¡Capa Silver completada!")
        engine.dispose()

    clean_and_split_data()

g09_silver_open_meteo()