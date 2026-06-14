from datetime import datetime, timezone
import re

import pandas as pd
import sqlalchemy
from airflow.sdk import dag, task
from sqlalchemy import text


DB_URI = (
    "postgresql+psycopg2://"
    "admin:admin@data_warehouse:5432/"
    "InfraCienciaDatos"
)

BRONZE_QUERY = """
SELECT
    snapshot_id,
    ingested_at,
    source,
    network_id,
    network_name,
    station_id,
    station_uid,
    station_name,
    latitude,
    longitude,
    free_bikes,
    empty_slots,
    station_timestamp,
    last_updated,
    is_renting,
    is_returning,
    address,
    slots,
    normal_bikes,
    virtual
FROM bronze.ecobici_stations_raw
"""


def _clean_text(value):
    if pd.isna(value):
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


@dag(
    dag_id="ecobici_silver",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["prod", "silver", "citybikes", "ecobici"],
)
def ecobici_silver():

    @task(retries=2)
    def read_bronze() -> int:
        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            total_rows = conn.execute(
                text("SELECT COUNT(*) FROM bronze.ecobici_stations_raw")
            ).scalar_one()

        print(f"Filas leidas en Bronze: {total_rows}")
        return int(total_rows)

    @task(retries=2)
    def transform_silver(bronze_count: int) -> dict:
        engine = sqlalchemy.create_engine(DB_URI)

        df = pd.read_sql(BRONZE_QUERY, engine)
        print(f"Bronze rows reportadas por read_bronze: {bronze_count}")
        print(f"Bronze rows cargadas para transformar: {len(df)}")

        for col in ["ingested_at", "station_timestamp", "last_updated"]:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

        for col in ["latitude", "longitude"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        for col in ["free_bikes", "empty_slots", "slots", "normal_bikes"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        for col in ["source", "network_id", "network_name", "station_id", "station_uid"]:
            df[col] = df[col].apply(_clean_text)

        df["station_name"] = df["station_name"].apply(_clean_text)
        df["address"] = df["address"].apply(_clean_text)

        for col in ["is_renting", "is_returning", "virtual"]:
            df[col] = df[col].map(lambda x: None if pd.isna(x) else bool(x))

        duplicate_mask = df.duplicated(subset=["snapshot_id", "station_id"], keep=False)
        coords_mask = (
            df["latitude"].between(-35, -34, inclusive="both")
            & df["longitude"].between(-59, -58, inclusive="both")
        )
        non_negative_mask = df[["free_bikes", "empty_slots", "slots", "normal_bikes"]].ge(0).all(axis=1)
        required_mask = df[
            [
                "snapshot_id",
                "ingested_at",
                "source",
                "network_id",
                "station_id",
                "station_name",
                "latitude",
                "longitude",
                "free_bikes",
                "empty_slots",
                "station_timestamp",
                "last_updated",
                "address",
                "slots",
                "normal_bikes",
            ]
        ].notna().all(axis=1)

        df["quarantine_reason"] = ""
        df.loc[~required_mask, "quarantine_reason"] += "MISSING_CRITICAL_FIELDS;"
        df.loc[~non_negative_mask, "quarantine_reason"] += "NEGATIVE_VALUES;"
        df.loc[~coords_mask, "quarantine_reason"] += "INVALID_COORDINATES;"
        df.loc[duplicate_mask, "quarantine_reason"] += "DUPLICATE_RECORD;"
        df["quarantine_reason"] = df["quarantine_reason"].str.rstrip(";")

        quarantine_df = df[df["quarantine_reason"] != ""].copy()
        silver_df = df[df["quarantine_reason"] == ""].copy()

        processed_at = datetime.now(timezone.utc)

        silver_df["total_capacity"] = silver_df["slots"].astype("Int64")
        silver_df["occupancy_ratio"] = (
            silver_df["free_bikes"].astype(float) / silver_df["total_capacity"].astype(float)
        ).where(silver_df["total_capacity"] > 0)
        silver_df["cleaned_at"] = processed_at

        quarantine_df["quarantined_at"] = processed_at

        silver_cols = [
            "snapshot_id",
            "ingested_at",
            "source",
            "network_id",
            "network_name",
            "station_id",
            "station_uid",
            "station_name",
            "latitude",
            "longitude",
            "free_bikes",
            "empty_slots",
            "station_timestamp",
            "last_updated",
            "is_renting",
            "is_returning",
            "address",
            "slots",
            "normal_bikes",
            "virtual",
            "total_capacity",
            "occupancy_ratio",
            "cleaned_at",
        ]

        quarantine_cols = [
            "snapshot_id",
            "ingested_at",
            "source",
            "network_id",
            "network_name",
            "station_id",
            "station_uid",
            "station_name",
            "latitude",
            "longitude",
            "free_bikes",
            "empty_slots",
            "station_timestamp",
            "last_updated",
            "is_renting",
            "is_returning",
            "address",
            "slots",
            "normal_bikes",
            "virtual",
            "quarantine_reason",
            "quarantined_at",
        ]

        silver_df = silver_df[silver_cols].copy()
        quarantine_df = quarantine_df[quarantine_cols].copy()

        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))

            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS silver.ecobici_stations (
                        snapshot_id TEXT NOT NULL,
                        ingested_at TIMESTAMPTZ NOT NULL,
                        source TEXT NOT NULL,
                        network_id TEXT,
                        network_name TEXT,
                        station_id TEXT NOT NULL,
                        station_uid TEXT,
                        station_name TEXT,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        free_bikes INTEGER,
                        empty_slots INTEGER,
                        station_timestamp TIMESTAMPTZ,
                        last_updated TIMESTAMPTZ,
                        is_renting BOOLEAN,
                        is_returning BOOLEAN,
                        address TEXT,
                        slots INTEGER,
                        normal_bikes INTEGER,
                        virtual BOOLEAN,
                        total_capacity INTEGER,
                        occupancy_ratio DOUBLE PRECISION,
                        cleaned_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )

            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS silver.ecobici_stations_quarantine (
                        snapshot_id TEXT,
                        ingested_at TIMESTAMPTZ,
                        source TEXT,
                        network_id TEXT,
                        network_name TEXT,
                        station_id TEXT,
                        station_uid TEXT,
                        station_name TEXT,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        free_bikes INTEGER,
                        empty_slots INTEGER,
                        station_timestamp TIMESTAMPTZ,
                        last_updated TIMESTAMPTZ,
                        is_renting BOOLEAN,
                        is_returning BOOLEAN,
                        address TEXT,
                        slots INTEGER,
                        normal_bikes INTEGER,
                        virtual BOOLEAN,
                        quarantine_reason TEXT NOT NULL,
                        quarantined_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )

            conn.execute(text("TRUNCATE TABLE silver.ecobici_stations"))
            conn.execute(text("TRUNCATE TABLE silver.ecobici_stations_quarantine"))

        dtype_silver = {
            "snapshot_id": sqlalchemy.Text(),
            "ingested_at": sqlalchemy.DateTime(timezone=True),
            "source": sqlalchemy.Text(),
            "network_id": sqlalchemy.Text(),
            "network_name": sqlalchemy.Text(),
            "station_id": sqlalchemy.Text(),
            "station_uid": sqlalchemy.Text(),
            "station_name": sqlalchemy.Text(),
            "latitude": sqlalchemy.Float(),
            "longitude": sqlalchemy.Float(),
            "free_bikes": sqlalchemy.Integer(),
            "empty_slots": sqlalchemy.Integer(),
            "station_timestamp": sqlalchemy.DateTime(timezone=True),
            "last_updated": sqlalchemy.DateTime(timezone=True),
            "is_renting": sqlalchemy.Boolean(),
            "is_returning": sqlalchemy.Boolean(),
            "address": sqlalchemy.Text(),
            "slots": sqlalchemy.Integer(),
            "normal_bikes": sqlalchemy.Integer(),
            "virtual": sqlalchemy.Boolean(),
            "total_capacity": sqlalchemy.Integer(),
            "occupancy_ratio": sqlalchemy.Float(),
            "cleaned_at": sqlalchemy.DateTime(timezone=True),
        }

        dtype_quarantine = {
            "snapshot_id": sqlalchemy.Text(),
            "ingested_at": sqlalchemy.DateTime(timezone=True),
            "source": sqlalchemy.Text(),
            "network_id": sqlalchemy.Text(),
            "network_name": sqlalchemy.Text(),
            "station_id": sqlalchemy.Text(),
            "station_uid": sqlalchemy.Text(),
            "station_name": sqlalchemy.Text(),
            "latitude": sqlalchemy.Float(),
            "longitude": sqlalchemy.Float(),
            "free_bikes": sqlalchemy.Integer(),
            "empty_slots": sqlalchemy.Integer(),
            "station_timestamp": sqlalchemy.DateTime(timezone=True),
            "last_updated": sqlalchemy.DateTime(timezone=True),
            "is_renting": sqlalchemy.Boolean(),
            "is_returning": sqlalchemy.Boolean(),
            "address": sqlalchemy.Text(),
            "slots": sqlalchemy.Integer(),
            "normal_bikes": sqlalchemy.Integer(),
            "virtual": sqlalchemy.Boolean(),
            "quarantine_reason": sqlalchemy.Text(),
            "quarantined_at": sqlalchemy.DateTime(timezone=True),
        }

        if not silver_df.empty:
            silver_df.to_sql(
                "ecobici_stations",
                engine,
                schema="silver",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
                dtype=dtype_silver,
            )

        if not quarantine_df.empty:
            quarantine_df.to_sql(
                "ecobici_stations_quarantine",
                engine,
                schema="silver",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
                dtype=dtype_quarantine,
            )

        print(f"Silver rows: {len(silver_df)}")
        print(f"Quarantine rows: {len(quarantine_df)}")

        return {
            "bronze_rows": int(bronze_count),
            "silver_rows": int(len(silver_df)),
            "quarantine_rows": int(len(quarantine_df)),
        }

    bronze_count = read_bronze()
    transform_silver(bronze_count)


ecobici_silver()