WITH ultimos_sismos AS (
    SELECT DISTINCT ON (event_id)
        event_id,
        payload,
        source_updated_ms
    FROM bronze.sismos_raw
    WHERE source_updated_ms IS NOT NULL
      AND payload->'properties'->>'time' IS NOT NULL
    ORDER BY
        event_id,
        source_updated_ms DESC,
        ingested_at DESC,
        id DESC
)

INSERT INTO silver.sismos (
    event_id,
    magnitud,
    lugar,
    fecha_utc,
    latitud,
    longitud,
    profundidad_km,
    source_updated_ms
)

SELECT
    event_id,
    (payload->'properties'->>'mag')::DOUBLE PRECISION,
    payload->'properties'->>'place',
    TO_TIMESTAMP(
        (payload->'properties'->>'time')::DOUBLE PRECISION / 1000
    ),
    (payload->'geometry'->'coordinates'->>1)::DOUBLE PRECISION,
    (payload->'geometry'->'coordinates'->>0)::DOUBLE PRECISION,
    (payload->'geometry'->'coordinates'->>2)::DOUBLE PRECISION,
    source_updated_ms

FROM ultimos_sismos

ON CONFLICT (event_id)
DO UPDATE SET
    magnitud = EXCLUDED.magnitud,
    lugar = EXCLUDED.lugar,
    fecha_utc = EXCLUDED.fecha_utc,
    latitud = EXCLUDED.latitud,
    longitud = EXCLUDED.longitud,
    profundidad_km = EXCLUDED.profundidad_km,
    source_updated_ms = EXCLUDED.source_updated_ms,
    processed_at = CURRENT_TIMESTAMP

WHERE EXCLUDED.source_updated_ms > silver.sismos.source_updated_ms;
