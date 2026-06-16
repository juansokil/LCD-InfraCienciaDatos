CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS bronze.usgs_earthquakes_raw (
    event_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    ingested_at TIMESTAMP NOT NULL,
    source TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    event_time TIMESTAMP,
    updated_time TIMESTAMP,
    raw_json JSONB NOT NULL,
    PRIMARY KEY (event_id, snapshot_id)
);
