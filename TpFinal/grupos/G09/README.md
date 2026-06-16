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


