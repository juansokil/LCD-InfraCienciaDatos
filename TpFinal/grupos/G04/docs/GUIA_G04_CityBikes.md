# Guía del proyecto — G04 · CityBikes

> Guía de estudio para entender el sistema de punta a punta, ejecutarlo y defenderlo en la presentación.
> Léela junto al `README.md` (resumen) y al código en `dags/` y `dashboard/`.

---

## 1. En una frase

Tomamos datos **en vivo** de la API pública de **CityBikes** (estado de estaciones de bici compartida), los procesamos con un pipeline de tres capas **Bronze → Silver → Gold** orquestado por **Airflow**, los guardamos en **PostgreSQL** y los mostramos en un **dashboard de Streamlit**. Todo corre con un solo comando: `docker compose up`.

La pregunta de negocio que respondemos: **¿qué estaciones se saturan o se quedan sin bicis, y a qué horas del día?**

---

## 2. Arquitectura general

```
            ┌─────────────┐     ┌──────────────────────── Airflow ────────────────────────┐
 API        │ CityBikes   │     │   DAG bronze (5')   DAG silver (10')   DAG gold (15')     │
 pública →  │ /v2/networks│ →   │        │                  │                  │            │
            └─────────────┘     └────────┼──────────────────┼──────────────────┼───────────┘
                                         ▼                  ▼                  ▼
                                   ┌──────────────────── PostgreSQL (warehouse) ───────────┐
                                   │  schema bronze  →  schema silver  →  schema gold       │
                                   └────────────────────────────────────────────┬──────────┘
                                                                                 ▼
                                                                        ┌──────────────────┐
                                                                        │ Streamlit         │
                                                                        │ dashboard (Gold)  │
                                                                        └──────────────────┘
```

### Los 4 servicios de Docker Compose

| Servicio | Imagen | Para qué |
|---|---|---|
| `warehouse` | `postgres:17-alpine` | Base de datos con **nuestros datos** (schemas bronze/silver/gold). Puerto host **5433**. |
| `airflow_db` | `postgres:17-alpine` | Base de **metadatos de Airflow** (separada del warehouse). |
| `airflow` | `apache/airflow:3.1.5` (custom) | Orquestador. Corre en modo `standalone`. UI en **8080**. |
| `dashboard` | `python:3.11-slim` (custom) | App Streamlit que consume Gold. UI en **8501**. |

Por qué dos Postgres: el de Airflow guarda su propio estado interno (runs, logs, etc.). Mezclarlo con los datos del negocio sería desprolijo y frágil. Por eso están separados.

---

## 3. La fuente: API de CityBikes

- **URL base:** `https://api.citybik.es/v2`
- **Auth:** ninguna. **Rate limit:** ~300 req/hora.
- **Refresh real:** la disponibilidad cambia cada **2–5 minutos**.
- **Endpoint que usamos:** `GET /v2/networks/{id}?fields=name,location,stations`
- **Redes que trackeamos** (configurable en `.env`, variable `CITYBIKES_NETWORKS`):
  - `ecobici` → Buenos Aires
  - `bicing` → Barcelona
  - `divvy` → Chicago

Cada respuesta trae, por red, la lista de estaciones con: nombre, latitud/longitud, `free_bikes` (bicis disponibles), `empty_slots` (lugares libres) y campos extra.

**Por qué solo 3 redes:** la API tiene ~560. Fijamos 3 para poder comparar ciudades y, sobre todo, para quedar **muy por debajo del rate limit** (3 redes × 12 corridas/hora ≈ 36 req/h de 300).

---

## 4. Modelo de datos por capa

La idea **medallion**: los datos van "subiendo de calidad" capa por capa. Bronze es crudo, Silver está limpio, Gold está listo para consumir.

### 🥉 Bronze — `bronze.citybikes_stations_raw`

Ingesta cruda: una fila por **estación × snapshot**, guardando el objeto JSON tal cual llega.

Columnas clave: `network_id`, `station_id`, `station_payload` (**JSONB**, el JSON crudo), `ingested_at` (cuándo lo trajimos), `source`.

Regla de oro de Bronze: **no se transforma nada**. Si la API manda basura, se guarda igual. Sirve como respaldo y permite reprocesar Silver/Gold si cambiamos la lógica.

### 🥈 Silver — `silver.station_status`

Datos **aplanados, tipados y validados**. Acá se "abre" el JSON de Bronze y se calculan métricas por snapshot.

Columnas clave: `free_bikes`, `empty_slots`, `total_slots` (= free + empty), `occupancy_rate` (ocupación 0–1), flags `is_empty` / `is_full`, `snapshot_at`. **PK:** `(station_id, snapshot_at)`.

Qué limpieza hace: descarta filas con `free_bikes` nulo o negativo, valida lat/long dentro de rango, normaliza `empty_slots` nulo. Es **incremental**: solo procesa lo nuevo desde Bronze usando un **watermark** (la última `snapshot_at` ya procesada).

### 🥇 Gold — modelo dimensional para consumo

Cuatro tablas pensadas para el dashboard:

| Tabla | Qué es | Para qué |
|---|---|---|
| `gold.dim_network` | Dimensión de redes (red, ciudad, país) | Filtro y comparación por ciudad |
| `gold.dim_station` | Dimensión de estaciones (nombre, ubicación, capacidad, first/last seen) | Joins y rankings |
| `gold.fact_station_hourly` | **Hecho**: agregados por estación y **hora** (promedios, mín/máx, % tiempo vacía/llena) | Patrón por hora, estaciones críticas |
| `gold.station_current` | Última foto de cada estación | Mapa "en vivo" y KPIs |

Esto es un mini **modelo estrella**: un hecho (`fact_station_hourly`) rodeado de dimensiones (`dim_network`, `dim_station`).

---

## 5. Los DAGs de Airflow

Están en `dags/`, uno por capa. Todos usan el **Task SDK de Airflow 3** (`from airflow.sdk import dag, task`) y comparten utilidades en `dags/citybikes_common.py` (config de redes + conexión al warehouse).

| DAG | Archivo | Schedule | Tareas (en orden) |
|---|---|---|---|
| `citybikes_bronze` | `01-bronze/citybikes_bronze.py` | `*/5 * * * *` (cada 5 min) | `ensure_table` → `ingest` |
| `citybikes_silver` | `02-silver/citybikes_silver.py` | `*/10 * * * *` (cada 10 min) | `ensure_table` → `transform` |
| `citybikes_gold` | `03-gold/citybikes_gold.py` | `*/15 * * * *` (cada 15 min) | `ensure_tables` → `build_dimensions` → `build_fact` |

**Tres propiedades que hay que saber explicar:**

1. **Arrancan solos** — `is_paused_upon_creation=False`. No hay que activarlos a mano en la UI.
2. **Schedule definido** — cada uno con su intervalo (no `schedule=None`), elegido según el refresh de la API.
3. **Idempotentes** — correr un DAG dos veces no duplica datos:
   - Silver usa `ON CONFLICT (station_id, snapshot_at) DO NOTHING`.
   - Gold hace `ON CONFLICT ... DO UPDATE` (upsert) en las dimensiones y, para el hecho, **borra y recalcula** las últimas 3 horas.

**Detalle clave (Bronze):** todas las estaciones de una corrida comparten el mismo `ingested_at` (un único "reloj" por snapshot). Si una red falla, se loguea un warning pero **no rompe** el DAG entero.

---

## 6. El dashboard (Streamlit)

Carpeta `dashboard/`. Estructura:
- `app.py` — página de inicio + chequeo de salud (cuántas filas hay en Gold).
- `db.py` — conexión reutilizable al warehouse (cachea queries 60s).
- `pages/1_Gold.py` — las vistas de negocio.

**Regla importante:** el dashboard consume **solo el schema `gold`**. Nunca lee Bronze ni Silver (eso es "backend" del pipeline). Esto es algo que el docente puede preguntar.

Qué muestra: KPIs en vivo (estaciones, bicis, % vacías/llenas), mapa de disponibilidad por ocupación, patrón de ocupación por hora del día, ranking de estaciones más críticas (sin bicis / saturadas) y comparación entre ciudades. Todo con un filtro por red que afecta todas las vistas.

---

## 7. El flujo completo, paso a paso (qué pasa cuando levantás el stack)

1. `docker compose up` crea los 4 contenedores.
2. El `warehouse` arranca y ejecuta `init.sql` (montado en `/docker-entrypoint-initdb.d/`), que **crea los schemas y todas las tablas**. Así el dashboard nunca falla por "tabla inexistente", incluso sin datos todavía.
3. Airflow arranca en `standalone` y, como los DAGs vienen despausados, empieza a correrlos según su schedule.
4. **~5 min:** primer corrida de Bronze → hay JSON crudo en `bronze.citybikes_stations_raw`.
5. **~10 min:** Silver procesa lo nuevo → `silver.station_status` con datos limpios.
6. **~15 min:** Gold arma dimensiones + hecho + foto actual → el dashboard se empieza a poblar.

---

## 8. Decisiones técnicas (y por qué) — para la defensa

- **Usamos `ingested_at` como eje temporal, no el `timestamp` de la API.** El `timestamp` venía en formato inconsistente y poco confiable; igual lo guardamos crudo en Bronze.
- **Transformaciones en SQL sobre JSONB.** Limpieza y agregación se hacen en Postgres (declarativo y eficiente) en vez de traer todo a pandas.
- **Incremental + idempotente.** Watermark en Silver y upsert/recálculo en Gold para no duplicar y poder reprocesar.
- **Dos Postgres separados** (datos vs. metadatos de Airflow) para aislar responsabilidades.
- **Tablas creadas en `init.sql` y también con `CREATE TABLE IF NOT EXISTS` dentro de cada DAG** (cinturón y tiradores: el stack arranca robusto en cualquier orden).

---

## 9. Cómo ejecutar el proyecto (paso a paso)

### Requisitos
- **Docker Desktop** instalado y corriendo.
- Los puertos **8080**, **8501** y **5433** libres en tu máquina.

### Pasos

```bash
# 1. Ubicarse en la carpeta del grupo
cd TpFinal/grupos/G04

# 2. Crear el archivo de variables de entorno a partir del ejemplo
cp .env.example .env        # en Windows PowerShell: copy .env.example .env

# 3. Levantar todo el stack (la primera vez tarda: construye imágenes)
docker compose up --build
```

Dejá la terminal abierta; vas a ver los logs de los 4 servicios.

### Accesos una vez levantado

| Qué | URL | Notas |
|---|---|---|
| **Airflow UI** | http://localhost:8080 | Usuario `admin`. La contraseña la genera Airflow standalone. |
| **Dashboard** | http://localhost:8501 | Se va poblando a medida que Gold tiene datos. |
| **Warehouse** | `localhost:5433` (db `citybikes`) | Para conectarse con DBeaver/psql si querés inspeccionar tablas. |

**Contraseña de Airflow** (en otra terminal):
```bash
docker compose logs airflow | grep -i password
```

### Verificar que el pipeline funciona

1. Entrá a **Airflow** (8080): deberías ver los 3 DAGs **activos** (no en pausa) y, con el correr de los minutos, corridas en verde.
2. Esperá ~15 min y abrí el **dashboard** (8501): los KPIs y el mapa se empiezan a llenar.
3. (Opcional) Conectate al warehouse y revisá:
   ```sql
   SELECT count(*) FROM bronze.citybikes_stations_raw;
   SELECT count(*) FROM silver.station_status;
   SELECT count(*) FROM gold.station_current;
   ```

### Para apagar
```bash
docker compose down        # apaga y borra contenedores (los datos quedan en el volumen)
docker compose down -v      # además borra los volúmenes (empieza de cero)
```

### Problemas típicos
- **Conflicto de puertos:** si tenés el stack del curso u otra cosa usando 8080/8501/5432, apagalo o cambiá los mapeos en `docker-compose.yml`. Por eso el warehouse usa **5433** en el host.
- **El dashboard dice "todavía no hay datos":** es normal los primeros minutos. Esperá a que Gold corra (cada 15 min).
- **Reconstruir tras cambios de código:** `docker compose up --build`.

---

## 10. Preguntas probables del docente (y cómo responder)

- **¿Por qué arquitectura medallion?** Separa responsabilidades: Bronze guarda crudo (trazabilidad/reproceso), Silver limpia y tipa, Gold modela para consumo. Si cambia la lógica de negocio, reproceso desde Bronze sin volver a pegarle a la API.
- **¿Por qué el dashboard consume solo Gold?** Gold es el modelo final, pensado para responder preguntas de negocio rápido. Bronze/Silver son etapas internas del pipeline.
- **¿Cómo evitan duplicados si un DAG corre dos veces?** Idempotencia: watermark en Silver + `ON CONFLICT DO NOTHING`; upsert en las dimensiones de Gold; el hecho se borra y recalcula por ventana de horas.
- **¿Por qué Airflow y no un cron?** Orquestación con dependencias entre tareas, reintentos, visibilidad de corridas, scheduling declarativo y backfill si hiciera falta.
- **¿Cómo arranca solo?** `init.sql` crea schemas/tablas; DAGs despausados (`is_paused_upon_creation=False`) con schedule; el dashboard se conecta y muestra Gold.
- **¿Por qué dos bases Postgres?** Una para metadatos de Airflow, otra para los datos del negocio: aislamiento y prolijidad.
- **¿Qué pasa si la API falla o cambia?** Bronze captura un warning por red caída sin romper el DAG; el resto sigue. Como guardamos crudo, podemos reprocesar.
- **¿Por qué el eje temporal es `ingested_at`?** El `timestamp` de la API era inconsistente; usamos el momento de ingesta, que controlamos nosotros.

---

## 11. Glosario rápido

- **Medallion (Bronze/Silver/Gold):** patrón de capas que sube la calidad/estructura del dato en cada paso.
- **DAG:** *Directed Acyclic Graph*. En Airflow, un flujo de tareas con dependencias; acá, un pipeline por capa.
- **Idempotencia:** correr lo mismo N veces da el mismo resultado (no duplica).
- **Watermark:** marca del último dato procesado, para procesar solo lo nuevo (incremental).
- **JSONB:** tipo de Postgres para guardar JSON consultable de forma eficiente.
- **Upsert:** "insertar o actualizar" (`INSERT ... ON CONFLICT ... DO UPDATE`).
- **Modelo dimensional / estrella:** un **hecho** (métricas) rodeado de **dimensiones** (contexto: estación, red, tiempo).
- **`occupancy_rate`:** proporción de ocupación de la estación (bicis vs. capacidad).
- **Standalone (Airflow):** modo todo-en-uno que levanta api-server + scheduler + dag-processor en un contenedor.

---

## 12. Reparto sugerido para exponer (5–6 min, hasta 10)

Como todos tienen que poder responder, conviene que cada uno domine una parte pero entienda el conjunto:

1. **Intro + pregunta de negocio + API** (diapos 1–2)
2. **Arquitectura medallion + stack** (diapo 3)
3. **Qué hace cada capa + DAGs** (diapo 4)
4. **Demo del dashboard en vivo** (diapo 5) — levantado en `localhost:8501`
5. **Dificultades, decisiones y arranque automático** (diapo 6)

Tip: tengan el stack **ya levantado** antes de empezar para que el dashboard tenga datos durante la demo.
