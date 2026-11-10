from airflow.sdk import dag, task
from datetime import datetime, timezone

import os
import pandas as pd
import sqlalchemy


@dag(
    dag_id="citybikes_silver",
    start_date=datetime(2026, 11, 1),
    schedule=None,   # manual mientras desarrollamos
    catchup=False,
    is_paused_upon_creation=True,
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
                    "CREATE SCHEMA IF NOT EXISTS silver;"
                )
            )

            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS
                    silver.citybikes_processed_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        processed_at TIMESTAMPTZ NOT NULL,
                        source_max_ingested_at TIMESTAMPTZ,
                        valid_rows INTEGER NOT NULL DEFAULT 0,
                        quarantine_rows INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
            )

        # -------------------------------------------------
        # 3. Leer solamente snapshots nuevos desde Bronze
        # -------------------------------------------------
        #
        # Los snapshots nuevos ya tienen snapshot_id.
        #
        # Los históricos que no tenían snapshot_id se
        # reconstruyen utilizando ingested_at.
        #
        # La tabla citybikes_processed_snapshots permite
        # excluir todo snapshot ya procesado.
        # -------------------------------------------------
        df = pd.read_sql(
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

                    station_timestamp,
                    provider_last_updated,

                    free_bikes,
                    empty_slots,
                    slots,

                    renting,
                    returning_allowed,

                    virtual,
                    payment_terminal,

                    COALESCE(
                        NULLIF(BTRIM(snapshot_id), ''),
                        TO_CHAR(
                            ingested_at AT TIME ZONE 'UTC',
                            'YYYYMMDD"T"HH24MISS.US"Z"'
                        )
                    ) AS snapshot_id,

                    raw_file_path,
                    source_url,
                    ingested_at

                FROM bronze.citybikes_stations

                WHERE
                    snapshot_id IS NOT NULL

                    OR (
                        renting IS NOT NULL
                        AND returning_allowed IS NOT NULL
                    )
            )

            SELECT
                s.*

            FROM source s

            WHERE
                s.snapshot_id IS NOT NULL

                AND NOT EXISTS (
                    SELECT 1
                    FROM silver.citybikes_processed_snapshots p
                    WHERE p.snapshot_id = s.snapshot_id
                )

            ORDER BY
                s.ingested_at,
                s.station_id
            """,
            engine,
        )

        # -------------------------------------------------
        # 4. Finalizar normalmente si no hay datos nuevos
        # -------------------------------------------------
        if df.empty:
            print(
                "No hay snapshots nuevos de Bronze "
                "pendientes de procesar."
            )
            return

        print(
            f"Filas nuevas leídas desde Bronze: {len(df)}"
        )

        print(
            f"Snapshots nuevos detectados: "
            f"{df['snapshot_id'].nunique()}"
        )

        # -------------------------------------------------
        # 5. Normalización técnica
        # -------------------------------------------------

        # ---------------------------
        # Strings
        # ---------------------------
        string_columns = [
            "network_id",
            "network_name",
            "network_city",
            "network_country",
            "station_id",
            "station_uid",
            "station_name",
            "snapshot_id",
        ]

        for column in string_columns:
            df[column] = (
                df[column]
                .astype("string")
                .str.strip()
            )

        # ---------------------------
        # Timestamp CityBikes
        # ---------------------------
        #
        # La API puede devolver:
        #
        # 2026-10-29T19:38:30.597698+00:00Z
        #
        # Si ya existe un offset +00:00 eliminamos la Z
        # final para poder parsearlo correctamente.
        # ---------------------------
        df["station_timestamp"] = (
            df["station_timestamp"]
            .astype("string")
            .str.replace(
                r"([+-]\d{2}:\d{2})Z$",
                r"\1",
                regex=True,
            )
        )

        df["station_timestamp"] = pd.to_datetime(
            df["station_timestamp"],
            errors="coerce",
            utc=True,
        )

        # ---------------------------
        # Timestamp de ingesta
        # ---------------------------
        df["ingested_at"] = pd.to_datetime(
            df["ingested_at"],
            errors="coerce",
            utc=True,
        )

        # ---------------------------
        # last_updated del proveedor
        # ---------------------------
        #
        # EcoBici actualmente lo informa como:
        #
        # 2026-11-10T01:17:17
        #
        # Lo convertimos a datetime.
        # ---------------------------
        df["provider_last_updated"] = pd.to_datetime(
            df["provider_last_updated"],
            errors="coerce",
            utc=True,
        )

        # ---------------------------
        # Numéricos
        # ---------------------------
        numeric_columns = [
            "latitude",
            "longitude",
            "free_bikes",
            "empty_slots",
            "renting",
            "returning_allowed",
            "slots",
        ]

        for column in numeric_columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        # -------------------------------------------------
        # 6. Deduplicación técnica
        # -------------------------------------------------
        #
        # GRANO SILVER:
        #
        # 1 fila =
        # 1 estación
        # x
        # 1 snapshot del pipeline
        #
        # station_timestamp no se utiliza como clave porque
        # el proveedor puede mantener el mismo timestamp
        # entre distintas consultas.
        # -------------------------------------------------
        df = (
            df.sort_values("ingested_at")
            .drop_duplicates(
                subset=[
                    "station_id",
                    "snapshot_id",
                ],
                keep="last",
            )
        )

        print(
            f"Filas luego de deduplicar: {len(df)}"
        )

        # -------------------------------------------------
        # 7. Variables derivadas
        # -------------------------------------------------

        # ---------------------------
        # Slots contabilizados
        # ---------------------------
        df["accounted_slots"] = (
            df["free_bikes"]
            + df["empty_slots"]
        )

        # ---------------------------
        # Capacidad nominal
        # ---------------------------
        #
        # Prioridad:
        #
        # 1. slots informado por EcoBici
        # 2. free_bikes + empty_slots como fallback
        # ---------------------------
        df["capacity"] = df["slots"].fillna(
            df["accounted_slots"]
        )

        # ---------------------------
        # Slots no explicados
        # ---------------------------
        #
        # En los datos reales observamos que:
        #
        # slots >= free_bikes + empty_slots
        #
        # No podemos afirmar que la diferencia represente
        # docks fuera de servicio, por lo que utilizamos
        # un nombre neutral.
        # ---------------------------
        df["unaccounted_slots"] = (
            df["capacity"]
            - df["accounted_slots"]
        )

        # ---------------------------
        # Porcentajes
        # ---------------------------
        df["occupancy_pct"] = float("nan")
        df["empty_slots_pct"] = float("nan")
        df["accounted_slots_pct"] = float("nan")
        df["unaccounted_slots_pct"] = float("nan")

        valid_capacity = (
            df["capacity"].notna()
            & (df["capacity"] > 0)
        )

        # Bicicletas disponibles / capacidad
        df.loc[
            valid_capacity,
            "occupancy_pct"
        ] = (
            df.loc[
                valid_capacity,
                "free_bikes"
            ]
            / df.loc[
                valid_capacity,
                "capacity"
            ]
            * 100
        )

        # Espacios vacíos / capacidad
        df.loc[
            valid_capacity,
            "empty_slots_pct"
        ] = (
            df.loc[
                valid_capacity,
                "empty_slots"
            ]
            / df.loc[
                valid_capacity,
                "capacity"
            ]
            * 100
        )

        # Slots contabilizados / capacidad
        df.loc[
            valid_capacity,
            "accounted_slots_pct"
        ] = (
            df.loc[
                valid_capacity,
                "accounted_slots"
            ]
            / df.loc[
                valid_capacity,
                "capacity"
            ]
            * 100
        )

        # Slots no explicados / capacidad
        df.loc[
            valid_capacity,
            "unaccounted_slots_pct"
        ] = (
            df.loc[
                valid_capacity,
                "unaccounted_slots"
            ]
            / df.loc[
                valid_capacity,
                "capacity"
            ]
            * 100
        )

        # -------------------------------------------------
        # 8. Validaciones de calidad
        # -------------------------------------------------
        def quality_check(row):

            reasons = []

            # -------------------------
            # Identificación
            # -------------------------
            if (
                pd.isna(row["station_id"])
                or not str(row["station_id"]).strip()
            ):
                reasons.append(
                    "missing_station_id"
                )

            if (
                pd.isna(row["station_name"])
                or not str(row["station_name"]).strip()
            ):
                reasons.append(
                    "missing_station_name"
                )

            if (
                pd.isna(row["snapshot_id"])
                or not str(row["snapshot_id"]).strip()
            ):
                reasons.append(
                    "missing_snapshot_id"
                )

            # -------------------------
            # Tiempo
            # -------------------------
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

            # -------------------------
            # Coordenadas
            # -------------------------
            if (
                pd.isna(row["latitude"])
                or row["latitude"] < -90
                or row["latitude"] > 90
            ):
                reasons.append(
                    "invalid_latitude"
                )

            if (
                pd.isna(row["longitude"])
                or row["longitude"] < -180
                or row["longitude"] > 180
            ):
                reasons.append(
                    "invalid_longitude"
                )

            # -------------------------
            # Bicicletas / slots
            # -------------------------
            if (
                pd.isna(row["free_bikes"])
                or row["free_bikes"] < 0
            ):
                reasons.append(
                    "invalid_free_bikes"
                )

            if (
                pd.isna(row["empty_slots"])
                or row["empty_slots"] < 0
            ):
                reasons.append(
                    "invalid_empty_slots"
                )

            if (
                pd.isna(row["capacity"])
                or row["capacity"] <= 0
            ):
                reasons.append(
                    "invalid_capacity"
                )

            # Si free_bikes + empty_slots supera capacity,
            # existe una inconsistencia física.
            if (
                pd.notna(row["capacity"])
                and pd.notna(row["accounted_slots"])
                and row["accounted_slots"]
                > row["capacity"]
            ):
                reasons.append(
                    "accounted_slots_exceeds_capacity"
                )

            # -------------------------
            # Estado operativo
            # -------------------------
            if pd.isna(row["renting"]):
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
                pd.notna(row["renting"])
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
                and row["returning_allowed"]
                not in [0, 1]
            ):
                reasons.append(
                    "invalid_returning_status"
                )

            return "|".join(reasons)

        df["quarantine_reason"] = df.apply(
            quality_check,
            axis=1,
        )

        # -------------------------------------------------
        # 9. Separar válidos e inválidos
        # -------------------------------------------------
        quarantine = df[
            df["quarantine_reason"] != ""
        ].copy()

        valid = df[
            df["quarantine_reason"] == ""
        ].copy()

        # -------------------------------------------------
        # 10. Estado operacional
        # -------------------------------------------------
        #
        # 1 / 1 -> operativa
        # 0 / 1 -> solo devolución
        # 1 / 0 -> solo retiro
        # 0 / 0 -> fuera de servicio
        # -------------------------------------------------
        def operational_status(row):

            if (
                row["renting"] == 1
                and row["returning_allowed"] == 1
            ):
                return "operativa"

            if (
                row["renting"] == 0
                and row["returning_allowed"] == 1
            ):
                return "solo_devolucion"

            if (
                row["renting"] == 1
                and row["returning_allowed"] == 0
            ):
                return "solo_retiro"

            if (
                row["renting"] == 0
                and row["returning_allowed"] == 0
            ):
                return "fuera_servicio"

            return "desconocido"

        valid["operational_status"] = (
            valid.apply(
                operational_status,
                axis=1,
            )
        )

        valid["is_fully_operational"] = (
            valid["operational_status"]
            == "operativa"
        )

        # -------------------------------------------------
        # 11. Metadata de auditoría Silver
        # -------------------------------------------------
        processed_at = datetime.now(
            timezone.utc
        )

        for dataframe in [
            valid,
            quarantine,
        ]:
            dataframe["_processed_at"] = (
                processed_at
            )

            dataframe["_source_table"] = (
                "bronze.citybikes_stations"
            )

        # -------------------------------------------------
        # 12. Metadata de snapshots procesados
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
            valid["snapshot_id"]
            .value_counts()
        )

        quarantine_counts = (
            quarantine["snapshot_id"]
            .value_counts()
        )

        snapshot_control["valid_rows"] = (
            snapshot_control["snapshot_id"]
            .map(valid_counts)
            .fillna(0)
            .astype(int)
        )

        snapshot_control["quarantine_rows"] = (
            snapshot_control["snapshot_id"]
            .map(quarantine_counts)
            .fillna(0)
            .astype(int)
        )

        snapshot_control["processed_at"] = (
            processed_at
        )

        # quarantine_reason solamente tiene sentido
        # para los registros rechazados.
        valid.drop(
            columns=["quarantine_reason"],
            inplace=True,
        )

        # -------------------------------------------------
        # 13. Persistencia incremental e idempotente
        # -------------------------------------------------
        #
        # Las tres escrituras se realizan dentro de una
        # misma transacción:
        #
        # 1. registros válidos
        # 2. quarantine
        # 3. snapshots procesados
        #
        # Si cualquiera falla, PostgreSQL hace rollback.
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
        # 14. Resumen de ejecución
        # -------------------------------------------------
        print(
            f"Snapshots nuevos procesados: "
            f"{df['snapshot_id'].nunique()}"
        )

        print(
            f"Válidas insertadas: {len(valid)}"
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
                ].value_counts(
                    dropna=False
                )
            )


    transform_bronze_to_silver()


citybikes_silver()