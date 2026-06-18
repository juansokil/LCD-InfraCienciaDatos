# TP Final - G09 - USGS Earthquakes

## Integrantes

- Juan Cruz Torrano (@jucruto-ops)

## API elegida

- **Nombre**: USGS Earthquake Catalog / Real-time Earthquake Feeds
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/
- **Descripcion**: API publica de eventos sismicos en formato GeoJSON. Devuelve terremotos recientes con magnitud, ubicacion, profundidad, tiempo del evento, ultima actualizacion, intensidad reportada/estimada y metadatos de impacto.
- **Auth**: Sin autenticacion
- **Refresh**: Tiempo real (feed `all_day` con eventos del ultimo dia)
- **Frecuencia del pipeline**: cada 15 minutos, con offsets entre capas para evitar que Silver o Gold corran antes de que termine la capa anterior.

## Pregunta de negocio

**Que regiones concentran mayor frecuencia y severidad sismica reciente, y que relacion hay entre magnitud, profundidad e intensidad percibida?**

El dashboard responde en tres vistas:

| Vista | Pregunta |
|---|---|
| Concentracion | Donde se registran mas terremotos y donde ocurren los de mayor magnitud |
| Relacion | Como se relacionan magnitud, profundidad e intensidad (CDI / MMI) |
| Tablas | Que eventos priorizar y como evoluciona la actividad diaria por region |

> **Nota tecnica**: la API no informa "duracion de percepcion". El analisis se enfoca en intensidad percibida/reportada, profundidad, magnitud y latencias del pipeline.

## Modelo de datos

### Bronze

Tabla `bronze.usgs_earthquakes_raw`: ingesta cruda del feed GeoJSON de USGS.

- Un **snapshot por corrida** (`snapshot_id` = timestamp de ingesta).
- Se conserva el JSON completo de cada evento (`raw_json`) mas metadatos de auditoria.
- Clave primaria `(event_id, snapshot_id)` para acumular historial de snapshots sin duplicar dentro del mismo snapshot.

Columnas principales: `event_id`, `snapshot_id`, `ingested_at`, `source`, `feed_url`, `event_time`, `updated_time`, `raw_json`.

### Silver

Tabla `silver.earthquakes`: ultimo estado conocido de cada evento, listo para analisis.

Transformaciones aplicadas:

- Parseo de GeoJSON a formato tabular (coordenadas, propiedades, tiempos).
- Deduplicacion con `DISTINCT ON (event_id)` tomando la ultima actualizacion.
- Extraccion de `region` a partir del campo `place`.
- Clasificacion de `severity_class` segun magnitud (leve / moderado / fuerte / mayor).
- Calculo de latencias: `latency_update_minutes` (evento → ultima actualizacion USGS) y `latency_ingestion_minutes` (evento → ingesta en nuestro pipeline).

Columnas principales: `event_id`, `place`, `region`, `mag`, `depth_km`, `latitude`, `longitude`, `cdi`, `mmi`, `alert`, `tsunami`, `sig`, `severity_class`, `latency_*`, timestamps de evento e ingesta.

### Gold

Tablas analiticas reconstruidas en cada corrida del DAG Gold:

| Tabla | Proposito |
|---|---|
| `gold.fact_earthquake_events` | Un registro por evento con todos los atributos de analisis (base del dashboard) |
| `gold.fact_region_daily` | Agregados diarios por region (conteo, mag max/prom, profundidad prom, eventos severos) |
| `gold.earthquake_risk_summary` | Resumen por region para ranking y KPIs (frecuencia, severidad, latencia prom.) |

## Dashboard (Streamlit)

El dashboard consume **solo la capa Gold** y esta organizado en tres paginas:

1. **Concentracion** (`/Concentracion`): KPIs de actividad, mapa geografico con severidad y ranking de regiones por frecuencia y magnitud maxima.
2. **Relacion** (`/Relacion`): scatter magnitud vs profundidad, magnitud vs intensidad (CDI/MMI) y grafico integrador magnitud-intensidad coloreado por banda de profundidad.
3. **Tablas** (`/Tablas`): eventos prioritarios (severidad, tsunami, alerta, significancia) y evolucion diaria por region.

Acceso: http://localhost:8501

## Interpretacion de resultados

Hallazgos observables con los datos del feed reciente:

- **Frecuencia vs severidad**: la mayoria de eventos son leves o moderados; los fuertes/mayores son minoria. Las regiones con mas eventos no siempre coinciden con las de mayor magnitud maxima.
- **Magnitud e intensidad**: existe una tendencia positiva (a mayor magnitud, mayor CDI/MMI), pero con **alta dispersion**: dos eventos de magnitud similar pueden tener intensidades muy distintas.
- **Profundidad como moderador**: a igual magnitud, los eventos mas superficiales (0–35 km) tienden a registrar mayor intensidad percibida que los profundos (>70 km).
- **CDI vs MMI**: CDI depende de reportes ciudadanos ("Did You Feel It?") y cubre menos eventos; MMI es una estimacion de USGS y suele estar mas completa.
- **Latencia del pipeline**: la latencia promedio de ingesta refleja el intervalo de schedule (15 min), la ventana del feed (`all_day`) y el momento en que el evento entro al catalogo USGS.

## Decisiones tecnicas

- **Offsets de schedule**: Bronze `*/15`, Silver `2-59/15`, Gold `4-59/15` para encadenar capas sin condiciones de carrera.
- **Silver con TRUNCATE**: se mantiene el ultimo estado de cada evento; el historial de snapshots queda en Bronze.
- **Gold con rebuild**: `DROP + CREATE TABLE AS` en cada corrida — simple y consistente para un TP con volumen moderado (~600 eventos).
- **Region por texto**: se extrae del campo `place` (ultimo segmento despues de coma o " of ") en lugar de geocodificacion inversa.
- **Dashboard multi-pagina**: separa las tres preguntas de negocio y facilita la presentacion oral.

## Como levantar el stack

```bash
cd TpFinal/grupos/G09/
cp .env.example .env
docker compose up -d --build
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:

- Airflow UI: http://localhost:8080
- Dashboard: http://localhost:8501
- Postgres: localhost:5432 (credenciales en `.env`)

**Apagar**:

```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

> Si tenes otro stack usando los mismos puertos (5432, 8080, 8501), apagalo antes o cambia los mapeos en `docker-compose.yml`.

## Ejecucion del pipeline

Los DAGs se ejecutan cada 15 minutos con offsets entre capas:

- `usgs_earthquakes_bronze`: ingesta el feed GeoJSON y guarda snapshots en `bronze.usgs_earthquakes_raw`.
- `usgs_earthquakes_silver`: normaliza, deduplica y carga `silver.earthquakes`.
- `usgs_earthquakes_gold`: reconstruye `gold.fact_earthquake_events`, `gold.fact_region_daily` y `gold.earthquake_risk_summary`.

Todos los DAGs tienen `is_paused_upon_creation=False` y arrancan solos al levantar el stack.

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

## Entrega del TP (Pull Request)

El TP se entrega via **Pull Request** en GitHub, no solo subiendo codigo a una branch.

### Pasos

1. **Trabajar en la branch del grupo** (ya creada):

   ```bash
   git checkout tp-final/G09
   ```

2. **Commitear y pushear** todos los cambios:

   ```bash
   git add TpFinal/grupos/G09/
   git commit -m "tp-final/G09: dashboard multi-pagina y README actualizado"
   git push -u origin tp-final/G09
   ```

   > Si el push falla con error 403, tu usuario de GitHub no tiene permiso de escritura en el repo. Pedile al docente o al dueno del repo (`juansokil`) que te agregue como colaborador, o pushea con la cuenta correcta.

3. **Abrir el PR** contra `main` en GitHub (si no existe todavia):

   - Titulo: `TP Final - G09 - USGS Earthquakes`
   - Body: integrantes, API elegida, pregunta de negocio (1-2 oraciones)

4. **Marcar como "Ready for review"** — esto es lo que oficializa la entrega:

   - Entra al PR en GitHub.
   - Si esta en **Draft** (borrador), hace click en **"Ready for review"** (arriba a la derecha del PR).
   - Eso le avisa al docente que el TP esta listo para evaluar.

### Resumen

| Estado del PR | Significado |
|---|---|
| **Draft** | Trabajo en progreso, no es entrega |
| **Ready for review** | Entrega formal, el docente puede evaluar |
| **Merged** | Aprobado e integrado a `main` (lo hace el docente) |

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md).

```
TpFinal/grupos/G09/
├── README.md
├── docker-compose.yml
├── dags/
│   ├── 01-bronze/usgs_earthquakes_bronze.py
│   ├── 02-silver/usgs_earthquakes_silver.py
│   └── 03-gold/usgs_earthquakes_gold.py
└── dashboard/
    ├── app.py                  # hub de navegacion
    ├── db.py                   # conexion a Postgres
    ├── constants.py            # colores y configuracion de graficos
    ├── data.py                 # carga de tablas Gold
    └── pages/
        ├── 1_Concentracion.py
        ├── 2_Relacion.py
        └── 3_Tablas.py
```
