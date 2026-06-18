from datetime import datetime
import os
import re

from airflow.decorators import dag, task

SCHEDULE = "2-59/15 * * * *"
SILVER_TABLE = "silver.earthquakes"
SOURCE_TABLE = "bronze.usgs_earthquakes_raw"
DB_URI = (
    os.getenv("SOURCE_DB_URI")
    or f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:"
    f"{os.getenv('SOURCE_DB_PORT', '5432')}/{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


def _region_from_place(place):
    if not place:
        return "unknown"
    text = place.strip()
    candidate = text.rsplit(" of ", 1)[-1] if " of " in text else text.split(",")[-1]
    return re.sub(r"\s+", " ", candidate).strip() or "unknown"


def _severity_class(mag):
    if mag is None:
        return "sin_magnitud"
    if mag < 3:
        return "leve"
    if mag < 5:
        return "moderado"
    if mag < 7:
        return "fuerte"
    return "mayor"


@dag(
    dag_id="usgs_earthquakes_silver",
    start_date=datetime(2026, 1, 1),
    schedule=SCHEDULE,
    catchup=False,
    tags=["g09", "silver", "usgs", "earthquakes"],
    is_paused_upon_creation=False,
)
def usgs_earthquakes_silver():
    @task
    def build_silver() -> None:
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver"))
            conn.execute(sqlalchemy.text(f"""
                CREATE TABLE IF NOT EXISTS {SILVER_TABLE} (
                    event_id                  TEXT PRIMARY KEY,
                    place                     TEXT,
                    region                    TEXT,
                    mag                       NUMERIC,
                    mag_type                  TEXT,
                    event_time                TIMESTAMP,
                    updated_time              TIMESTAMP,
                    ingested_at               TIMESTAMP,
                    longitude                 NUMERIC,
                    latitude                  NUMERIC,
                    depth_km                  NUMERIC,
                    felt                      INTEGER,
                    cdi                       NUMERIC,
                    mmi                       NUMERIC,
                    alert                     TEXT,
                    tsunami                   INTEGER,
                    sig                       INTEGER,
                    status                    TEXT,
                    event_type                TEXT,
                    severity_class            TEXT,
                    latency_update_minutes    NUMERIC,
                    latency_ingestion_minutes NUMERIC,
                    _processed_at             TIMESTAMP
                )
            """))
            conn.execute(sqlalchemy.text(f"TRUNCATE TABLE {SILVER_TABLE}"))

        with engine.connect() as conn:
            if not conn.execute(
                sqlalchemy.text(f"SELECT to_regclass('{SOURCE_TABLE}')")
            ).scalar():
                print(f"{SOURCE_TABLE} no existe todavia.")
                return

        df = pd.read_sql("""
            SELECT DISTINCT ON (event_id)
                event_id, snapshot_id, ingested_at, event_time, updated_time, raw_json
            FROM bronze.usgs_earthquakes_raw
            ORDER BY event_id, updated_time DESC NULLS LAST, ingested_at DESC
        """, engine)

        if df.empty:
            print("Sin registros para cargar en Silver.")
            return

        now = datetime.utcnow()
        rows = []
        for rec in df.to_dict(orient="records"):
            feature = rec.get("raw_json") or {}
            props = feature.get("properties") or {}
            coords = (feature.get("geometry") or {}).get("coordinates") or [None, None, None]

            event_time = None if pd.isna(rec.get("event_time")) else rec.get("event_time")
            updated_time = None if pd.isna(rec.get("updated_time")) else rec.get("updated_time")
            ingested_at = None if pd.isna(rec.get("ingested_at")) else rec.get("ingested_at")
            mag = props.get("mag")

            rows.append({
                "event_id": rec["event_id"],
                "place": props.get("place"),
                "region": _region_from_place(props.get("place")),
                "mag": mag,
                "mag_type": props.get("magType"),
                "event_time": event_time,
                "updated_time": updated_time,
                "ingested_at": ingested_at,
                "longitude": coords[0] if len(coords) > 0 else None,
                "latitude": coords[1] if len(coords) > 1 else None,
                "depth_km": coords[2] if len(coords) > 2 else None,
                "felt": props.get("felt"),
                "cdi": props.get("cdi"),
                "mmi": props.get("mmi"),
                "alert": props.get("alert"),
                "tsunami": props.get("tsunami"),
                "sig": props.get("sig"),
                "status": props.get("status"),
                "event_type": props.get("type"),
                "severity_class": _severity_class(mag),
                "latency_update_minutes": (
                    (updated_time - event_time).total_seconds() / 60
                    if event_time and updated_time else None
                ),
                "latency_ingestion_minutes": (
                    (ingested_at - event_time).total_seconds() / 60
                    if event_time and ingested_at else None
                ),
                "_processed_at": now,
            })

        pd.DataFrame(rows).to_sql("earthquakes", engine, schema="silver", if_exists="append", index=False)
        print(f"Silver: {len(rows)} eventos cargados")

    build_silver()


usgs_earthquakes_silver()
