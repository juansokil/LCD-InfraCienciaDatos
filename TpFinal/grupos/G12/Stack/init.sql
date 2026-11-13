CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;


CREATE TABLE IF NOT EXISTS bronze.raw_earthquakes (
    type            text,
    properties      text,
    geometry        text,
    id              text,
    earthquake_id   text,
    version_updated timestamp,
    ingested_at     timestamp
);