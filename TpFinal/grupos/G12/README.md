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

Tabla `bronze.raw_earthquakes` (la crea `init.sql` al arrancar la base). Guardamos cada sismo tal como viene de la API, sin tocarlo:

- `id`: id del sismo en el USGS
- `type`: tipo de objeto GeoJSON (`Feature`)
- `properties`: JSON con los datos del sismo (magnitud, lugar, hora, alerta, etc.)
- `geometry`: JSON con las coordenadas (longitud, latitud y profundidad)
- `earthquake_id` y `version_updated`: id y fecha de la versión del USGS, para saber si ya lo teníamos
- `ingested_at`: cuándo lo bajamos (metadato de auditoría)

Antes de guardar, Bronze compara contra lo que ya está y solo agrega sismos nuevos o versiones nuevas (el USGS corrige magnitudes después). Si no hay nada nuevo, no guarda nada. Además, el JSON crudo de cada llamada se guarda en `Stack/data/raw/usgs_earthquakes/ds=AAAA-MM-DD/`. La llamada a la API tiene un timeout de 30 segundos.

Para cargar historia hay una función aparte, `ingestar_historico_30dias()` en `Stack/scripts/ingest_bronze.py`, que trae los últimos 30 días. Se corre a mano una sola vez.

### Silver

Tabla `silver.earthquakes`, un registro por evento. Se rearma completa en cada corrida a partir de Bronze. Guarda **todos** los eventos (sismos, voladuras, explosiones): el filtro de solo sismos se hace en Gold.

- **Columnas útiles en español**: `id_sismo`, `titulo`, `magnitud`, `tipo_magnitud`, `tipo_evento`, `lugar`, `alerta`, `significancia`, `alerta_tsunami`.
- **Coordenadas**: `geometry.coordinates` viene como [longitud, latitud, profundidad] y lo separamos en `longitud`, `latitud` y `profundidad_km`.
- **Ubicación y región**: el lugar se separa en la última coma. "121 km SE of Atka, Alaska" queda `ubicacion` = "121 km SE of Atka" y `region` = "Alaska".
- **Regiones unificadas**: las abreviaturas pasan a nombre completo (CA -> California, NV -> Nevada, MX -> Mexico) y se saca el " region" del final (Japan region -> Japan).
- **Deduplicación**: un registro por sismo, el más nuevo según la fecha de versión del USGS (`ROW_NUMBER()` por `id_sismo`, ordenado por `updated`).
- **Tipos y nulos**: la magnitud vacía queda en NULL y la alerta de tsunami vacía en 0.
- **Fechas**: la API manda milisegundos; los pasamos a `fecha_hora_utc` y `fecha` (en UTC).
- **Enriquecimiento**: `escala_magnitud` (Menor < 3, Leve < 4.5, Moderado < 6, Fuerte / Mayor) y `energia_joules` (log10(E) = 4.8 + 1.5 * magnitud).

### Gold

Modelo estrella con una tabla de hechos y cuatro dimensiones. Solo entran los eventos de tipo `earthquake`. Se rearma completo en cada corrida y tiene claves primarias y foráneas.

- `gold.fact_terremoto`: un registro por terremoto. `id_terremoto` (PK), las claves a las dimensiones (`fecha_id`, `id_ubicacion`, `id_magnitud`, `id_alerta`), `magnitud`, `profundidad`, `latitud`, `longitud`, `significancia` y `cantidad_terremoto` (siempre 1, para sumar).
- `gold.dim_fecha`: `fecha_id` (AAAAMMDD), `fecha`, `anio`, `mes`, `dia`, `dia_semana`.
- `gold.dim_ubicacion`: `id_ubicacion`, `region`, `ubicacion`.
- `gold.dim_magnitud`: `id_magnitud`, `tipo_magnitud` (mb, ml, mww, ...).
- `gold.dim_alerta`: `id_alerta`, `tipo_alerta` (green, yellow, orange, red y unknown). Cuando el USGS no informa alerta queda como `unknown`, no como verde.

## Dashboard

Streamlit en http://localhost:8501, lee solo las tablas de Gold:

- **Inicio** (`app.py`): total de terremotos, magnitud máxima y promedio, profundidad promedio, los 10 más fuertes y las regiones donde más tiembla.
- **Evolución**: terremotos y magnitud por día, y actividad por día de la semana (con filtro de fechas).
- **Magnitudes y alertas**: distribución de magnitudes, escalas que usa el USGS, alertas y profundidad vs. magnitud.
- **Mapa**: un punto por terremoto, con filtro de magnitud mínima y color por profundidad o alerta.

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

No hay que tocar nada más. Los schemas y la tabla de Bronze se crean solos (`init.sql`) y el DAG arranca activado. Corre cada 15 minutos (:00, :15, :30 y :45), así que la primera corrida es en el próximo cuarto de hora. Si no querés esperar, lo podés disparar a mano con el botón de play en Airflow.

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
├── init.sql                 # crea los schemas y la tabla bronze.raw_earthquakes
├── .env                     # variables del stack (credenciales de prueba)
├── dags/
│   └── dag_usgs_earthquakes.py
├── scripts/
│   ├── ingest_bronze.py
│   ├── transform_silver.py
│   └── transform_gold.py
├── data/raw/                # JSON crudos de la API
└── dashboard/               # Streamlit sobre las tablas Gold
    ├── app.py               # pagina de inicio
    ├── db.py                # conexion a la base
    └── pages/               # Evolucion, Magnitudes y alertas, Mapa
```

Para cargar 30 días de historia (opcional, se corre una sola vez con el stack levantado):

```bash
docker compose exec airflow python -c "import sys; sys.path.insert(0, '/opt/airflow'); from scripts.ingest_bronze import ingestar_historico_30dias; ingestar_historico_30dias()"
```

Después hay que correr el DAG una vez (play en Airflow) para que llegue a Silver y Gold.
