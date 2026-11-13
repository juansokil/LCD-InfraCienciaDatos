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
    # Silver guarda TODOS los eventos (sismos, voladuras, explosiones, etc.).
    # El filtro de solo sismos se hace en Gold.
    sql_silver = """
    DROP TABLE IF EXISTS silver.earthquakes;

    CREATE TABLE silver.earthquakes AS
    WITH extraido AS (
        -- 1) Columnas utiles del JSON de bronze, renombradas al espanol
        SELECT
            id                                                     AS id_sismo,
            NULLIF(properties::jsonb ->> 'mag', '')::numeric       AS magnitud,
            properties::jsonb ->> 'place'                          AS lugar,
            (properties::jsonb ->> 'time')::bigint                 AS tiempo_ms,
            (properties::jsonb ->> 'updated')::bigint              AS actualizado_ms,
            properties::jsonb ->> 'magType'                        AS tipo_magnitud,
            properties::jsonb ->> 'type'                           AS tipo_evento,
            properties::jsonb ->> 'title'                          AS titulo,
            COALESCE(NULLIF(properties::jsonb ->> 'tsunami', '')::integer, 0) AS alerta_tsunami,
            properties::jsonb ->> 'alert'                          AS alerta,
            NULLIF(properties::jsonb ->> 'sig', '')::integer       AS significancia,
            -- 2) geometry.coordinates viene como [longitud, latitud, profundidad]
            (geometry::jsonb -> 'coordinates' ->> 0)::numeric      AS longitud,
            (geometry::jsonb -> 'coordinates' ->> 1)::numeric      AS latitud,
            (geometry::jsonb -> 'coordinates' ->> 2)::numeric      AS profundidad_km,
            ingested_at                                            AS fecha_ingesta
        FROM bronze.raw_earthquakes
    ),
    sin_duplicados AS (
        -- 3) Un registro por sismo: la version mas nueva segun el USGS
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY id_sismo
                ORDER BY actualizado_ms DESC, fecha_ingesta DESC
            ) AS rn
        FROM extraido
    )
    SELECT
        id_sismo,
        titulo,
        magnitud,
        tipo_magnitud,
        CASE
            WHEN magnitud IS NULL THEN 'Desconocida'
            WHEN magnitud < 3.0 THEN 'Menor'
            WHEN magnitud < 4.5 THEN 'Leve'
            WHEN magnitud < 6.0 THEN 'Moderado'
            ELSE 'Fuerte / Mayor'
        END                                                        AS escala_magnitud,
        CASE WHEN magnitud > 0 THEN power(10, 4.8 + 1.5 * magnitud) END AS energia_joules,
        lugar,
        -- 4) lugar = "121 km SE of Atka, Alaska": ubicacion antes de la ultima coma, region despues
        CASE
            WHEN position(',' in lugar) > 0 THEN TRIM(regexp_replace(lugar, ',[^,]*$', ''))
        END                                                        AS ubicacion,
        TRIM(regexp_replace(lugar, '^.*,', ''))                    AS region,
        latitud,
        longitud,
        profundidad_km,
        alerta_tsunami,
        alerta,
        significancia,
        -- 5) Fechas: la API manda milisegundos. Las dejamos explicitamente en UTC
        to_timestamp(tiempo_ms / 1000.0) AT TIME ZONE 'UTC'        AS fecha_hora_utc,
        (to_timestamp(tiempo_ms / 1000.0) AT TIME ZONE 'UTC')::date AS fecha,
        to_timestamp(actualizado_ms / 1000.0) AT TIME ZONE 'UTC'   AS actualizado_utc,
        tipo_evento,
        fecha_ingesta,
        NOW()                                                      AS fecha_procesado
    FROM sin_duplicados
    WHERE rn = 1
    """

    # Separamos por ';' y ejecutamos uno por uno
    comandos = [cmd.strip() for cmd in sql_silver.split(';') if cmd.strip()]

    with engine.begin() as conn:  # engine.begin() hace el commit automático
        for cmd in comandos:
            conn.execute(text(cmd))

    with engine.connect() as conn:
        resultado = conn.execute(text("SELECT COUNT(*) FROM silver.earthquakes")).scalar()

    print(f'🥈 Silver procesado exitosamente vía SQL: {resultado} filas en silver.earthquakes')


if __name__ == "__main__":
    procesar_silver_usgs()