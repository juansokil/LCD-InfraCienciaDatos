from airflow.sdk import dag, task
from datetime import datetime

import os

import pandas as pd
import sqlalchemy


# =========================================================
# CONFIGURACIÓN
# =========================================================

TARGET_NETWORK_ID = "ecobici-buenos-aires"

LOCAL_TIMEZONE = "America/Argentina/Buenos_Aires"


# =========================================================
# DAG
# =========================================================

@dag(
    dag_id="citybikes_gold",
    start_date=datetime(2026, 11, 1),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=["prod", "gold", "citybikes"],
)
def citybikes_gold():

    # =====================================================
    # TASK 1
    # Construcción del modelo Gold
    # =====================================================

    @task
    def build_gold_model():

        # -------------------------------------------------
        # 1. Conexión
        # -------------------------------------------------

        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://"
            f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
            f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
            f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
        )

        with engine.begin() as conn:

            # -------------------------------------------------
            # 2. Schema Gold
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE SCHEMA
                    IF NOT EXISTS gold;
                    """
                )
            )

            # -------------------------------------------------
            # 3. DIM_ZONA
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS
                    gold.dim_zona (

                        zona_key TEXT PRIMARY KEY,

                        barrio TEXT NOT NULL,

                        comuna BIGINT NOT NULL,

                        created_at
                            TIMESTAMPTZ NOT NULL
                            DEFAULT NOW(),

                        UNIQUE (
                            barrio,
                            comuna
                        )
                    );
                    """
                )
            )

            # -------------------------------------------------
            # 4. DIM_ESTACION
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS
                    gold.dim_estacion (

                        estacion_key TEXT PRIMARY KEY,

                        station_id TEXT
                            NOT NULL UNIQUE,

                        station_uid TEXT,

                        network_id TEXT
                            NOT NULL,

                        network_name TEXT,

                        station_name TEXT
                            NOT NULL,

                        address TEXT,

                        post_code TEXT,

                        latitude
                            DOUBLE PRECISION,

                        longitude
                            DOUBLE PRECISION,

                        altitude
                            DOUBLE PRECISION,

                        capacity
                            DOUBLE PRECISION,

                        zona_key TEXT,

                        updated_at
                            TIMESTAMPTZ
                            NOT NULL,

                        CONSTRAINT
                            fk_dim_estacion_zona

                            FOREIGN KEY (
                                zona_key
                            )

                            REFERENCES
                                gold.dim_zona(
                                    zona_key
                                )
                    );
                    """
                )
            )

            # -------------------------------------------------
            # 5. FACT_OCUPACION_POR_HORA
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS
                    gold.fact_ocupacion_por_hora (

                        estacion_key TEXT
                            NOT NULL,

                        hour_start_utc
                            TIMESTAMPTZ
                            NOT NULL,

                        hour_start_local
                            TIMESTAMP
                            NOT NULL,

                        fecha_local
                            DATE
                            NOT NULL,

                        hora_local
                            SMALLINT
                            NOT NULL,

                        snapshots_count
                            INTEGER
                            NOT NULL,

                        avg_capacity
                            DOUBLE PRECISION,

                        avg_free_bikes
                            DOUBLE PRECISION,

                        min_free_bikes
                            DOUBLE PRECISION,

                        max_free_bikes
                            DOUBLE PRECISION,

                        avg_empty_slots
                            DOUBLE PRECISION,

                        min_empty_slots
                            DOUBLE PRECISION,

                        max_empty_slots
                            DOUBLE PRECISION,

                        avg_occupancy_pct
                            DOUBLE PRECISION,

                        min_occupancy_pct
                            DOUBLE PRECISION,

                        max_occupancy_pct
                            DOUBLE PRECISION,

                        avg_unaccounted_slots
                            DOUBLE PRECISION,

                        zero_bikes_count
                            INTEGER
                            NOT NULL,

                        zero_empty_slots_count
                            INTEGER
                            NOT NULL,

                        operational_snapshots
                            INTEGER
                            NOT NULL,

                        out_of_service_snapshots
                            INTEGER
                            NOT NULL,

                        fully_operational_pct
                            DOUBLE PRECISION,

                        zero_bikes_pct
                            DOUBLE PRECISION,

                        zero_empty_slots_pct
                            DOUBLE PRECISION,

                        first_snapshot_at_utc
                            TIMESTAMPTZ,

                        last_snapshot_at_utc
                            TIMESTAMPTZ,

                        loaded_at
                            TIMESTAMPTZ
                            NOT NULL,

                        PRIMARY KEY (
                            estacion_key,
                            hour_start_utc
                        ),

                        CONSTRAINT
                            fk_fact_estacion

                            FOREIGN KEY (
                                estacion_key
                            )

                            REFERENCES
                                gold.dim_estacion(
                                    estacion_key
                                )
                    );
                    """
                )
            )

            # -------------------------------------------------
            # 6. FULL REFRESH
            # -------------------------------------------------
            #
            # Orden importante por las FK:
            #
            # FACT
            # ↓
            # DIM_ESTACION
            # ↓
            # DIM_ZONA
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    TRUNCATE TABLE
                        gold.fact_ocupacion_por_hora,
                        gold.dim_estacion,
                        gold.dim_zona;
                    """
                )
            )

            # -------------------------------------------------
            # 7. Cargar DIM_ZONA
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO gold.dim_zona (
                        zona_key,
                        barrio,
                        comuna,
                        created_at
                    )

                    SELECT DISTINCT

                        MD5(
                            CONCAT(
                                'citybikes|',
                                comuna::TEXT,
                                '|',
                                barrio
                            )
                        ) AS zona_key,

                        barrio,

                        comuna,

                        NOW()

                    FROM
                        silver.citybikes_stations

                    WHERE
                        network_id = :target_network_id

                        AND barrio IS NOT NULL

                        AND comuna IS NOT NULL

                    ORDER BY
                        comuna,
                        barrio;
                    """
                ),
                {
                    "target_network_id":
                        TARGET_NETWORK_ID
                },
            )

            # -------------------------------------------------
            # 8. Cargar DIM_ESTACION
            # -------------------------------------------------
            #
            # Utilizamos la observación más reciente de cada
            # estación para los atributos descriptivos.
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO gold.dim_estacion (

                        estacion_key,

                        station_id,
                        station_uid,

                        network_id,
                        network_name,

                        station_name,

                        address,
                        post_code,

                        latitude,
                        longitude,
                        altitude,

                        capacity,

                        zona_key,

                        updated_at
                    )

                    WITH latest_station AS (

                        SELECT DISTINCT ON (
                            station_id
                        )

                            station_id,
                            station_uid,

                            network_id,
                            network_name,

                            station_name,

                            address,
                            post_code,

                            latitude,
                            longitude,
                            altitude,

                            capacity,

                            barrio,
                            comuna,

                            ingested_at

                        FROM
                            silver.citybikes_stations

                        WHERE
                            network_id =
                                :target_network_id

                        ORDER BY
                            station_id,
                            ingested_at DESC
                                NULLS LAST
                    )

                    SELECT

                        MD5(
                            CONCAT(
                                'station|',
                                ls.station_id
                            )
                        ) AS estacion_key,

                        ls.station_id,
                        ls.station_uid,

                        ls.network_id,
                        ls.network_name,

                        ls.station_name,

                        ls.address,
                        ls.post_code,

                        ls.latitude,
                        ls.longitude,
                        ls.altitude,

                        ls.capacity,

                        dz.zona_key,

                        NOW()

                    FROM
                        latest_station ls

                    LEFT JOIN
                        gold.dim_zona dz

                        ON dz.barrio =
                            ls.barrio

                        AND dz.comuna =
                            ls.comuna

                    ORDER BY
                        ls.station_name;
                    """
                ),
                {
                    "target_network_id":
                        TARGET_NETWORK_ID
                },
            )

            # -------------------------------------------------
            # 9. Cargar FACT_OCUPACION_POR_HORA
            # -------------------------------------------------
            #
            # GRANO GOLD:
            #
            # 1 fila =
            # 1 estación
            # x
            # 1 hora
            #
            # IMPORTANTE:
            #
            # Utilizamos ingested_at como tiempo del snapshot.
            # No station_timestamp, porque el proveedor puede
            # mantener ese timestamp entre distintas consultas.
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO
                        gold.fact_ocupacion_por_hora (

                            estacion_key,

                            hour_start_utc,
                            hour_start_local,

                            fecha_local,
                            hora_local,

                            snapshots_count,

                            avg_capacity,

                            avg_free_bikes,
                            min_free_bikes,
                            max_free_bikes,

                            avg_empty_slots,
                            min_empty_slots,
                            max_empty_slots,

                            avg_occupancy_pct,
                            min_occupancy_pct,
                            max_occupancy_pct,

                            avg_unaccounted_slots,

                            zero_bikes_count,

                            zero_empty_slots_count,

                            operational_snapshots,

                            out_of_service_snapshots,

                            fully_operational_pct,

                            zero_bikes_pct,

                            zero_empty_slots_pct,

                            first_snapshot_at_utc,

                            last_snapshot_at_utc,

                            loaded_at
                        )

                    WITH base AS (

                        SELECT

                            de.estacion_key,

                            s.ingested_at,

                            DATE_TRUNC(
                                'hour',

                                s.ingested_at
                                AT TIME ZONE 'UTC'
                            )
                            AT TIME ZONE 'UTC'
                                AS hour_start_utc,

                            DATE_TRUNC(
                                'hour',

                                s.ingested_at
                                AT TIME ZONE
                                :local_timezone
                            )
                                AS hour_start_local,

                            s.capacity,

                            s.free_bikes,

                            s.empty_slots,

                            s.occupancy_pct,

                            s.unaccounted_slots,

                            s.operational_status,

                            s.is_fully_operational

                        FROM
                            silver.citybikes_stations s

                        INNER JOIN
                            gold.dim_estacion de

                            ON de.station_id =
                                s.station_id

                        WHERE
                            s.network_id =
                                :target_network_id

                            AND s.ingested_at
                                IS NOT NULL
                    )

                    SELECT

                        estacion_key,

                        hour_start_utc,

                        hour_start_local,

                        hour_start_local::DATE
                            AS fecha_local,

                        EXTRACT(
                            HOUR
                            FROM hour_start_local
                        )::SMALLINT
                            AS hora_local,

                        COUNT(*)::INTEGER
                            AS snapshots_count,

                        AVG(
                            capacity
                        )::DOUBLE PRECISION
                            AS avg_capacity,

                        AVG(
                            free_bikes
                        )::DOUBLE PRECISION
                            AS avg_free_bikes,

                        MIN(
                            free_bikes
                        )::DOUBLE PRECISION
                            AS min_free_bikes,

                        MAX(
                            free_bikes
                        )::DOUBLE PRECISION
                            AS max_free_bikes,

                        AVG(
                            empty_slots
                        )::DOUBLE PRECISION
                            AS avg_empty_slots,

                        MIN(
                            empty_slots
                        )::DOUBLE PRECISION
                            AS min_empty_slots,

                        MAX(
                            empty_slots
                        )::DOUBLE PRECISION
                            AS max_empty_slots,

                        AVG(
                            occupancy_pct
                        )::DOUBLE PRECISION
                            AS avg_occupancy_pct,

                        MIN(
                            occupancy_pct
                        )::DOUBLE PRECISION
                            AS min_occupancy_pct,

                        MAX(
                            occupancy_pct
                        )::DOUBLE PRECISION
                            AS max_occupancy_pct,

                        AVG(
                            unaccounted_slots
                        )::DOUBLE PRECISION
                            AS avg_unaccounted_slots,

                        COUNT(*) FILTER (
                            WHERE free_bikes = 0
                        )::INTEGER
                            AS zero_bikes_count,

                        COUNT(*) FILTER (
                            WHERE empty_slots = 0
                        )::INTEGER
                            AS zero_empty_slots_count,

                        COUNT(*) FILTER (
                            WHERE
                                operational_status =
                                'operativa'
                        )::INTEGER
                            AS operational_snapshots,

                        COUNT(*) FILTER (
                            WHERE
                                operational_status =
                                'fuera_servicio'
                        )::INTEGER
                            AS out_of_service_snapshots,

                        (
                            100.0
                            * COUNT(*) FILTER (
                                WHERE
                                    is_fully_operational
                                    IS TRUE
                            )

                            / NULLIF(
                                COUNT(*),
                                0
                            )
                        )::DOUBLE PRECISION
                            AS fully_operational_pct,

                        (
                            100.0
                            * COUNT(*) FILTER (
                                WHERE free_bikes = 0
                            )

                            / NULLIF(
                                COUNT(*),
                                0
                            )
                        )::DOUBLE PRECISION
                            AS zero_bikes_pct,

                        (
                            100.0
                            * COUNT(*) FILTER (
                                WHERE empty_slots = 0
                            )

                            / NULLIF(
                                COUNT(*),
                                0
                            )
                        )::DOUBLE PRECISION
                            AS zero_empty_slots_pct,

                        MIN(
                            ingested_at
                        )
                            AS first_snapshot_at_utc,

                        MAX(
                            ingested_at
                        )
                            AS last_snapshot_at_utc,

                        NOW()
                            AS loaded_at

                    FROM
                        base

                    GROUP BY
                        estacion_key,
                        hour_start_utc,
                        hour_start_local

                    ORDER BY
                        hour_start_utc,
                        estacion_key;
                    """
                ),
                {
                    "target_network_id":
                        TARGET_NETWORK_ID,

                    "local_timezone":
                        LOCAL_TIMEZONE,
                },
            )

            # -------------------------------------------------
            # 10. Índices para consultas/dashboard
            # -------------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_fact_citybikes_hour_local

                    ON
                        gold.fact_ocupacion_por_hora (
                            hour_start_local
                        );
                    """
                )
            )

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_dim_estacion_zona

                    ON
                        gold.dim_estacion (
                            zona_key
                        );
                    """
                )
            )

        print(
            "Modelo Gold de CityBikes "
            "construido correctamente."
        )

    # =====================================================
    # TASK 2
    # Validaciones Gold
    # =====================================================

    @task
    def validate_gold_model():

        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://"
            f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
            f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
            f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
        )

        # -------------------------------------------------
        # Conteos generales
        # -------------------------------------------------

        counts = pd.read_sql(
            """
            SELECT

                (
                    SELECT COUNT(*)
                    FROM gold.dim_zona
                ) AS zonas,

                (
                    SELECT COUNT(*)
                    FROM gold.dim_estacion
                ) AS estaciones,

                (
                    SELECT COUNT(*)
                    FROM gold.fact_ocupacion_por_hora
                ) AS fact_rows,

                (
                    SELECT COUNT(*)
                    FROM silver.citybikes_stations
                    WHERE network_id =
                        'ecobici-buenos-aires'
                ) AS silver_rows;
            """,
            engine,
        )

        print(
            "\n=== CONTEOS GOLD ==="
        )

        print(
            counts.to_string(
                index=False
            )
        )

        # -------------------------------------------------
        # Estaciones sin zona
        # -------------------------------------------------

        missing_zone = pd.read_sql(
            """
            SELECT
                COUNT(*) AS estaciones_sin_zona

            FROM
                gold.dim_estacion

            WHERE
                zona_key IS NULL;
            """,
            engine,
        )

        print(
            "\n=== ESTACIONES SIN ZONA ==="
        )

        print(
            missing_zone.to_string(
                index=False
            )
        )

        # -------------------------------------------------
        # Duplicados de la fact
        # -------------------------------------------------

        duplicates = pd.read_sql(
            """
            SELECT
                COUNT(*) AS duplicados

            FROM (

                SELECT
                    estacion_key,
                    hour_start_utc,
                    COUNT(*)

                FROM
                    gold.fact_ocupacion_por_hora

                GROUP BY
                    estacion_key,
                    hour_start_utc

                HAVING COUNT(*) > 1

            ) d;
            """,
            engine,
        )

        print(
            "\n=== DUPLICADOS FACT ==="
        )

        print(
            duplicates.to_string(
                index=False
            )
        )

        # -------------------------------------------------
        # Claves huérfanas
        # -------------------------------------------------

        orphan_fact = pd.read_sql(
            """
            SELECT
                COUNT(*) AS fact_sin_estacion

            FROM
                gold.fact_ocupacion_por_hora f

            LEFT JOIN
                gold.dim_estacion e

                ON e.estacion_key =
                    f.estacion_key

            WHERE
                e.estacion_key IS NULL;
            """,
            engine,
        )

        print(
            "\n=== FACT SIN DIM_ESTACION ==="
        )

        print(
            orphan_fact.to_string(
                index=False
            )
        )

        # -------------------------------------------------
        # Validaciones obligatorias
        # -------------------------------------------------

        station_count = int(
            counts.loc[
                0,
                "estaciones"
            ]
        )

        fact_count = int(
            counts.loc[
                0,
                "fact_rows"
            ]
        )

        missing_zone_count = int(
            missing_zone.loc[
                0,
                "estaciones_sin_zona"
            ]
        )

        duplicates_count = int(
            duplicates.loc[
                0,
                "duplicados"
            ]
        )

        orphan_count = int(
            orphan_fact.loc[
                0,
                "fact_sin_estacion"
            ]
        )

        if station_count == 0:

            raise ValueError(
                "Gold no contiene estaciones."
            )

        if fact_count == 0:

            raise ValueError(
                "Gold no contiene hechos "
                "de ocupación."
            )

        if missing_zone_count != 0:

            raise ValueError(
                f"Hay "
                f"{missing_zone_count} "
                f"estaciones sin zona."
            )

        if duplicates_count != 0:

            raise ValueError(
                f"Hay "
                f"{duplicates_count} "
                f"duplicados en la fact."
            )

        if orphan_count != 0:

            raise ValueError(
                f"Hay "
                f"{orphan_count} "
                f"hechos sin estación."
            )

        print(
            "\nValidación Gold OK."
        )

    # =====================================================
    # ORQUESTACIÓN
    # =====================================================

    build = build_gold_model()

    validate = validate_gold_model()

    build >> validate


citybikes_gold()