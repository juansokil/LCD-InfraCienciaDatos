from datetime import datetime, timezone
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from airflow.sdk import dag, task, Asset

# Escuchamos lo que publica Silver
SILVER_ASSET = Asset(name="g09_silver_open_meteo_clean")
# Publicamos el Asset de Gold
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
    description="Modelo estrella para el Dashboard",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=[SILVER_ASSET], 
    catchup=False,
    tags=["g09", "gold"],
)
def g09_gold_open_meteo():

    @task(outlets=[GOLD_ASSET])
    def build_star_schema():
        engine = get_database_engine()
        
        print("Iniciando construccion del modelo estrella...")
        
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))

            # 1. DIMENSION CIUDAD
            # Hacemos DROP porque las dimensiones son chicas y se pueden recalcular enteras
            conn.execute(text("DROP TABLE IF EXISTS gold.dim_ciudad CASCADE;"))
            conn.execute(text("""
                CREATE TABLE gold.dim_ciudad AS
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY ciudad) AS ciudad_id,
                    ciudad,
                    region
                FROM (SELECT DISTINCT ciudad, region FROM silver.clima_pronostico) as sub;
            """))

            # 2. DIMENSION TIEMPO
            conn.execute(text("DROP TABLE IF EXISTS gold.dim_tiempo CASCADE;"))
            conn.execute(text("""
                CREATE TABLE gold.dim_tiempo AS
                SELECT 
                    fecha AS tiempo_id,
                    EXTRACT(YEAR FROM fecha) AS anio,
                    EXTRACT(MONTH FROM fecha) AS mes,
                    EXTRACT(DAY FROM fecha) AS dia,
                    TO_CHAR(fecha, 'Month') AS nombre_mes
                FROM (SELECT DISTINCT fecha_pronostico AS fecha FROM silver.clima_pronostico) as sub;
            """))

            # 3. TABLA DE HECHOS (La magia para que no se dupliquen los pronosticos)
            # Usamos ROW_NUMBER para quedarnos SOLO con el pronostico mas nuevo (la ultima ingesta)
            conn.execute(text("DROP TABLE IF EXISTS gold.fact_clima_diario;"))
            conn.execute(text("""
                CREATE TABLE gold.fact_clima_diario AS
                WITH PronosticoReciente AS (
                    SELECT *, 
                           ROW_NUMBER() OVER(
                               PARTITION BY ciudad, fecha_pronostico 
                               ORDER BY fecha_hora_ingesta DESC
                           ) as rn
                    FROM silver.clima_pronostico
                )
                SELECT 
                    p.fecha_pronostico AS tiempo_id,
                    c.ciudad_id,
                    p.temp_media_c,
                    p.temp_max_c,
                    p.temp_min_c,
                    p.lluvia_mm,
                    p.viento_kmh
                FROM PronosticoReciente p
                JOIN gold.dim_ciudad c ON p.ciudad = c.ciudad
                WHERE p.rn = 1; -- Solo la version mas nueva
            """))

        print("¡Modelo Estrella (Gold) creado con exito!")
        engine.dispose()

    build_star_schema()

g09_gold_open_meteo()