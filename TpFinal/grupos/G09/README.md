# TP Final - G09 - USGS Earthquakes

## Integrantes

- Juan Cruz Torrano (@jucruto-ops)


## API elegida

- **Nombre**: USGS Earthquake Catalog / Real-time Earthquake Feeds
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/
- **Descripcion**: API publica de eventos sismicos en formato GeoJSON. Devuelve terremotos recientes con magnitud, ubicacion, profundidad, tiempo del evento, ultima actualizacion, intensidad reportada/estimada y metadatos de impacto.
- **Frecuencia del pipeline**: cada 15 minutos, con offsets entre capas para evitar que Silver o Gold corran antes de que termine la capa anterior.

## Pregunta de negocio

**Que regiones concentran mayor frecuencia y severidad sismica reciente, y que relacion hay entre magnitud, profundidad e intensidad percibida?**

Subpreguntas que va a responder el dashboard:

- Donde se registran mas terremotos recientes?
- Donde ocurren los eventos de mayor magnitud?
- Que relacion hay entre magnitud, profundidad e intensidad percibida (`cdi` / `mmi`)?
- Que eventos deberian priorizarse por severidad, tsunami, alerta o significancia?
- Cuanto tarda nuestro pipeline en capturar eventos desde que ocurrieron?

> Nota tecnica: la API no informa "duracion de percepcion". Por eso el analisis se enfoca en intensidad percibida/reportada, profundidad, magnitud y latencias aproximadas.

Columnas previstas:

- `event_id`
- `place`
- `region`
- `mag`
- `mag_type`
- `event_time`
- `updated_time`
- `ingested_at`
- `longitude`
- `latitude`
- `depth_km`
- `felt`
- `cdi`
- `mmi`
- `alert`
- `tsunami`
- `sig`
- `status`
- `severity_class`
- `latency_update_minutes`
- `latency_ingestion_minutes`

## Como levantar el stack

```bash
cd TpFinal/grupos/G09/
cp .env.example .env
docker compose up -d --build
```

**Accesos esperados**:

- Airflow UI: http://localhost:8080
- Dashboard Gold: http://localhost:8501
- Postgres: localhost:5432

## Ejecucion del pipeline

Los DAGs se ejecutan cada 15 minutos con offsets entre capas:

- `usgs_earthquakes_bronze`: ingesta el feed GeoJSON de USGS y guarda snapshots crudos en `bronze.usgs_earthquakes_raw`.
- `usgs_earthquakes_silver`: toma el ultimo estado de cada evento, normaliza campos y carga `silver.earthquakes`.
- `usgs_earthquakes_gold`: reconstruye las tablas analiticas `gold.fact_earthquake_events`, `gold.fact_region_daily` y `gold.earthquake_risk_summary`.

Si se ejecutan manualmente desde Airflow, correrlos en este orden:

1. `usgs_earthquakes_bronze`
2. `usgs_earthquakes_silver`
3. `usgs_earthquakes_gold`

## Validacion

Consulta de control en Postgres:

```sql
SELECT 'bronze.usgs_earthquakes_raw' AS tabla, count(*) AS filas FROM bronze.usgs_earthquakes_raw
UNION ALL SELECT 'silver.earthquakes', count(*) FROM silver.earthquakes
UNION ALL SELECT 'gold.fact_earthquake_events', count(*) FROM gold.fact_earthquake_events
UNION ALL SELECT 'gold.fact_region_daily', count(*) FROM gold.fact_region_daily
UNION ALL SELECT 'gold.earthquake_risk_summary', count(*) FROM gold.earthquake_risk_summary;
```

Resultado de una corrida validada:

- `bronze.usgs_earthquakes_raw`: 3391 filas
- `silver.earthquakes`: 589 filas
- `gold.fact_earthquake_events`: 589 filas
- `gold.fact_region_daily`: 324 filas
- `gold.earthquake_risk_summary`: 230 filas

El dashboard Streamlit consume la capa Gold y permite analizar distribucion geografica, ranking de regiones, magnitud versus profundidad, intensidad percibida y eventos prioritarios.
