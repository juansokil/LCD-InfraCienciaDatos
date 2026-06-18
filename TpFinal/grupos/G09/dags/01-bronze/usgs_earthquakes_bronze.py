from datetime import datetime, timezone
import json
import os

from airflow.decorators import dag, task

FEED_URL = os.getenv(
    "USGS_FEED_URL",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
)
SOURCE = "usgs-earthquakes"
SCHEDULE = "*/15 * * * *"
DB_URI = (
    os.getenv("SOURCE_DB_URI")
    or f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:"
    f"{os.getenv('SOURCE_DB_PORT', '5432')}/{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


def _ms_to_dt(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


@dag(
    dag_id="usgs_earthquakes_bronze",
    start_date=datetime(2026, 1, 1),
    schedule=SCHEDULE,
    catchup=False,
    tags=["g09", "bronze", "usgs", "earthquakes"],
    is_paused_upon_creation=False,
)
def usgs_earthquakes_bronze():
    @task(retries=2)
    def fetch_feed() -> dict:
        import requests

        response = requests.get(FEED_URL, timeout=30)
        response.raise_for_status()
        payload = response.json()
        print(f"Eventos recibidos: {len(payload.get('features', []))}")
        return payload

    @task
    def load_raw(payload: dict) -> None:
        import sqlalchemy

        now = datetime.utcnow()
        snapshot_id = now.strftime("%Y%m%d%H%M%S")

        rows = []
        for f in payload.get("features", []):
            if not f.get("id"):
                continue
            props = f.get("properties") or {}
            rows.append({
                "event_id": f["id"],
                "snapshot_id": snapshot_id,
                "ingested_at": now,
                "source": SOURCE,
                "feed_url": FEED_URL,
                "event_time": _ms_to_dt(props.get("time")),
                "updated_time": _ms_to_dt(props.get("updated")),
                "raw_json": json.dumps(f),
            })

        if not rows:
            print("Sin eventos para cargar.")
            return

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS bronze"))
            conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS bronze.usgs_earthquakes_raw (
                    event_id     TEXT      NOT NULL,
                    snapshot_id  TEXT      NOT NULL,
                    ingested_at  TIMESTAMP NOT NULL,
                    source       TEXT      NOT NULL,
                    feed_url     TEXT      NOT NULL,
                    event_time   TIMESTAMP,
                    updated_time TIMESTAMP,
                    raw_json     JSONB     NOT NULL,
                    PRIMARY KEY (event_id, snapshot_id)
                )
            """))

        stmt = sqlalchemy.text("""
            INSERT INTO bronze.usgs_earthquakes_raw (
                event_id, snapshot_id, ingested_at, source, feed_url,
                event_time, updated_time, raw_json
            )
            VALUES (
                :event_id, :snapshot_id, :ingested_at, :source, :feed_url,
                :event_time, :updated_time, CAST(:raw_json AS JSONB)
            )
            ON CONFLICT (event_id, snapshot_id) DO NOTHING
        """)
        with engine.begin() as conn:
            result = conn.execute(stmt, rows)
        print(f"Bronze: {result.rowcount} filas nuevas (snapshot {snapshot_id})")

    load_raw(fetch_feed())


usgs_earthquakes_bronze()
