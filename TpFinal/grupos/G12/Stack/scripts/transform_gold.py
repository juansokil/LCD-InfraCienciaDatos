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
    -- En Gold solo analizamos sismos: todo filtra tipo_evento = 'earthquake'.

    -- Limpieza: borra las tablas del modelo viejo si quedaron de corridas anteriores
    DROP TABLE IF EXISTS gold.fact_sismos_diarios;
    DROP TABLE IF EXISTS gold.agg_ranking_zonas;
    DROP TABLE IF EXISTS gold.dim_region;

    -- ===== Modelo estrella: fact_terremoto + 4 dimensiones =====
    -- Primero la fact, porque tiene claves foraneas hacia las dimensiones
    DROP TABLE IF EXISTS gold.fact_terremoto;
    DROP TABLE IF EXISTS gold.dim_fecha;
    DROP TABLE IF EXISTS gold.dim_ubicacion;
    DROP TABLE IF EXISTS gold.dim_magnitud;
    DROP TABLE IF EXISTS gold.dim_alerta;

    -- dim_fecha: la clave es la fecha como numero AAAAMMDD (ej. 20261112)
    CREATE TABLE gold.dim_fecha AS
    SELECT DISTINCT
        to_char(fecha, 'YYYYMMDD')::integer AS fecha_id,
        fecha,
        EXTRACT(YEAR FROM fecha)::integer   AS anio,
        EXTRACT(MONTH FROM fecha)::integer  AS mes,
        EXTRACT(DAY FROM fecha)::integer    AS dia,
        EXTRACT(ISODOW FROM fecha)::integer AS dia_semana
    FROM silver.earthquakes
    WHERE fecha IS NOT NULL
      AND tipo_evento = 'earthquake';

    -- dim_ubicacion: cada combinacion de region + ubicacion
    CREATE TABLE gold.dim_ubicacion AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY region, ubicacion) AS id_ubicacion,
        region,
        ubicacion
    FROM (
        SELECT DISTINCT region, ubicacion
        FROM silver.earthquakes
        WHERE tipo_evento = 'earthquake'
    ) t;

    -- dim_magnitud: cada tipo de magnitud (mb, ml, mww, ...)
    CREATE TABLE gold.dim_magnitud AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY tipo_magnitud) AS id_magnitud,
        tipo_magnitud
    FROM (
        SELECT DISTINCT COALESCE(tipo_magnitud, 'unknown') AS tipo_magnitud
        FROM silver.earthquakes
        WHERE tipo_evento = 'earthquake'
    ) t;

    -- dim_alerta: lista fija con los niveles del USGS + unknown para los nulos
    CREATE TABLE gold.dim_alerta AS
    SELECT *
    FROM (VALUES
        (1, 'green'),
        (2, 'yellow'),
        (3, 'orange'),
        (4, 'red'),
        (5, 'unknown')
    ) AS t(id_alerta, tipo_alerta);

    -- fact_terremoto: una fila por terremoto
    CREATE TABLE gold.fact_terremoto AS
    SELECT
        s.id_sismo           AS id_terremoto,
        f.fecha_id,
        a.id_alerta,
        u.id_ubicacion,
        m.id_magnitud,
        s.magnitud,
        s.profundidad_km     AS profundidad,
        s.significancia,
        1                    AS cantidad_terremoto
    FROM silver.earthquakes s
    JOIN gold.dim_fecha f
        ON f.fecha = s.fecha
    JOIN gold.dim_alerta a
        ON a.tipo_alerta = CASE
                               WHEN s.alerta IN ('green', 'yellow', 'orange', 'red') THEN s.alerta
                               ELSE 'unknown'   -- nulo = sin dato, NO es alerta verde
                           END
    JOIN gold.dim_ubicacion u
        ON u.region IS NOT DISTINCT FROM s.region
       AND u.ubicacion IS NOT DISTINCT FROM s.ubicacion
    JOIN gold.dim_magnitud m
        ON m.tipo_magnitud = COALESCE(s.tipo_magnitud, 'unknown')
    WHERE s.tipo_evento = 'earthquake';

    -- Claves primarias y foraneas: dejan la estrella explicita en la base
    ALTER TABLE gold.dim_fecha     ADD PRIMARY KEY (fecha_id);
    ALTER TABLE gold.dim_ubicacion ADD PRIMARY KEY (id_ubicacion);
    ALTER TABLE gold.dim_magnitud  ADD PRIMARY KEY (id_magnitud);
    ALTER TABLE gold.dim_alerta    ADD PRIMARY KEY (id_alerta);
    ALTER TABLE gold.fact_terremoto ADD PRIMARY KEY (id_terremoto);
    ALTER TABLE gold.fact_terremoto ADD FOREIGN KEY (fecha_id)     REFERENCES gold.dim_fecha (fecha_id);
    ALTER TABLE gold.fact_terremoto ADD FOREIGN KEY (id_alerta)    REFERENCES gold.dim_alerta (id_alerta);
    ALTER TABLE gold.fact_terremoto ADD FOREIGN KEY (id_ubicacion) REFERENCES gold.dim_ubicacion (id_ubicacion);
    ALTER TABLE gold.fact_terremoto ADD FOREIGN KEY (id_magnitud)  REFERENCES gold.dim_magnitud (id_magnitud);
    """

    # Separamos por ';' y ejecutamos uno por uno
    comandos = [cmd.strip() for cmd in sql_gold.split(';') if cmd.strip()]
    
    with engine.begin() as conn:
        for cmd in comandos:
            conn.execute(text(cmd))

    with engine.connect() as conn:
        terremotos = conn.execute(text("SELECT COUNT(*) FROM gold.fact_terremoto")).scalar()

    print(f'🥇 Gold procesado correctamente vía SQL: {terremotos} terremotos en gold.fact_terremoto')
if __name__ == '__main__':
    procesar_gold_usgs()