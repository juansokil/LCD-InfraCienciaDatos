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
        # 2. Leer datos desde Bronze
        # -------------------------------------------------
        df = pd.read_sql(
            """
            SELECT
                network_id,
                network_name,
                station_id,
                station_name,
                latitude,
                longitude,
                station_timestamp,
                free_bikes,
                empty_slots,
                renting,
                returning_allowed,
                slots,
                ingested_at
            FROM bronze.citybikes_stations
            WHERE renting IS NOT NULL
              AND returning_allowed IS NOT NULL

            """,
            engine,
        )

        if df.empty:
            raise ValueError(
                "bronze.citybikes_stations no contiene datos"
            )

        print(f"Filas leídas desde Bronze: {len(df)}")

        # -------------------------------------------------
        # 3. Normalización técnica
        # -------------------------------------------------
        df["station_name"] = (
            df["station_name"]
            .astype("string")
            .str.strip()
        )

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

        df["ingested_at"] = pd.to_datetime(
            df["ingested_at"],
            errors="coerce",
            utc=True,
        )

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
        # 4. Deduplicación técnica
        # -------------------------------------------------
        df = (
            df.sort_values("ingested_at")
            .drop_duplicates(
                subset=[
                    "station_id",
                    "station_timestamp",
                ],
                keep="last",
            )
        )

        print(f"Filas luego de deduplicar: {len(df)}")

        # -------------------------------------------------
        # 5. Variables derivadas
        # -------------------------------------------------
        # CityBikes informa capacidad en slots.
        # Si falta, usamos bicicletas + espacios vacíos.
        fallback_capacity = (
            df["free_bikes"] + df["empty_slots"]
        )

        df["capacity"] = df["slots"].fillna(
            fallback_capacity
        )
        df["occupancy_pct"] = float("nan")

        valid_capacity = (
            df["capacity"].notna()
            & (df["capacity"] > 0)
        )

        df.loc[
            valid_capacity,
            "occupancy_pct"
        ] = (
            df.loc[valid_capacity, "free_bikes"]
            / df.loc[valid_capacity, "capacity"]
            * 100
        )

        # -------------------------------------------------
        # 6. Validaciones de calidad
        # -------------------------------------------------
        def quality_check(row):

            reasons = []

            if pd.isna(row["station_id"]):
                reasons.append("missing_station_id")

            if (
                pd.isna(row["station_name"])
                or not str(row["station_name"]).strip()
            ):
                reasons.append("missing_station_name")

            if pd.isna(row["station_timestamp"]):
                reasons.append("invalid_timestamp")

            if (
                pd.isna(row["latitude"])
                or row["latitude"] < -90
                or row["latitude"] > 90
            ):
                reasons.append("invalid_latitude")

            if (
                pd.isna(row["longitude"])
                or row["longitude"] < -180
                or row["longitude"] > 180
            ):
                reasons.append("invalid_longitude")

            if (
                pd.isna(row["free_bikes"])
                or row["free_bikes"] < 0
            ):
                reasons.append("invalid_free_bikes")

            if (
                pd.isna(row["empty_slots"])
                or row["empty_slots"] < 0
            ):
                reasons.append("invalid_empty_slots")

            if (
                pd.isna(row["capacity"])
                or row["capacity"] <= 0
            ):
                reasons.append("invalid_capacity")

            if pd.isna(row["renting"]):
                reasons.append("missing_renting_status")

            if pd.isna(row["returning_allowed"]):
                reasons.append("missing_returning_status")

            if (
                pd.notna(row["renting"])
                and row["renting"] not in [0, 1]
            ):
                reasons.append("invalid_renting_status")

            if (
                pd.notna(row["returning_allowed"])
                and row["returning_allowed"] not in [0, 1]
            ):
                reasons.append("invalid_returning_status")

            if (
                pd.notna(row["capacity"])
                and pd.notna(row["free_bikes"])
                and row["free_bikes"] > row["capacity"]
            ):
                reasons.append("free_bikes_exceeds_capacity")

            return "|".join(reasons)

        df["quarantine_reason"] = df.apply(
            quality_check,
            axis=1,
        )

        # -------------------------------------------------
        # 7. Separar válidos e inválidos
        # -------------------------------------------------
        quarantine = df[
            df["quarantine_reason"] != ""
        ].copy()

        valid = df[
            df["quarantine_reason"] == ""
        ].copy()

        # -------------------------------------------------
        # 8. Separar estaciones inactivas
        # -------------------------------------------------
        inactive_mask = (
            (valid["renting"] == 0)
            | (valid["returning_allowed"] == 0)
        )

        inactive = valid[inactive_mask].copy()

        active = valid[~inactive_mask].copy()

        # -------------------------------------------------
        # 9. Metadata de auditoría Silver
        # -------------------------------------------------
        processed_at = datetime.now(timezone.utc)

        for dataframe in [active, inactive, quarantine]:
            dataframe["_processed_at"] = processed_at
            dataframe["_source_table"] = (
                "bronze.citybikes_stations"
            )

        active.drop(
            columns=["quarantine_reason"],
            inplace=True,
        )

        inactive.drop(
            columns=["quarantine_reason"],
            inplace=True,
        )

        # -------------------------------------------------
        # 10. Guardar en Silver
        # -------------------------------------------------
        active.to_sql(
            "citybikes_stations",
            engine,
            schema="silver",
            if_exists="replace",
            index=False,
        )

        inactive.to_sql(
            "citybikes_inactive_stations",
            engine,
            schema="silver",
            if_exists="replace",
            index=False,
        )

        quarantine.to_sql(
            "quarantine_citybikes_stations",
            engine,
            schema="silver",
            if_exists="replace",
            index=False,
        )

        print(f"Activas: {len(active)}")
        print(f"Inactivas: {len(inactive)}")
        print(f"Quarantine: {len(quarantine)}")

    transform_bronze_to_silver()


citybikes_silver()