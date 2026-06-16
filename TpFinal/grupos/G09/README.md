# TP Final - G09 - USGS Earthquakes

## Integrantes

- Juan Cruz Torrano (@jucruto-ops)
- Nombre Apellido (@usuario-github)

## API elegida

- **Nombre**: USGS Earthquake Catalog / Real-time Earthquake Feeds
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/
- **Descripcion**: API publica de eventos sismicos en formato GeoJSON. Devuelve terremotos recientes con magnitud, ubicacion, profundidad, tiempo del evento, ultima actualizacion, intensidad reportada/estimada y metadatos de impacto.
- **Frecuencia del pipeline**: cada 15 minutos (`*/15 * * * *`), para capturar eventos recientes sin sobreconsultar la API.

## Pregunta de negocio

**Que regiones concentran mayor frecuencia y severidad sismica reciente, y que relacion hay entre magnitud, profundidad e intensidad percibida?**

Subpreguntas que va a responder el dashboard:

- Donde se registran mas terremotos recientes?
- Donde ocurren los eventos de mayor magnitud?
- Que relacion hay entre magnitud, profundidad e intensidad percibida (`cdi` / `mmi`)?
- Que eventos deberian priorizarse por severidad, tsunami, alerta o significancia?
- Cuanto tarda nuestro pipeline en capturar eventos desde que ocurrieron?

> Nota tecnica: la API no informa "duracion de percepcion". Por eso el analisis se enfoca en intensidad percibida/reportada, profundidad, magnitud y latencias aproximadas.

## Modelo de datos

### Bronze

Tabla cruda: `bronze.usgs_earthquakes_raw`

Grano: una fila por evento sismico por snapshot de ingesta.

Columnas previstas:

- `event_id`: identificador USGS del evento.
- `snapshot_id`: identificador de la corrida de ingesta.
- `ingested_at`: timestamp de captura del pipeline.
- `source`: fuente del dato (`usgs-earthquakes`).
- `feed_url`: endpoint consultado.
- `event_time`: timestamp original del evento.
- `updated_time`: timestamp de ultima actualizacion del evento en USGS.
- `raw_json`: feature GeoJSON completo tal como llega desde la API.

### Silver

Tabla limpia: `silver.earthquakes`

Transformaciones previstas:

- Parsear GeoJSON a tabla relacional.
- Extraer longitud, latitud y profundidad desde `geometry.coordinates`.
- Tipar magnitud, profundidad, timestamps e indicadores numericos.
- Normalizar `place`, `mag_type`, `status`, `alert` y `type`.
- Deduplicar por `event_id`, conservando la version mas actualizada.
- Calcular `latency_update_minutes = updated_time - event_time`.
- Calcular `latency_ingestion_minutes = ingested_at - event_time`.
- Clasificar severidad por magnitud: leve, moderado, fuerte, mayor.

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

### Gold

Modelo orientado al dashboard:

- `gold.dim_region`: regiones derivadas desde `place`.
- `gold.dim_time`: fecha, hora, dia de semana y franja horaria.
- `gold.fact_earthquake_events`: hechos por evento con magnitud, profundidad, intensidad y flags de impacto.
- `gold.fact_region_daily`: agregados diarios por region.
- `gold.earthquake_risk_summary`: ranking de zonas/eventos por frecuencia y severidad.

El dashboard Streamlit va a consumir exclusivamente tablas Gold.

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

## Estado actual

- Stack base con Airflow, Postgres warehouse, Postgres metadata y Streamlit.
- DAG Bronze: `usgs_earthquakes_bronze`.
- DAG Silver: `usgs_earthquakes_silver`.
- DAG Gold: `usgs_earthquakes_gold`.
- Dashboard inicial sobre tablas Gold.
Los tres DAGs tienen `schedule="*/15 * * * *"` e `is_paused_upon_creation=False`.
