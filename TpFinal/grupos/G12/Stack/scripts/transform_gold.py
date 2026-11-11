import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = Path('.env')
load_dotenv(dotenv_path=env_path)

DB_USER = os.getenv('SOURCE_DB_USER', 'admin')
DB_PASS = os.getenv('SOURCE_DB_PASS', 'admin')
DB_NAME = os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')
DB_HOST = os.getenv('SOURCE_DB_HOST', 'localhost')
DB_PORT = int(os.getenv('SOURCE_DB_PORT', 5432))

DATABASE_URL = f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(DATABASE_URL)

def procesar_gold_usgs():
    sql_gold = """
    DROP TABLE IF EXISTS gold.dim_region;
    CREATE TABLE gold.dim_region AS
    SELECT 
        ROW_NUMBER() OVER (ORDER BY region) AS region_id,
        region
    FROM (SELECT DISTINCT region FROM silver.earthquakes) sub;

    DROP TABLE IF EXISTS gold.fact_sismos_diarios;
    CREATE TABLE gold.fact_sismos_diarios AS
    SELECT 
        s.event_date,
        d.region_id,
        COUNT(s.earthquake_id) AS cantidad_sismos,
        ROUND(AVG(s.magnitude), 2) AS magnitud_promedio,
        ROUND(MAX(s.magnitude), 2) AS magnitud_maxima,
        SUM(s.energia_joules) AS energia_total_joules,
        SUM(s.tsunami_alert) AS alertas_tsunami
    FROM silver.earthquakes s
    JOIN gold.dim_region d ON s.region = d.region
    GROUP BY s.event_date, d.region_id;

    DROP TABLE IF EXISTS gold.agg_ranking_zonas;
    CREATE TABLE gold.agg_ranking_zonas AS
    SELECT 
        region,
        COUNT(earthquake_id) AS total_sismos,
        ROUND(AVG(magnitude), 2) AS magnitud_promedio,
        ROUND(MAX(magnitude), 2) AS magnitud_maxima,
        ROUND(AVG(depth_km), 2) AS profundidad_promedio_km,
        SUM(tsunami_alert) AS total_alertas_tsunami
    FROM silver.earthquakes
    GROUP BY region
    ORDER BY total_sismos DESC;
    """

    # Separamos por ';' y ejecutamos uno por uno
    comandos = [cmd.strip() for cmd in sql_gold.split(';') if cmd.strip()]
    
    with engine.begin() as conn:
        for cmd in comandos:
            conn.execute(text(cmd))

    with engine.connect() as conn:
        regiones = conn.execute(text("SELECT COUNT(*) FROM gold.dim_region")).scalar()
        hechos = conn.execute(text("SELECT COUNT(*) FROM gold.fact_sismos_diarios")).scalar()
        ranking = conn.execute(text("SELECT COUNT(*) FROM gold.agg_ranking_zonas")).scalar()

    print(f'🥇 Gold procesado correctamente vía SQL:')
    print(f'  - dim_region: {regiones} filas')
    print(f'  - fact_sismos_diarios: {hechos} filas')
    print(f'  - agg_ranking_zonas: {ranking} filas')

if __name__ == '__main__':
    procesar_gold_usgs()