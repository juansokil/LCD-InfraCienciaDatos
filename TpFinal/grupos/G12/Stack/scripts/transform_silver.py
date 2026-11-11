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

def procesar_silver_usgs():
    sql_silver = """
    DROP TABLE IF EXISTS silver.earthquakes;
    
    CREATE TABLE silver.earthquakes AS
    WITH parsed_data AS (
        SELECT 
            id AS earthquake_id,
            NULLIF(properties::jsonb ->> 'mag', '')::numeric AS magnitude,
            properties::jsonb ->> 'place' AS place,
            COALESCE(NULLIF(properties::jsonb ->> 'tsunami', '')::integer, 0) AS tsunami_alert,
            to_timestamp((properties::jsonb ->> 'time')::numeric / 1000) AS event_timestamp,
            (geometry::jsonb -> 'coordinates' ->> 0)::numeric AS longitude,
            (geometry::jsonb -> 'coordinates' ->> 1)::numeric AS latitude,
            (geometry::jsonb -> 'coordinates' ->> 2)::numeric AS depth_km,
            ingested_at
        FROM bronze.raw_earthquakes
    ),
    deduplicated AS (
        SELECT *, ROW_NUMBER() OVER(PARTITION BY earthquake_id ORDER BY ingested_at DESC) as rn
        FROM parsed_data
    )
    SELECT 
        earthquake_id,
        magnitude,
        CASE 
            WHEN magnitude IS NULL THEN 'Desconocida'
            WHEN magnitude < 3.0 THEN 'Menor'
            WHEN magnitude < 4.5 THEN 'Leve'
            WHEN magnitude < 6.0 THEN 'Moderado'
            ELSE 'Fuerte / Mayor'
        END AS escala_magnitud,
        CASE 
            WHEN magnitude > 0 THEN power(10, 4.8 + 1.5 * magnitude)
            ELSE NULL
        END AS energia_joules,
        place,
        TRIM(SPLIT_PART(place, ',', 1)) AS place_detail,
        CASE 
            WHEN position(',' in place) > 0 THEN TRIM(regexp_replace(place, '^.*,\\s*', ''))
            ELSE place
        END AS region,
        tsunami_alert,
        event_timestamp,
        event_timestamp::date AS event_date,
        longitude,
        latitude,
        depth_km,
        ingested_at,
        NOW() AS processed_at
    FROM deduplicated
    WHERE rn = 1;
    """

    # LA MAGIA ESTÁ ACÁ: Separamos por ';' y ejecutamos uno por uno
    comandos = [cmd.strip() for cmd in sql_silver.split(';') if cmd.strip()]
    
    with engine.begin() as conn:  # engine.begin() hace el commit automático
        for cmd in comandos:
            conn.execute(text(cmd))

    with engine.connect() as conn:
        resultado = conn.execute(text("SELECT COUNT(*) FROM silver.earthquakes")).scalar()

    print(f'🥈 Silver procesado exitosamente vía SQL: {resultado} filas en silver.earthquakes')

if __name__ == '__main__':
    procesar_silver_usgs()