"""
DAG Gold - Modelo Estrella EcoBici Buenos Aires.
Transforma y carga datos procesados desde silver.ecobici_stations hacia 
las dimensiones y tabla de hechos del esquema gold.

"""
from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
import sqlalchemy
from airflow.decorators import dag, task
from sqlalchemy import text

# URI de conexión al Data Warehouse Postgres mapeado en Docker
DB_URI = (
    "postgresql+psycopg2://"
    "admin:admin@data_warehouse:5432/InfraCienciaDatos"
)

@dag(
    dag_id="gold_ecobici",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",  # Corre sincronizado cada 15 minutos con Bronze y Silver
    catchup=False,
    is_paused_upon_creation=False,  # Activo por defecto como pide la cátedra
    tags=["prod", "gold", "modelado_dimensional", "ecobici"],
)
def gold_ecobici_pipeline():

    @task()
    def extract_silver_data() -> str:
        """Extrae los últimos datos limpios y normalizados de la capa Silver."""
        engine = sqlalchemy.create_engine(DB_URI)
        
        # Leemos los datos desde la tabla unificada de Silver
        query = """
            SELECT 
                station_id, station_name, address, slots as total_capacity,
                latitude, longitude, free_bikes, empty_slots, occupancy_ratio,
                station_timestamp
            FROM silver.ecobici_stations;
        """
        df = pd.read_sql(query, con=engine)
        
        # Guardamos temporalmente en formato JSON serializado para pasarlo por XCom
        return df.to_json(orient="records", date_format="iso")

    @task()
    def load_dim_station(json_data: str):
        """Pobla la dimensión Satélite de Estaciones (Desnormalizada/BI Friendly)."""
        df = pd.read_json(json_data, orient="records")
        if df.empty:
            return

        # Seleccionamos las columnas únicas para el catálogo de estaciones
        df_station = df[[
            "station_id", "station_name", "address", 
            "total_capacity", "latitude", "longitude"
        ]].drop_duplicates(subset=["station_id"])

        engine = sqlalchemy.create_engine(DB_URI)
        
        # Inserción idempotente con Upsert (Si la estación cambia de nombre o capacidad, se actualiza)
        with engine.begin() as conn:
            for _, row in df_station.iterrows():
                conn.execute(
                    text("""
                        INSERT INTO gold.dim_station (
                            station_id, station_name, address, total_capacity, latitude, longitude
                        ) VALUES (:station_id, :station_name, :address, :total_capacity, :latitude, :longitude)
                        ON CONFLICT (station_id) 
                        DO UPDATE SET 
                            station_name = EXCLUDED.station_name,
                            address = EXCLUDED.address,
                            total_capacity = EXCLUDED.total_capacity,
                            latitude = EXCLUDED.latitude,
                            longitude = EXCLUDED.longitude;
                    """),
                    {
                        "station_id": str(row["station_id"]),
                        "station_name": row["station_name"],
                        "address": row["address"],
                        "total_capacity": int(row["total_capacity"]),
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"])
                    }
                )

    @task()
    def load_dim_time(json_data: str):
        """Genera y puebla la dimensión de Tiempo a partir de los timestamps de los snapshots."""
        df = pd.read_json(json_data, orient="records")
        if df.empty:
            return

        # Convertimos a objeto datetime estructurado
        df["dt"] = pd.to_datetime(df["station_timestamp"])
        
        df_time = pd.DataFrame()
        df_time["full_timestamp"] = df["dt"].drop_duplicates()
        
        # Construimos los atributos derivados requeridos para analítica horaria/diaria
        df_time["hour"] = df_time["full_timestamp"].dt.hour
        df_time["minute"] = df_time["full_timestamp"].dt.minute
        
        # Mapeo del día de la semana en español para facilitar los filtros en Streamlit
        dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        df_time["day_of_week"] = df_time["full_timestamp"].dt.dayofweek.map(dias)
        df_time["is_weekend"] = df_time["full_timestamp"].dt.dayofweek.isin([5, 6])
        
        # Formato de Clave Entera Inteligente (YYYYMMDDHHMI) para evitar JOINs costosos por cadenas
        df_time["time_id"] = df_time["full_timestamp"].dt.strftime("%Y%m%d%H%M").astype(int)

        engine = sqlalchemy.create_engine(DB_URI)
        
        with engine.begin() as conn:
            for _, row in df_time.iterrows():
                conn.execute(
                    text("""
                        INSERT INTO gold.dim_time (
                            time_id, full_timestamp, hour, minute, day_of_week, is_weekend
                        ) VALUES (:time_id, :full_timestamp, :hour, :minute, :day_of_week, :is_weekend)
                        ON CONFLICT (time_id) DO NOTHING;
                    """),
                    {
                        "time_id": int(row["time_id"]),
                        "full_timestamp": row["full_timestamp"],
                        "hour": int(row["hour"]),
                        "minute": int(row["minute"]),
                        "day_of_week": row["day_of_week"],
                        "is_weekend": bool(row["is_weekend"])
                    }
                )

    @task()
    def load_fact_availability(json_data: str):
        """Puebla la Tabla de Hechos central vinculando las dimensiones mediante sus claves de negocio."""
        df = pd.read_json(json_data, orient="records")
        if df.empty:
            return

        df["dt"] = pd.to_datetime(df["station_timestamp"])
        # Re-calculamos el time_id idéntico para hacer la relación física como Clave Foránea
        df["time_id"] = df["dt"].dt.strftime("%Y%m%d%H%M").astype(int)

        engine = sqlalchemy.create_engine(DB_URI)
        
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(
                    text("""
                        INSERT INTO gold.fact_station_availability (
                            time_id, station_id, bikes_available, slots_available, occupancy_ratio
                        ) VALUES (:time_id, :station_id, :bikes_available, :slots_available, :occupancy_ratio)
                        ON CONFLICT (time_id, station_id) 
                        DO UPDATE SET 
                            bikes_available = EXCLUDED.bikes_available,
                            slots_available = EXCLUDED.slots_available,
                            occupancy_ratio = EXCLUDED.occupancy_ratio;
                    """),
                    {
                        "time_id": int(row["time_id"]),
                        "station_id": str(row["station_id"]),
                        "bikes_available": int(row["free_bikes"]),
                        "slots_available": int(row["empty_slots"]),
                        "occupancy_ratio": float(row["occupancy_ratio"])
                    }
                )

    # Definición explícita del flujo de control del Grafo Dirigido (DAG)
    raw_silver_data = extract_silver_data()
    
    task_station = load_dim_station(raw_silver_data)
    task_time = load_dim_time(raw_silver_data)
    task_fact = load_fact_availability(raw_silver_data)
    
    # Las dimensiones se deben cargar SI o SI antes que la tabla de hechos para no romper las Foreign Keys de Postgres
    [task_station, task_time] >> task_fact

gold_ecobici_dag = gold_ecobici_pipeline()