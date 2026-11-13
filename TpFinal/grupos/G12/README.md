# TP Final - G12 - Sismos (USGS Earthquakes)

Pipeline de datos sobre los sismos que publica el USGS (Servicio Geológico de Estados Unidos). Airflow baja los datos de la API, los guarda en Postgres en tres capas (Bronze, Silver y Gold) y un dashboard muestra los resultados de Gold. Todo levanta con Docker.

---

## Integrantes

- Lautaro Ramos (@lautira2006)
- Valentina Varisco (@valenvarisco)
- Francisco Baudracco (@franbaudra)
- Ramiro Kammerer (usuario de GitHub pendiente)

## API elegida

- **Nombre**: `USGS Earthquakes`
- **URL**: `https://earthquake.usgs.gov/fdsnws/event/1/query`
- **Endpoint que usa el DAG**: `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson` (sismos de magnitud 2.5 o más del último día)
- **Descripcion**: `Devuelve información de sismos en tiempo real y datos históricos en formato GeoJSON, incluyendo magnitud, profundidad, coordenadas y alertas de tsunami.`
- **Auth**: `sin auth`
- **API key**: `no necesita`
- **Refresh**: `Tiempo real cada vez que ocurre un sismo`

## Modelo de datos

Las transformaciones de Silver y Gold están hechas en SQL (`Stack/scripts/transform_silver.py` y `Stack/scripts/transform_gold.py`). El DAG `dag_usgs_earthquakes_pipeline` corre las tres capas en orden: bronze -> silver -> gold.

### Bronze

Tabla `bronze.raw_earthquakes`. Guardamos cada sismo tal como viene de la API, sin tocarlo:

- `id`: id del sismo en el USGS
- `type`: tipo de objeto GeoJSON (`Feature`)
- `properties`: JSON con los datos del sismo (magnitud, lugar, hora, alerta de tsunami, etc.)
- `geometry`: JSON con las coordenadas (longitud, latitud y profundidad)
- `ingested_at`: cuándo lo bajamos (metadato de auditoría)

Cada corrida agrega filas (append), así que el mismo sismo puede aparecer varias veces. Además, el JSON crudo de cada llamada se guarda en `Stack/data/raw/usgs_earthquakes/ds=AAAA-MM-DD/`.

Para cargar historia hay una función aparte, `ingestar_historico_30dias()` en `Stack/scripts/ingest_bronze.py`, que trae los últimos 30 días. Se corre a mano una sola vez.

### Silver

Tabla `silver.earthquakes`, un registro por sismo. Se rearma completa en cada corrida a partir de Bronze:

- **Parseo**: saca del JSON la magnitud, el lugar, la alerta de tsunami, la fecha y hora (viene en milisegundos y la pasamos a timestamp) y las coordenadas.
- **Deduplicación**: si un sismo aparece varias veces en Bronze, nos quedamos con la versión más nueva (`ROW_NUMBER()` por `earthquake_id`, ordenado por `ingested_at`).
- **Tipos y nulos**: la magnitud vacía queda en NULL y la alerta de tsunami vacía queda en 0.
- **Enriquecimiento**:
  - `escala_magnitud`: Menor (< 3), Leve (< 4.5), Moderado (< 6) y Fuerte / Mayor (6 o más). Si no hay magnitud queda como Desconocida.
  - `energia_joules`: energía estimada con log10(E) = 4.8 + 1.5 * magnitud
  - `region`: lo que está después de la última coma del lugar (ej: "10 km NE of Tokyo, Japan" -> "Japan")
  - `event_date`: la fecha del sismo, para agrupar por día

### Gold

Modelo estrella: una tabla de hechos con una dimensión, más un agregado para el ranking. También se rearma completo en cada corrida.

- `gold.dim_region`: `region_id`, `region`
- `gold.fact_sismos_diarios`: un registro por día y región, con `cantidad_sismos`, `magnitud_promedio`, `magnitud_maxima`, `energia_total_joules` y `alertas_tsunami`. Se une con `dim_region` por `region_id`.
- `gold.agg_ranking_zonas`: un registro por región con el total de sismos, magnitud promedio y máxima, profundidad promedio y alertas de tsunami.

Preguntas que responde el dashboard:

- ¿Cómo cambia la actividad sísmica día a día?
- ¿En qué zonas tiembla más, y en cuáles más fuerte?
- ¿Qué zonas tuvieron alertas de tsunami?

## Como levantar el stack

Todo se corre desde la raíz del repo. Si tenés levantado el stack del curso, apagalo antes porque usa los mismos puertos:

```bash
docker compose -f stack/docker-compose.yml stop
```

Después:

```bash
cd TpFinal/grupos/G12/Stack
docker compose up -d --build   # el .env ya viene en el repo
```

No hay que tocar nada más. Los schemas `bronze`, `silver` y `gold` se crean solos (`init.sql`) y el DAG arranca activado. Corre cada 15 minutos (:00, :15, :30 y :45), así que la primera corrida es en el próximo cuarto de hora. Si no querés esperar, lo podés disparar a mano con el botón de play en Airflow.

**Accesos**:
- Airflow UI: http://localhost:8080 (no pide usuario ni contraseña: el `.env` deja entrar a todos como admin)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432`, base `InfraCienciaDatos`, usuario `admin` / contraseña `admin`

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

```
TpFinal/grupos/G12/Stack/
├── docker-compose.yml       # warehouse + airflow_db + airflow + dashboard
├── Dockerfile               # imagen de Airflow 3.1.5 con pandas, requests, sqlalchemy
├── Dockerfile.postgres      # Postgres 17 con el init.sql adentro
├── init.sql                 # crea los schemas bronze, silver y gold
├── .env                     # variables del stack (credenciales de prueba)
├── dags/
│   └── dag_usgs_earthquakes.py
├── scripts/
│   ├── ingest_bronze.py
│   ├── transform_silver.py
│   └── transform_gold.py
├── data/raw/                # JSON crudos de la API
└── dashboard/               # Streamlit sobre las tablas Gold
```
