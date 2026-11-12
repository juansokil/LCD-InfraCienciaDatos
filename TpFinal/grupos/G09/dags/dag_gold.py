from datetime import datetime, timezone
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

# Escuchamos lo que publica Silver para arrancar
SILVER_ASSET = Asset(name="g09_silver_open_meteo_clean")
# Publicamos el Asset de Gold (para que el Dashboard sepa que hay datos)
GOLD_ASSET = Asset(name="g09_gold_open_meteo_star")

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
    dag_id="g09_gold_open_meteo",
    description="Modelo estrella para el Dashboard de Clima",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[SILVER_ASSET], # Se despierta solo cuando termina Silver
    catchup=False,
    tags=["g09", "gold"],
)
def g09_gold_open_meteo():

    @task(outlets=[GOLD_ASSET])
    def build_star_schema():
        engine = get_database_engine()
        
        print("Iniciando construccion del modelo estrella en Gold...")
        
        with engine.begin() as conn:
            # 1. Crear el esquema Gold
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))

            # 2. Crear Dimensión Ciudad
            conn.execute(text("DROP TABLE IF EXISTS gold.dim_ciudad CASCADE;"))
            conn.execute(text("""
                CREATE TABLE gold.dim_ciudad AS
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY ciudad) AS ciudad_id,
                    ciudad,
                    region
                FROM (SELECT DISTINCT ciudad, region FROM silver.clima_diario_clean) as sub;
            """))

            # 3. Crear Dimensión Tiempo (Fecha)
            conn.execute(text("DROP TABLE IF EXISTS gold.dim_tiempo CASCADE;"))
            conn.execute(text("""
                CREATE TABLE gold.dim_tiempo AS
                SELECT 
                    fecha AS tiempo_id,
                    EXTRACT(YEAR FROM fecha) AS anio,
                    EXTRACT(MONTH FROM fecha) AS mes,
                    EXTRACT(DAY FROM fecha) AS dia,
                    TO_CHAR(fecha, 'Month') AS nombre_mes
                FROM (SELECT DISTINCT fecha FROM silver.clima_diario_clean) as sub;
            """))

            # 4. Crear Tabla de Hechos (Fact)
            conn.execute(text("DROP TABLE IF EXISTS gold.fact_clima_diario;"))
            conn.execute(text("""
                CREATE TABLE gold.fact_clima_diario AS
                SELECT 
                    s.fecha AS tiempo_id,
                    c.ciudad_id,
                    s.temp_media_c,
                    s.temp_max_c,
                    s.temp_min_c,
                    s.lluvia_mm,
                    s.viento_kmh
                FROM silver.clima_diario_clean s
                JOIN gold.dim_ciudad c ON s.ciudad = c.ciudad;
            """))

        print("¡Modelo Estrella (Gold) creado con éxito!")
        engine.dispose()

    build_star_schema()

g09_gold_open_meteo()