# TP Final - G09 - USGS Earthquakes

## Integrantes

- Juan Cruz Torrano (@jucruto-ops)

## API elegida

- **Nombre**: USGS Earthquake Catalog / Real-time Feeds
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/
- **Descripcion**: Feed GeoJSON con terremotos recientes. Trae magnitud, profundidad, coordenadas, intensidad reportada (CDI), intensidad estimada (MMI), alertas y flags de tsunami.
- **Auth**: Sin autenticacion
- **Refresh**: Tiempo real (feed `all_day`)

## Pregunta de negocio

Que regiones concentran mayor frecuencia y severidad sismica reciente, y que relacion hay entre magnitud, profundidad e intensidad percibida.

La API no informa duracion de percepcion, asi que el analisis se centra en intensidad percibida/reportada, profundidad y latencias del pipeline.

## Modelo de datos

### Bronze

`bronze.usgs_earthquakes_raw`: un snapshot por corrida del DAG. Guarda el JSON crudo de cada evento con metadatos de auditoria (`ingested_at`, `source`, `feed_url`). Clave primaria `(event_id, snapshot_id)` para acumular historial sin duplicados dentro del mismo snapshot.

### Silver

`silver.earthquakes`: ultimo estado conocido de cada evento.

- Parseo de GeoJSON a tabular (coordenadas, propiedades, tiempos).
- Deduplicacion con `DISTINCT ON (event_id)` tomando la ultima actualizacion.
- `region` extraida del campo `place` (ultimo segmento despues de coma o " of ").
- `severity_class`: leve / moderado / fuerte / mayor segun magnitud.
- `latency_update_minutes`: tiempo entre ocurrencia y ultima actualizacion en USGS.
- `latency_ingestion_minutes`: tiempo entre ocurrencia e ingesta en nuestro pipeline.

### Gold

`fact_earthquake_events`  Un registro por evento con todos los atributos (base del dashboard) 
`fact_region_daily`  Conteo, mag max/prom, profundidad prom y eventos severos por region y dia 
`earthquake_risk_summary`  Resumen por region: frecuencia, severidad acumulada, latencia prom. 

## Dashboard

Tres paginas en Streamlit, cada una sobre una parte de la pregunta:

1. **Concentracion**: mapa de eventos con severidad y ranking de regiones por frecuencia y magnitud maxima.
2. **Relacion**: scatter magnitud vs profundidad, magnitud vs intensidad (CDI/MMI) y un grafico magnitud-intensidad coloreado por banda de profundidad.
3. **Tablas**: eventos prioritarios (fuertes, tsunami, alerta, sig >= 500) y evolucion diaria por region.

Acceso: http://localhost:8501

## Hallazgos

- La mayoria de eventos son leves o moderados; fuertes/mayores son minoria.
- Las regiones con mas eventos no siempre son las de mayor magnitud maxima.
- A mayor magnitud hay tendencia a mayor intensidad percibida, pero con bastante dispersion.
- Los eventos mas superficiales (< 35 km) tienden a registrar mayor CDI/MMI a igual magnitud.
- CDI cubre pocos eventos (depende del reporte ciudadano); MMI es estimada por USGS y esta mas completa.

## Decisiones tecnicas

- Offsets de schedule: Bronze `*/15`, Silver `2-59/15`, Gold `4-59/15`, para que no corran encimadas.
- Silver con TRUNCATE: queda el ultimo estado de cada evento; el historial vive en Bronze.
- Gold con `DROP + CREATE TABLE AS` en cada corrida, suficiente para el volumen del feed (~600 eventos).
- Region por texto, sin geocodificacion inversa.

## Como levantar el stack

```bash
cd TpFinal/grupos/G09/
cp .env.example .env
docker compose up -d --build
```

Esperar ~30s a que Airflow inicialice. Accesos:

- Airflow: http://localhost:8080
- Dashboard: http://localhost:8501
- Postgres: localhost:5432

## Ejecucion

Los tres DAGs arrancan solos (`is_paused_upon_creation=False`). Si se corren a mano, el orden es:

1. `usgs_earthquakes_bronze`
2. `usgs_earthquakes_silver`
3. `usgs_earthquakes_gold`

## Validacion

```sql
SELECT 'bronze.usgs_earthquakes_raw' AS tabla, count(*) AS filas FROM bronze.usgs_earthquakes_raw
UNION ALL SELECT 'silver.earthquakes', count(*) FROM silver.earthquakes
UNION ALL SELECT 'gold.fact_earthquake_events', count(*) FROM gold.fact_earthquake_events
UNION ALL SELECT 'gold.fact_region_daily', count(*) FROM gold.fact_region_daily
UNION ALL SELECT 'gold.earthquake_risk_summary', count(*) FROM gold.earthquake_risk_summary;
```

Corrida validada: bronze 3391 / silver 589 / gold events 589 / gold daily 324 / gold summary 230.

