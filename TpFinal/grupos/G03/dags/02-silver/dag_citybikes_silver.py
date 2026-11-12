from airflow.sdk import dag, task
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

from datetime import datetime, timezone

import json
import math
import os

import pandas as pd
import sqlalchemy

from shapely.geometry import Point, shape
from shapely.ops import nearest_points


# =========================================================
# CONFIGURACIÓN
# =========================================================

TARGET_NETWORK_ID = "ecobici-buenos-aires"

GEOJSON_PATH = (
    "/opt/airflow/data/reference/"
    "barrios_caba.geojson"
)

# Fallback geográfico:
# si una estación queda apenas fuera del polígono,
# permitimos asociarla al barrio más cercano.
MAX_NEAREST_DISTANCE_M = 200


# =========================================================
# DAG
# =========================================================

@dag(
    dag_id="citybikes_silver",
    start_date=datetime(2026, 11, 1),
    schedule=None,  
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    tags=["prod", "silver", "citybikes"],
)
def citybikes_silver():

    @task
    def transform_bronze_to_silver():

        # -------------------------------------------------
        # 1. Conectar al Data Warehouse
        # -------------------------------------------------

        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://"
            f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
            f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
            f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
        )

        # -------------------------------------------------
        # 2. Asegurar estructuras técnicas de Silver
        # -------------------------------------------------

        with engine.begin() as conn:

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE SCHEMA
                    IF NOT EXISTS silver;
                    """
                )
            )

            # ---------------------------------------------
            # Tabla de control incremental
            # ---------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS
                    silver.citybikes_processed_snapshots (

                        snapshot_id TEXT PRIMARY KEY,

                        processed_at
                            TIMESTAMPTZ NOT NULL,

                        source_max_ingested_at
                            TIMESTAMPTZ,

                        valid_rows
                            INTEGER NOT NULL DEFAULT 0,

                        quarantine_rows
                            INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
            )

            # ---------------------------------------------
            # Evolución del esquema Silver
            # ---------------------------------------------
            #
            # Si las tablas ya existen de versiones
            # anteriores, agregamos las nuevas columnas.
            # Si todavía no existen, to_sql las creará.
            # ---------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    """
                    ALTER TABLE IF EXISTS
                    silver.citybikes_stations

                    ADD COLUMN IF NOT EXISTS
                        altitude DOUBLE PRECISION,

                    ADD COLUMN IF NOT EXISTS
                        normal_bikes BIGINT,

                    ADD COLUMN IF NOT EXISTS
                        address TEXT,

                    ADD COLUMN IF NOT EXISTS
                        post_code TEXT,

                    ADD COLUMN IF NOT EXISTS
                        barrio TEXT,

                    ADD COLUMN IF NOT EXISTS
                        comuna BIGINT,

                    ADD COLUMN IF NOT EXISTS
                        zone_assignment_method TEXT,

                    ADD COLUMN IF NOT EXISTS
                        zone_distance_m DOUBLE PRECISION;
                    """
                )
            )

            conn.execute(
                sqlalchemy.text(
                    """
                    ALTER TABLE IF EXISTS
                    silver.quarantine_citybikes_stations

                    ADD COLUMN IF NOT EXISTS
                        altitude DOUBLE PRECISION,

                    ADD COLUMN IF NOT EXISTS
                        normal_bikes BIGINT,

                    ADD COLUMN IF NOT EXISTS
                        address TEXT,

                    ADD COLUMN IF NOT EXISTS
                        post_code TEXT,

                    ADD COLUMN IF NOT EXISTS
                        barrio TEXT,

                    ADD COLUMN IF NOT EXISTS
                        comuna BIGINT,

                    ADD COLUMN IF NOT EXISTS
                        zone_assignment_method TEXT,

                    ADD COLUMN IF NOT EXISTS
                        zone_distance_m DOUBLE PRECISION;
                    """
                )
            )

            # ---------------------------------------------
            # Función auxiliar SQL: conversión segura a
            # timestamp con zona horaria
            # ---------------------------------------------
            #
            # Reemplaza al pd.to_datetime(errors="coerce")
            # que se hacía en pandas:
            #
            #  - saca la 'Z' sobrante cuando ya hay offset
            #    (2026-11-10T02:25:30+00:00Z)
            #  - si no trae zona, asume UTC
            #  - si no se puede interpretar -> NULL
            #    (el registro irá luego a cuarentena)
            # ---------------------------------------------

            conn.execute(
                sqlalchemy.text(
                    r"""
                    CREATE OR REPLACE FUNCTION
                    silver.safe_timestamptz(raw TEXT)
                    RETURNS TIMESTAMPTZ
                    LANGUAGE plpgsql
                    STABLE
                    AS $$
                    DECLARE
                        cleaned TEXT;
                    BEGIN
                        cleaned := REGEXP_REPLACE(
                            BTRIM(raw),
                            '([+-][0-9]{2}:[0-9]{2})Z$',
                            '\1'
                        );

                        IF cleaned IS NULL OR cleaned = '' THEN
                            RETURN NULL;
                        END IF;

                        IF cleaned !~
                            '(Z|[+-][0-9]{2}(:?[0-9]{2})?)$'
                        THEN
                            cleaned := cleaned || '+00';
                        END IF;

                        RETURN cleaned::TIMESTAMPTZ;

                    EXCEPTION WHEN OTHERS THEN
                        RETURN NULL;
                    END;
                    $$;
                    """
                )
            )

        # -------------------------------------------------
        # 3. Leer snapshots nuevos y transformarlos EN SQL
        # -------------------------------------------------
        #
        # SQL PUSHDOWN: la transformación se hace dentro de
        # Postgres, no en pandas. A Python llegan filas ya
        # normalizadas, deduplicadas y con las variables
        # derivadas calculadas. Pasos de la consulta:
        #
        #   source      snapshots de Bronze de la red
        #   pending     solo los snapshots no procesados
        #   normalized  trim, ''->NULL y tipado de fechas
        #   deduped     1 fila por (estación, snapshot)
        #   enriched    accounted_slots y capacity
        #   metrics     unaccounted_slots, porcentajes y
        #               estado operativo
        #
        # En Python quedan solamente: el enriquecimiento
        # geográfico (shapely), las validaciones de calidad,
        # la separación en cuarentena y la escritura.
        # -------------------------------------------------

        query = sqlalchemy.text(
            """
            WITH source AS (

                SELECT

                    network_id,
                    network_name,
                    network_city,
                    network_country,

                    station_id,
                    station_uid,
                    station_name,

                    latitude,
                    longitude,
                    altitude,

                    address,
                    post_code,

                    station_timestamp,
                    provider_last_updated,

                    free_bikes,
                    empty_slots,
                    slots,
                    normal_bikes,

                    renting,
                    returning_allowed,

                    virtual,
                    payment_terminal,

                    COALESCE(
                        NULLIF(
                            BTRIM(snapshot_id),
                            ''
                        ),
                        TO_CHAR(
                            ingested_at
                            AT TIME ZONE 'UTC',
                            'YYYYMMDD"T"HH24MISS.US"Z"'
                        )
                    ) AS snapshot_id,

                    raw_file_path,
                    source_url,
                    ingested_at

                FROM bronze.citybikes_stations

                WHERE
                    network_id = :target_network_id

                    AND (
                        snapshot_id IS NOT NULL

                        OR (
                            renting IS NOT NULL
                            AND returning_allowed
                                IS NOT NULL
                        )
                    )
            ),

            -- Solo snapshots que todavía no se procesaron
            pending AS (

                SELECT
                    s.*

                FROM source s

                WHERE
                    s.snapshot_id IS NOT NULL

                    AND NOT EXISTS (

                        SELECT 1

                        FROM
                            silver.citybikes_processed_snapshots p

                        WHERE
                            p.snapshot_id = s.snapshot_id
                    )
            ),

            -- Normalización: trim, blancos -> NULL y fechas
            normalized AS (

                SELECT

                    NULLIF(BTRIM(network_id), '')
                        AS network_id,
                    NULLIF(BTRIM(network_name), '')
                        AS network_name,
                    NULLIF(BTRIM(network_city), '')
                        AS network_city,
                    NULLIF(BTRIM(network_country), '')
                        AS network_country,

                    NULLIF(BTRIM(station_id), '')
                        AS station_id,
                    NULLIF(BTRIM(station_uid), '')
                        AS station_uid,
                    NULLIF(BTRIM(station_name), '')
                        AS station_name,

                    latitude,
                    longitude,
                    altitude,

                    NULLIF(BTRIM(address), '')
                        AS address,
                    NULLIF(BTRIM(post_code), '')
                        AS post_code,

                    silver.safe_timestamptz(
                        station_timestamp::TEXT
                    ) AS station_timestamp,

                    silver.safe_timestamptz(
                        provider_last_updated::TEXT
                    ) AS provider_last_updated,

                    free_bikes,
                    empty_slots,
                    slots,
                    normal_bikes,

                    renting,
                    returning_allowed,

                    virtual,
                    payment_terminal,

                    snapshot_id,
                    raw_file_path,
                    source_url,

                    ingested_at::TIMESTAMPTZ
                        AS ingested_at

                FROM pending
            ),

            -- GRANO SILVER:
            -- 1 fila = 1 estación x 1 snapshot del pipeline.
            -- Si hay repetidas, se queda la última ingestada.
            -- station_timestamp no forma parte de la clave
            -- porque el proveedor puede mantenerlo entre
            -- consultas consecutivas.
            deduped AS (

                SELECT DISTINCT ON (
                    station_id,
                    snapshot_id
                )
                    n.*

                FROM normalized n

                ORDER BY
                    n.station_id,
                    n.snapshot_id,
                    n.ingested_at DESC NULLS LAST
            ),

            -- Slots contabilizados y capacidad nominal.
            -- Capacidad: 1) slots informado por EcoBici,
            -- 2) free_bikes + empty_slots como fallback.
            enriched AS (

                SELECT
                    d.*,

                    d.free_bikes + d.empty_slots
                        AS accounted_slots,

                    COALESCE(
                        d.slots,
                        d.free_bikes + d.empty_slots
                    ) AS capacity

                FROM deduped d
            ),

            -- Slots no explicados, porcentajes y estado
            -- operativo.
            --
            -- Porcentajes: solo con capacidad > 0
            -- (NULLIF evita la división por cero).
            --
            -- Estado operativo (renting / returning):
            --   1 / 1 -> operativa
            --   0 / 1 -> solo devolución
            --   1 / 0 -> solo retiro
            --   0 / 0 -> fuera de servicio
            metrics AS (

                SELECT
                    e.*,

                    e.capacity - e.accounted_slots
                        AS unaccounted_slots,

                    CASE WHEN e.capacity > 0 THEN
                        e.free_bikes::DOUBLE PRECISION
                        / NULLIF(e.capacity, 0) * 100
                    END AS occupancy_pct,

                    CASE WHEN e.capacity > 0 THEN
                        e.empty_slots::DOUBLE PRECISION
                        / NULLIF(e.capacity, 0) * 100
                    END AS empty_slots_pct,

                    CASE WHEN e.capacity > 0 THEN
                        e.accounted_slots::DOUBLE PRECISION
                        / NULLIF(e.capacity, 0) * 100
                    END AS accounted_slots_pct,

                    CASE WHEN e.capacity > 0 THEN
                        (e.capacity - e.accounted_slots)
                            ::DOUBLE PRECISION
                        / NULLIF(e.capacity, 0) * 100
                    END AS unaccounted_slots_pct,

                    CASE
                        WHEN e.renting = 1
                            AND e.returning_allowed = 1
                            THEN 'operativa'
                        WHEN e.renting = 0
                            AND e.returning_allowed = 1
                            THEN 'solo_devolucion'
                        WHEN e.renting = 1
                            AND e.returning_allowed = 0
                            THEN 'solo_retiro'
                        WHEN e.renting = 0
                            AND e.returning_allowed = 0
                            THEN 'fuera_servicio'
                        ELSE 'desconocido'
                    END AS operational_status

                FROM enriched e
            )

            SELECT
                m.*,

                (m.operational_status = 'operativa')
                    AS is_fully_operational

            FROM metrics m

            ORDER BY
                m.ingested_at,
                m.station_id
            """
        )

        df = pd.read_sql(
            query,
            engine,
            params={
                "target_network_id":
                    TARGET_NETWORK_ID,
            },
        )

        # -------------------------------------------------
        # 4. Finalizar si no hay snapshots nuevos
        # -------------------------------------------------

        if df.empty:

            print(
                "No hay snapshots nuevos de Bronze "
                "pendientes de procesar."
            )

            return

        print(
            f"Filas nuevas leídas desde Bronze "
            f"(ya normalizadas y deduplicadas en SQL): "
            f"{len(df)}"
        )

        print(
            f"Snapshots nuevos detectados: "
            f"{df['snapshot_id'].nunique()}"
        )

        # -------------------------------------------------
        # 5, 6 y 7. Normalización, deduplicación y
        #           variables derivadas
        # -------------------------------------------------
        #
        # Ya se resolvieron en SQL en el paso 3 (pushdown).
        # No se repiten en pandas.
        # -------------------------------------------------

        # -------------------------------------------------
        # 8. Enriquecimiento geográfico
        # -------------------------------------------------

        if not os.path.exists(
            GEOJSON_PATH
        ):

            raise FileNotFoundError(
                f"No se encontró el GeoJSON: "
                f"{GEOJSON_PATH}"
            )

        with open(
            GEOJSON_PATH,
            encoding="utf-8",
        ) as f:

            geojson = json.load(f)

        if not geojson.get("features"):

            raise ValueError(
                "El GeoJSON de barrios "
                "no contiene features."
            )

        barrios = []

        for feature in geojson["features"]:

            props = (
                feature.get("properties")
                or {}
            )

            geometry = (
                feature.get("geometry")
            )

            if geometry is None:
                continue

            barrio_name = (
                props.get("BARRIO")
            )

            comuna_value = (
                props.get("COMUNA")
            )

            if (
                barrio_name is None
                or comuna_value is None
            ):
                continue

            barrios.append({

                "barrio":
                    str(
                        barrio_name
                    ).strip(),

                "comuna":
                    int(
                        comuna_value
                    ),

                "geometry":
                    shape(
                        geometry
                    ),
            })

        if not barrios:

            raise ValueError(
                "No se pudieron cargar "
                "barrios válidos desde "
                "el GeoJSON."
            )

        print(
            f"Barrios cargados: "
            f"{len(barrios)}"
        )

        # -------------------------------------------------
        # Distancia geodésica aproximada
        # -------------------------------------------------

        def haversine_meters(
            lon1,
            lat1,
            lon2,
            lat2,
        ):

            earth_radius_m = 6371000

            phi1 = math.radians(
                lat1
            )

            phi2 = math.radians(
                lat2
            )

            delta_phi = math.radians(
                lat2 - lat1
            )

            delta_lambda = math.radians(
                lon2 - lon1
            )

            a = (

                math.sin(
                    delta_phi / 2
                ) ** 2

                + math.cos(phi1)
                * math.cos(phi2)

                * math.sin(
                    delta_lambda / 2
                ) ** 2
            )

            c = 2 * math.atan2(
                math.sqrt(a),
                math.sqrt(1 - a),
            )

            return (
                earth_radius_m * c
            )

        # -------------------------------------------------
        # Asignación barrio/comuna
        # -------------------------------------------------

        def assign_zone(
            station_id,
            latitude,
            longitude,
        ):

            # Coordenadas inválidas:
            # no intentamos geolocalización.

            if (
                pd.isna(latitude)
                or pd.isna(longitude)
            ):

                return {

                    "station_id":
                        station_id,

                    "latitude":
                        latitude,

                    "longitude":
                        longitude,

                    "barrio":
                        None,

                    "comuna":
                        None,

                    "zone_assignment_method":
                        "invalid_coordinates",

                    "zone_distance_m":
                        None,
                }

            point = Point(
                longitude,
                latitude,
            )

            # ---------------------------------------------
            # 1. Point-in-polygon
            # ---------------------------------------------

            for barrio in barrios:

                if (
                    barrio["geometry"]
                    .covers(point)
                ):

                    return {

                        "station_id":
                            station_id,

                        "latitude":
                            latitude,

                        "longitude":
                            longitude,

                        "barrio":
                            barrio["barrio"],

                        "comuna":
                            barrio["comuna"],

                        "zone_assignment_method":
                            "polygon",

                        "zone_distance_m":
                            0.0,
                    }

            # ---------------------------------------------
            # 2. Fallback:
            #    polígono más cercano
            # ---------------------------------------------

            nearest_match = None
            nearest_distance = None

            for barrio in barrios:

                nearest_point = (

                    nearest_points(
                        point,
                        barrio["geometry"],
                    )[1]
                )

                distance_m = (
                    haversine_meters(
                        point.x,
                        point.y,
                        nearest_point.x,
                        nearest_point.y,
                    )
                )

                if (
                    nearest_distance is None
                    or distance_m
                    < nearest_distance
                ):

                    nearest_distance = (
                        distance_m
                    )

                    nearest_match = (
                        barrio
                    )

            # ---------------------------------------------
            # Aceptar fallback solo dentro
            # del umbral definido.
            # ---------------------------------------------

            if (
                nearest_match is not None
                and nearest_distance
                <= MAX_NEAREST_DISTANCE_M
            ):

                return {

                    "station_id":
                        station_id,

                    "latitude":
                        latitude,

                    "longitude":
                        longitude,

                    "barrio":
                        nearest_match[
                            "barrio"
                        ],

                    "comuna":
                        nearest_match[
                            "comuna"
                        ],

                    "zone_assignment_method":
                        "nearest",

                    "zone_distance_m":
                        nearest_distance,
                }

            # ---------------------------------------------
            # Sin asignación confiable
            # ---------------------------------------------

            return {

                "station_id":
                    station_id,

                "latitude":
                    latitude,

                "longitude":
                    longitude,

                "barrio":
                    None,

                "comuna":
                    None,

                "zone_assignment_method":
                    "unmatched",

                # Conservamos la distancia al polígono
                # más cercano para auditoría.
                "zone_distance_m":
                    nearest_distance,
            }

        # -------------------------------------------------
        # Calcular zona solamente para posiciones únicas
        # -------------------------------------------------
        #
        # Evitamos repetir el point-in-polygon para una
        # misma estación en cada snapshot.
        # -------------------------------------------------

        station_positions = (

            df[
                [
                    "station_id",
                    "latitude",
                    "longitude",
                ]
            ]

            .drop_duplicates()
        )

        zone_rows = []

        for _, row in (
            station_positions.iterrows()
        ):

            zone_rows.append(
                assign_zone(
                    station_id=(
                        row["station_id"]
                    ),
                    latitude=(
                        row["latitude"]
                    ),
                    longitude=(
                        row["longitude"]
                    ),
                )
            )

        zone_map = pd.DataFrame(
            zone_rows
        )

        if not zone_map.empty:

            zone_map["comuna"] = (

                pd.to_numeric(
                    zone_map["comuna"],
                    errors="coerce",
                )

                .astype("Int64")
            )

            df = df.merge(

                zone_map,

                on=[
                    "station_id",
                    "latitude",
                    "longitude",
                ],

                how="left",

                validate="many_to_one",
            )

        else:

            df["barrio"] = None

            df["comuna"] = (
                pd.Series(
                    pd.NA,
                    index=df.index,
                    dtype="Int64",
                )
            )

            df[
                "zone_assignment_method"
            ] = "unmatched"

            df[
                "zone_distance_m"
            ] = float("nan")

        # -------------------------------------------------
        # Auditoría geográfica
        # -------------------------------------------------

        print(
            "\nMétodos de asignación geográfica:"
        )

        print(
            df[
                "zone_assignment_method"
            ]
            .value_counts(
                dropna=False
            )
        )

        print(
            f"Filas sin barrio: "
            f"{df['barrio'].isna().sum()}"
        )

        print(
            f"Estaciones únicas sin barrio: "
            f"{df.loc[df['barrio'].isna(), 'station_id'].nunique()}"
        )

        # -------------------------------------------------
        # 9. Validaciones de calidad
        # -------------------------------------------------

        def quality_check(row):

            reasons = []

            # -----------------------------------------
            # Identificación
            # -----------------------------------------

            if (
                pd.isna(
                    row["station_id"]
                )
                or not str(
                    row["station_id"]
                ).strip()
            ):

                reasons.append(
                    "missing_station_id"
                )

            if (
                pd.isna(
                    row["station_name"]
                )
                or not str(
                    row["station_name"]
                ).strip()
            ):

                reasons.append(
                    "missing_station_name"
                )

            if (
                pd.isna(
                    row["snapshot_id"]
                )
                or not str(
                    row["snapshot_id"]
                ).strip()
            ):

                reasons.append(
                    "missing_snapshot_id"
                )

            # -----------------------------------------
            # Tiempo
            # -----------------------------------------

            if pd.isna(
                row["station_timestamp"]
            ):

                reasons.append(
                    "invalid_timestamp"
                )

            if pd.isna(
                row["ingested_at"]
            ):

                reasons.append(
                    "invalid_ingested_at"
                )

            # -----------------------------------------
            # Coordenadas
            # -----------------------------------------

            if (
                pd.isna(
                    row["latitude"]
                )
                or row["latitude"] < -90
                or row["latitude"] > 90
            ):

                reasons.append(
                    "invalid_latitude"
                )

            if (
                pd.isna(
                    row["longitude"]
                )
                or row["longitude"] < -180
                or row["longitude"] > 180
            ):

                reasons.append(
                    "invalid_longitude"
                )

            # -----------------------------------------
            # Bicicletas / slots
            # -----------------------------------------

            if (
                pd.isna(
                    row["free_bikes"]
                )
                or row["free_bikes"] < 0
            ):

                reasons.append(
                    "invalid_free_bikes"
                )

            if (
                pd.isna(
                    row["empty_slots"]
                )
                or row["empty_slots"] < 0
            ):

                reasons.append(
                    "invalid_empty_slots"
                )

            if (
                pd.isna(
                    row["capacity"]
                )
                or row["capacity"] <= 0
            ):

                reasons.append(
                    "invalid_capacity"
                )

            if (
                pd.notna(
                    row["normal_bikes"]
                )
                and row["normal_bikes"] < 0
            ):

                reasons.append(
                    "invalid_normal_bikes"
                )

            # free_bikes + empty_slots
            # no debería superar capacity.

            if (
                pd.notna(
                    row["capacity"]
                )
                and pd.notna(
                    row["accounted_slots"]
                )
                and row["accounted_slots"]
                > row["capacity"]
            ):

                reasons.append(
                    "accounted_slots_exceeds_capacity"
                )

            # -----------------------------------------
            # Estado operativo
            # -----------------------------------------

            if pd.isna(
                row["renting"]
            ):

                reasons.append(
                    "missing_renting_status"
                )

            if pd.isna(
                row["returning_allowed"]
            ):

                reasons.append(
                    "missing_returning_status"
                )

            if (
                pd.notna(
                    row["renting"]
                )
                and row["renting"]
                not in [0, 1]
            ):

                reasons.append(
                    "invalid_renting_status"
                )

            if (
                pd.notna(
                    row["returning_allowed"]
                )
                and row[
                    "returning_allowed"
                ]
                not in [0, 1]
            ):

                reasons.append(
                    "invalid_returning_status"
                )

            # -----------------------------------------
            # Zona
            # -----------------------------------------
            #
            # Una falla de enriquecimiento geográfico
            # NO convierte automáticamente el snapshot
            # en dato técnicamente inválido.
            #
            # Se conserva con barrio/comuna NULL y
            # zone_assignment_method='unmatched'.
            # -----------------------------------------

            return "|".join(
                reasons
            )

        df["quarantine_reason"] = (

            df.apply(
                quality_check,
                axis=1,
            )
        )

        # -------------------------------------------------
        # 10. Separar válidos e inválidos
        # -------------------------------------------------

        quarantine = (

            df[
                df[
                    "quarantine_reason"
                ] != ""
            ]

            .copy()
        )

        valid = (

            df[
                df[
                    "quarantine_reason"
                ] == ""
            ]

            .copy()
        )

        # -------------------------------------------------
        # 11. Estado operacional
        # -------------------------------------------------
        #
        # operational_status e is_fully_operational ya se
        # calcularon en SQL (paso 3). La tabla de cuarentena
        # nunca tuvo esas dos columnas, así que se quitan de
        # ese DataFrame para no cambiar su esquema.
        # -------------------------------------------------

        quarantine = quarantine.drop(
            columns=[
                "operational_status",
                "is_fully_operational",
            ]
        )

        # -------------------------------------------------
        # 12. Metadata de auditoría Silver
        # -------------------------------------------------

        processed_at = (
            datetime.now(
                timezone.utc
            )
        )

        for dataframe in [
            valid,
            quarantine,
        ]:

            dataframe[
                "_processed_at"
            ] = processed_at

            dataframe[
                "_source_table"
            ] = (
                "bronze.citybikes_stations"
            )

        # -------------------------------------------------
        # 13. Metadata de snapshots procesados
        # -------------------------------------------------

        snapshot_control = (

            df.groupby(
                "snapshot_id",
                as_index=False,
            )

            .agg(
                source_max_ingested_at=(
                    "ingested_at",
                    "max",
                )
            )
        )

        valid_counts = (

            valid[
                "snapshot_id"
            ]
            .value_counts()
        )

        quarantine_counts = (

            quarantine[
                "snapshot_id"
            ]
            .value_counts()
        )

        snapshot_control[
            "valid_rows"
        ] = (

            snapshot_control[
                "snapshot_id"
            ]

            .map(
                valid_counts
            )

            .fillna(0)

            .astype(int)
        )

        snapshot_control[
            "quarantine_rows"
        ] = (

            snapshot_control[
                "snapshot_id"
            ]

            .map(
                quarantine_counts
            )

            .fillna(0)

            .astype(int)
        )

        snapshot_control[
            "processed_at"
        ] = processed_at

        # quarantine_reason solamente existe
        # en los registros rechazados.

        valid.drop(
            columns=[
                "quarantine_reason"
            ],
            inplace=True,
        )

        # -------------------------------------------------
        # 14. Persistencia incremental e idempotente
        # -------------------------------------------------
        #
        # Las tres escrituras se realizan dentro de una
        # misma transacción:
        #
        # 1. registros válidos
        # 2. quarantine
        # 3. snapshots procesados
        #
        # Si cualquiera falla:
        # PostgreSQL hace rollback.
        # -------------------------------------------------

        with engine.begin() as conn:

            if not valid.empty:

                valid.to_sql(
                    "citybikes_stations",
                    conn,
                    schema="silver",
                    if_exists="append",
                    index=False,
                )

            if not quarantine.empty:

                quarantine.to_sql(
                    "quarantine_citybikes_stations",
                    conn,
                    schema="silver",
                    if_exists="append",
                    index=False,
                )

            snapshot_control.to_sql(
                "citybikes_processed_snapshots",
                conn,
                schema="silver",
                if_exists="append",
                index=False,
            )

        # -------------------------------------------------
        # 15. Resumen de ejecución
        # -------------------------------------------------

        print(
            f"Snapshots nuevos procesados: "
            f"{df['snapshot_id'].nunique()}"
        )

        print(
            f"Válidas insertadas: "
            f"{len(valid)}"
        )

        print(
            f"Quarantine insertadas: "
            f"{len(quarantine)}"
        )

        print(
            f"Total procesado: "
            f"{len(valid) + len(quarantine)}"
        )

        if not valid.empty:

            print(
                "\nEstados operativos:"
            )

            print(
                valid[
                    "operational_status"
                ]
                .value_counts(
                    dropna=False
                )
            )

            print(
                "\nAsignación geográfica:"
            )

            print(
                valid[
                    "zone_assignment_method"
                ]
                .value_counts(
                    dropna=False
                )
            )

            print(
                f"\nEstaciones únicas "
                f"con barrio: "
                f"{valid.loc[valid['barrio'].notna(), 'station_id'].nunique()}"
            )

            print(
                f"Estaciones únicas "
                f"sin barrio: "
                f"{valid.loc[valid['barrio'].isna(), 'station_id'].nunique()}"
            )


    transform = transform_bronze_to_silver()

    trigger_gold = TriggerDagRunOperator(
        task_id="trigger_citybikes_gold",
        trigger_dag_id="citybikes_gold",
        wait_for_completion=True,
        poke_interval=5,
        allowed_states=["success"],
        failed_states=["failed"],
    )

    transform >> trigger_gold


citybikes_silver()