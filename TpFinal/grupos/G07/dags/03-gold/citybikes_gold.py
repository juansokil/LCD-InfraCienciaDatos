"""
DAG Gold: Modelo analítico para CityBikes / EcoBici

Objetivo:
Construir tablas Gold orientadas al dashboard en Streamlit y a preguntas de negocio
sobre disponibilidad, ocupación y estaciones críticas.

Modelo propuesto:
- gold.dim_time
- gold.dim_estacion
- gold.dim_zona
- gold.fact_ocupacion_por_hora
- gold.fact_estado_actual_estacion

Este DAG separa dos responsabilidades:
1. Crear las tablas Gold a partir de un contrato YAML.
2. Poblar las tablas Gold con transformaciones desde Silver.
"""

from datetime import datetime
import os
from pathlib import Path

import yaml
from airflow.sdk import dag, task
import sqlalchemy


# =====================================================
# CONTRATO RUTA
# =====================================================

CONTRACT_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "data",
    "contracts",
    "gold_contracts.yaml"
))

# Umbrales operativos para clasificar estaciones según proporción de bicicletas disponibles.
# - menor a 40%: estación de devolución
# - entre 40% y 60%: estación equilibrada
# - mayor a 60%: estación de alquiler
UMBRAL_DEVOLUCION = 40
UMBRAL_ALQUILER = 60


# =====================================================
# FUNCIONES AUXILIARES
# =====================================================

def get_engine():
    DB_URI = (
        f"postgresql+psycopg2://"
        f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
        f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
        f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
        f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
    )
    return sqlalchemy.create_engine(DB_URI)


def cargar_contrato(path: Path) -> dict:
    """Lee el contrato YAML de Gold."""
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def construir_create_table_sql(table_contract: dict) -> str:
    """
    Construye una sentencia CREATE TABLE a partir de un contrato YAML.

    Formato esperado del contrato:
    - schema
    - table
    - columns: [{name, type, nullable, description}]
    - primary_key: [columna_1, columna_2, ...]
    """
    schema = table_contract["schema"]
    table = table_contract["table"]
    columns = table_contract["columns"]
    primary_key = table_contract.get("primary_key", [])

    column_defs = []
    for column in columns:
        name = column["name"]
        data_type = column["type"]
        nullable = column.get("nullable", True)
        not_null = " NOT NULL" if nullable is False else ""
        column_defs.append(f"{name} {data_type}{not_null}")

    if primary_key:
        pk_cols = ", ".join(primary_key)
        column_defs.append(f"PRIMARY KEY ({pk_cols})")

    column_defs_sql = ",\n            ".join(column_defs)

    return f"""
    CREATE TABLE IF NOT EXISTS {schema}.{table} (
            {column_defs_sql}
    );
    """


# =====================================================
# DAG
# =====================================================

@dag(
    dag_id="gold_citybikes",
    description="Construcción de tablas Gold para dashboard operativo de CityBikes/EcoBici",
    start_date=datetime(2024, 1, 1),
    schedule="2-59/5 * * * *",
    is_paused_upon_creation=False,
    catchup=False,
    tags=["citybikes", "gold", "dashboard", "streamlit"],
)
def gold_citybikes():
    """DAG para construir el esquema Gold de CityBikes."""

    @task
    def crear_tablas_desde_contrato():
        """
        Crea el schema Gold y las tablas definidas en gold_contracts.yaml.

        El contrato define estructura, tipos de datos, nulabilidad y claves primarias.
        La lógica de negocio queda en las tareas de carga.
        """
        contrato = cargar_contrato(CONTRACT_PATH)
        engine = get_engine()

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS gold;"))

            for table_contract in contrato["tables"]:
                create_sql = construir_create_table_sql(table_contract)
                conn.execute(sqlalchemy.text(create_sql))

    @task
    def cargar_dim_time():
        """
        Carga la dimensión temporal.

        Granularidad:
        - una fila por fecha y hora observada en Silver.
        """
        engine = get_engine()

        sql = """
        TRUNCATE TABLE gold.dim_time;

        INSERT INTO gold.dim_time (
            time_id,
            fecha,
            hora,
            dia_semana,
            nombre_dia,
            mes,
            nombre_mes,
            anio
        )
        SELECT DISTINCT
            TO_CHAR(ts::timestamp, 'YYYYMMDDHH24')::BIGINT AS time_id,
            DATE(ts::timestamp) AS fecha,
            EXTRACT(HOUR FROM ts::timestamp)::INTEGER AS hora,
            EXTRACT(DOW FROM ts::timestamp)::INTEGER AS dia_semana,
            TRIM(TO_CHAR(ts::timestamp, 'Day')) AS nombre_dia,
            EXTRACT(MONTH FROM ts::timestamp)::INTEGER AS mes,
            TRIM(TO_CHAR(ts::timestamp, 'Month')) AS nombre_mes,
            EXTRACT(YEAR FROM ts::timestamp)::INTEGER AS anio
        FROM silver.station_availability
        WHERE ts IS NOT NULL;
        """

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(sql))

    @task
    def cargar_dim_zona():
        """
        Carga la dimensión de zona.

        Si Silver todavía no tiene enriquecimiento geográfico completo,
        se asigna una zona genérica.
        """
        engine = get_engine()

        sql = """
        TRUNCATE TABLE gold.dim_zona CASCADE;

        INSERT INTO gold.dim_zona (
            zona_id,
            barrio,
            comuna
        )
        SELECT DISTINCT
            CONCAT(
                COALESCE(comuna::text, 'sin_comuna'),
                '_',
                COALESCE(LOWER(REPLACE(barrio, ' ', '_')), 'sin_barrio')
            ) AS zona_id,
            barrio,
            comuna
        FROM silver.stations
        WHERE station_id IS NOT NULL;
        """

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(sql))

    @task
    def cargar_dim_estacion():
        """
        Carga la dimensión de estaciones.

        Contiene atributos descriptivos relativamente estables:
        nombre, coordenadas, capacidad, zona y estado activo/inactivo.
        """
        engine = get_engine()

        sql = """
        TRUNCATE TABLE gold.dim_estacion CASCADE;

        INSERT INTO gold.dim_estacion (
            station_id,
            network_id,
            name,
            latitude,
            longitude,
            barrio,
            comuna,
            zona_id
        )
        SELECT DISTINCT ON (station_id)
            station_id,
            network_id,
            name,
            latitude,
            longitude,
            barrio,
            comuna,
            CONCAT(
                COALESCE(comuna::text, 'sin_comuna'),
                '_',
                COALESCE(LOWER(REPLACE(barrio, ' ', '_')), 'sin_barrio')
            ) AS zona_id
        FROM silver.stations
        WHERE station_id IS NOT NULL
        ORDER BY station_id;
        """

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(sql))

    @task
    def cargar_fact_ocupacion_por_hora():
        """
        Carga la fact table principal de Gold.

        Granularidad:
        - una fila por estación, fecha y hora.

        Preguntas que responde:
        - ¿Cómo varía la disponibilidad a lo largo del día?
        - ¿Qué estaciones presentan saturación o desabastecimiento?
        - ¿Qué zonas requieren más atención?
        - ¿Qué estaciones son recurrentemente problemáticas?
        """
        engine = get_engine()

        sql = f"""
        TRUNCATE TABLE gold.fact_ocupacion_por_hora;

        INSERT INTO gold.fact_ocupacion_por_hora (
            time_id,
            station_id,
            network_id,
            zona_id,
            free_bikes_promedio,
            empty_slots_promedio,
            free_bikes_pct_promedio,
            free_bikes_pct_maxima,
            free_bikes_pct_minima,
            cantidad_observaciones,
            porcentaje_tiempo_devolucion,
            porcentaje_tiempo_equilibrada,
            porcentaje_tiempo_alquiler
        )
        SELECT
            TO_CHAR(sa.ts::timestamp, 'YYYYMMDDHH24')::BIGINT AS time_id,
            sa.station_id,
            sa.network_id,
            CONCAT(
                COALESCE(st.comuna::text, 'sin_comuna'),
                '_',
                COALESCE(LOWER(REPLACE(st.barrio, ' ', '_')), 'sin_barrio')
            ) AS zona_id,
            AVG(sa.free_bikes)::NUMERIC(10, 2) AS free_bikes_promedio,
            AVG(sa.empty_slots)::NUMERIC(10, 2) AS empty_slots_promedio,
            AVG(sa.free_bikes_pct)::NUMERIC(10, 2) AS free_bikes_pct_promedio,
            MAX(sa.free_bikes_pct)::NUMERIC(10, 2) AS free_bikes_pct_maxima,
            MIN(sa.free_bikes_pct)::NUMERIC(10, 2) AS free_bikes_pct_minima,
            COUNT(*)::INTEGER AS cantidad_observaciones,
            AVG(
                CASE
                    WHEN sa.free_bikes_pct < {UMBRAL_DEVOLUCION}
                    THEN 1
                    ELSE 0
                END
            )::NUMERIC(10, 4) AS porcentaje_tiempo_devolucion,
            AVG(
                CASE
                    WHEN sa.free_bikes_pct >= {UMBRAL_DEVOLUCION}
                     AND sa.free_bikes_pct <= {UMBRAL_ALQUILER}
                    THEN 1
                    ELSE 0
                END
            )::NUMERIC(10, 4) AS porcentaje_tiempo_equilibrada,
            AVG(
                CASE
                    WHEN sa.free_bikes_pct > {UMBRAL_ALQUILER}
                    THEN 1
                    ELSE 0
                END
            )::NUMERIC(10, 4) AS porcentaje_tiempo_alquiler
        FROM silver.station_availability sa
        LEFT JOIN silver.stations st
            ON sa.station_id = st.station_id
           AND sa.network_id = st.network_id
        WHERE sa.ts IS NOT NULL
          AND sa.station_id IS NOT NULL
          AND sa.network_id IS NOT NULL
          AND sa.free_bikes_pct IS NOT NULL
        GROUP BY
            TO_CHAR(sa.ts::timestamp, 'YYYYMMDDHH24')::BIGINT,
            sa.station_id,
            sa.network_id,
            CONCAT(
                COALESCE(st.comuna::text, 'sin_comuna'),
                '_',
                COALESCE(LOWER(REPLACE(st.barrio, ' ', '_')), 'sin_barrio')
            );
        """

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(sql))

    @task
    def cargar_fact_estado_actual_estacion():
        """
        Carga una fact table con el último estado disponible por estación.

        Esta tabla alimenta principalmente el mapa operativo y los KPIs del
        estado actual de la red.
        """
        engine = get_engine()

        sql = f"""
        TRUNCATE TABLE gold.fact_estado_actual_estacion;

        INSERT INTO gold.fact_estado_actual_estacion (
            station_id,
            network_id,
            time_id,
            ts,
            timestamp_api,
            free_bikes_actuales,
            empty_slots_actuales,
            free_bikes_pct_actual,
            tipo_estacion_actual,
            estado_critico_actual
        )
        WITH ultimo_snapshot AS (
            SELECT
                sa.*,
                ROW_NUMBER() OVER (
                    PARTITION BY sa.station_id, sa.network_id
                    ORDER BY sa.ts::timestamp DESC
                ) AS rn
            FROM silver.station_availability sa
            WHERE sa.station_id IS NOT NULL
              AND sa.network_id IS NOT NULL
              AND sa.ts IS NOT NULL
        )
        SELECT
            station_id,
            network_id,
            TO_CHAR(ts::timestamp, 'YYYYMMDDHH24')::BIGINT AS time_id,
            ts,
            timestamp_api,
            free_bikes AS free_bikes_actuales,
            empty_slots AS empty_slots_actuales,
            free_bikes_pct AS free_bikes_pct_actual,
            CASE
                WHEN free_bikes_pct < {UMBRAL_DEVOLUCION}
                THEN 'Estación de devolución'
                WHEN free_bikes_pct <= {UMBRAL_ALQUILER}
                THEN 'Estación equilibrada'
                ELSE 'Estación de alquiler'
            END AS tipo_estacion_actual,
            CASE
                WHEN free_bikes_pct < {UMBRAL_DEVOLUCION}
                  OR free_bikes_pct > {UMBRAL_ALQUILER}
                THEN TRUE
                ELSE FALSE
            END AS estado_critico_actual
        FROM ultimo_snapshot
        WHERE rn = 1;
        """

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(sql))

    crear_tablas = crear_tablas_desde_contrato()

    dim_time = cargar_dim_time()
    dim_zona = cargar_dim_zona()
    dim_estacion = cargar_dim_estacion()
    fact_hora = cargar_fact_ocupacion_por_hora()
    fact_actual = cargar_fact_estado_actual_estacion()

    crear_tablas >> [dim_time, dim_zona]
    dim_zona >> dim_estacion
    [dim_time, dim_estacion] >> fact_hora
    fact_hora >> fact_actual


gold_citybikes()