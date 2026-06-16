# Guía del proyecto — G04 · CityBikes

> Documentación del proyecto: cómo funciona el sistema de punta a punta y cómo levantarlo.
> Léela junto al `README.md` (resumen) y al código en `dags/` y `dashboard/`.

---

## 1. En una frase

Tomamos datos **en vivo** de la API pública de **CityBikes** (estado de estaciones de bici compartida), los procesamos con un pipeline de tres capas **Bronze → Silver → Gold** orquestado por **Airflow**, los guardamos en **PostgreSQL** y los mostramos en un **dashboard de Streamlit**. Todo corre con un solo comando: `docker compose up`.

La pregunta de negocio que respondemos: **¿qué estaciones se saturan o se quedan sin bicis, y a qué horas del día?**

**Nuestro hallazgo (la respuesta):** entre las ~20 ciudades de Sudamérica, la región está **bien abastecida** (~8% de estaciones sin bicis en promedio). Las más ajustadas hoy: **Vitória (~32%)** y **Medellín (~16%)**; las más equilibradas: Curitiba, Nordelta, Cuenca (~0%). *(Son datos en vivo: los números cambian, pero el panorama se mantiene.)*

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
- **Auth:** ninguna. **Rate limit:** **300 req/hora** — límite **oficial** documentado (docs.citybik.es/api/), verificable en el header de respuesta `x-ratelimit-limit-hour: 300`; se resetea cada hora. (Para más, se pide API key a info@citybik.es o se auto-hostea.)
- **Refresh real:** la disponibilidad cambia cada **2–5 minutos**.
- **Endpoint que usamos:** `GET /v2/networks/{id}?fields=name,location,stations`
- **Redes que trackeamos** (configurable en `.env`, variable `CITYBIKES_NETWORKS`):
  - **Latinoamérica Sur** — todas las redes de Sudamérica disponibles en la API (~22 redes):
  - 🇦🇷 Argentina: Buenos Aires, Rosario, Nordelta
  - 🇧🇷 Brasil: São Paulo, Río de Janeiro, Curitiba, Porto Alegre, Salvador… (14 ciudades)
  - 🇨🇱 Chile: Santiago · 🇨🇴 Colombia: Bogotá, Medellín · 🇪🇨 Ecuador: Cuenca · 🇵🇪 Perú: Lima

Cada respuesta trae, por red, la lista de estaciones con: nombre, latitud/longitud, `free_bikes` (bicis disponibles), `empty_slots` (lugares libres) y campos extra.

**Por qué Sudamérica:** la API tiene ~560 redes del mundo. Trackeamos las de **Sudamérica** (~22) para comparar ciudades de la región (tema relatable), quedando bajo el **rate limit** (~22 × 12 corridas/hora ≈ 264 req/h de 300). Es configurable en el `.env`.

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

Carpeta `dashboard/`. Estructura (usa `st.navigation`: un router + vistas, por eso las transiciones son suaves):
- `app.py` — **router**: inyecta estilos + barra lateral una sola vez y enruta a las vistas.
- `ui.py` — estilos de marca (CSS), encabezados, tablas y la barra lateral con íconos.
- `db.py` — conexión reutilizable al warehouse (cachea queries 60s).
- `views/inicio.py` — inicio: arquitectura + **KPIs en vivo** (totales de todas las ciudades).
- `views/gold.py` — vistas de negocio: mapa, dona, patrón por hora, estaciones críticas y comparación.

**Regla importante:** el dashboard consume **solo el schema `gold`**. Nunca lee Bronze ni Silver (eso es "backend" del pipeline).

Qué muestra: KPIs en vivo (estaciones, bicis, % vacías/llenas), mapa de disponibilidad por ocupación, patrón de ocupación por hora del día, ranking de estaciones más críticas (sin bicis / saturadas) y comparación entre ciudades. Todo con un filtro por red que afecta todas las vistas.

### Qué cuenta cada gráfico (y cómo lo pensamos)

Todo el dashboard responde **una** pregunta: *¿qué estaciones se saturan o se quedan sin bicis, y a qué horas?* Cada gráfico ataca una parte:

| Gráfico | Qué cuenta | Cómo se hizo | Por qué lo pusimos |
|---|---|---|---|
| **4 KPIs** (estaciones, bicis, % sin bicis, % saturadas) | La foto del estado *ahora*, de un vistazo | Query sobre `gold.station_current` | Arrancar con el "titular" antes del detalle |
| **Mapa de disponibilidad** | *Dónde* están los problemas — cada punto una estación, color = ocupación, tamaño = capacidad | `st.map` sobre `station_current`, coloreado por `occupancy_rate` | Lo geográfico importa (¿se concentran en el centro?) |
| **Dona "Estaciones por nivel"** | El *resumen* del mapa en %: cuántas sin bicis / a medias / con bicis | Clasificamos cada estación por `occupancy_rate` en 3 niveles y contamos | El mapa muestra el "dónde", la dona el "cuánto" |
| **Patrón por hora del día** | El *"¿a qué horas?"* — ocupación media y % de estaciones vacías a lo largo del día, con el peor momento marcado | `gold.fact_station_hourly` agregado por hora | La disponibilidad cambia con la hora (ir/volver del trabajo) |
| **Estaciones más críticas (top 10)** | El *"¿qué estaciones?"* — las 10 que más tiempo pasan sin bicis y las 10 más saturadas | Ranking sobre `fact_station_hourly` por % del tiempo vacía/llena | Pasar de lo general a lo accionable (estaciones con nombre y apellido) |
| **Comparación entre ciudades** | Ocupación media de cada red — cuál está más crítica/equilibrada | Agregado por `city` sobre `fact_station_hourly` | De acá sale el **hallazgo** (comparar las ~20 ciudades de la región) |

**En resumen:** *"Los KPIs dan el estado general; el mapa y la dona muestran **dónde** y **cuánto**; el patrón por hora responde **a qué horas**; las estaciones críticas el **qué estaciones**; y la comparación nos dio el hallazgo entre ciudades."*

---

## 7. El flujo completo, paso a paso (qué pasa cuando levantás el stack)

1. `docker compose up` crea los 4 contenedores.
2. El `warehouse` arranca y ejecuta `init.sql` (montado en `/docker-entrypoint-initdb.d/`), que **crea los schemas y todas las tablas**. Así el dashboard nunca falla por "tabla inexistente", incluso sin datos todavía.
3. Airflow arranca en `standalone` y, como los DAGs vienen despausados, empieza a correrlos según su schedule.
4. **~5 min:** primer corrida de Bronze → hay JSON crudo en `bronze.citybikes_stations_raw`.
5. **~10 min:** Silver procesa lo nuevo → `silver.station_status` con datos limpios.
6. **~15 min:** Gold arma dimensiones + hecho + foto actual → el dashboard se empieza a poblar.

---

## 8. Decisiones técnicas (y por qué)

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

> **Para ver los datos hay 2 formas:** (1) el **dashboard** (Streamlit), abriendo http://localhost:8501 en cualquier navegador; (2) las **tablas crudas**, conectándote con **DBeaver** al warehouse (pasos detallados abajo).

| Qué | URL / Cómo entrar | Notas |
|---|---|---|
| **Dashboard** (Streamlit) | Abrí **http://localhost:8501** en el navegador | Tiene 2 páginas (Inicio + Gold) en el menú izquierdo. Se va poblando con Gold. |
| **Airflow UI** | Abrí **http://localhost:8080** en el navegador | Usuario `admin`. La contraseña la genera Airflow standalone (ver abajo). |
| **Warehouse** (Postgres) | `localhost:5433` (db `citybikes`) | Para ver las tablas crudas con **DBeaver**/psql (pasos abajo). |

### Entrar a Airflow (PASO A PASO)

Abrí **http://localhost:8080**. Te aparece un login con dos campos:

| Campo | Valor |
|---|---|
| **Username** | `admin` |
| **Password** | la que generó Airflow (en nuestra corrida: `8vy6cUvuXymmxnbr`) |

Clic en **Sign In** y entrás a la lista de DAGs.

**¿De dónde sale esa contraseña?** No la elegimos nosotros. Airflow corre en modo `standalone`, y la **primera vez** que arranca su *Simple Auth Manager* crea el usuario `admin` y le genera una **contraseña aleatoria** de 16 caracteres. La guarda en dos lados:
- en los **logs** del contenedor (al arrancar imprime `Password for user 'admin': ...`);
- en un **archivo** dentro del contenedor: `/opt/airflow/simple_auth_manager_passwords.json.generated` (un JSON tipo `{"admin": "..."}`).

**Para sacarla vos** (en otra terminal, **parado en la carpeta del proyecto** — la de G04, donde está el `docker-compose.yml`):
```bash
# Opción 1 — desde los logs (le pedís a Airflow su "diario" y filtrás la línea de la clave):
docker compose logs airflow | grep -i password

# Opción 2 — leyendo el archivo directo desde adentro del contenedor:
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```
Qué hace cada uno:
- `docker compose logs airflow` muestra **todo lo que imprimió** el contenedor desde que arrancó; `| grep -i password` **filtra** y deja solo las líneas que dicen "password" (el `-i` ignora mayúsculas/minúsculas).
- `docker compose exec airflow cat <archivo>` ejecuta un comando **adentro** del contenedor y te imprime el archivo donde Airflow dejó anotada la clave (`{"admin": "..."}`).

> ⚠️ Si te dice `no such service: airflow`, es porque **no estás parado en la carpeta del proyecto**. Hacé `cd` a `...\TpFinal\grupos\G04` y volvé a correrlo.

> Se **mantiene** entre reinicios normales (`restart` / `up`). Solo cambia si hacés `docker compose down -v` (borra los volúmenes): ahí Airflow genera una nueva y la volvés a sacar con los comandos de arriba. Por eso el valor de la tabla es el de *nuestra* corrida — en otra máquina puede salir distinto.

### Conectarse a la base de datos con DBeaver (PASO A PASO)

> Esto es lo que a varios les pidió "usuario y contraseña" y no sabían qué poner. Acá están **los datos exactos**.

El stack tiene que estar **levantado** (`docker compose up` corriendo). En DBeaver:

1. **Database → New Database Connection** → elegí **PostgreSQL** → *Next*.
2. Completá los campos así (salen del `.env`):

   | Campo | Valor |
   |---|---|
   | **Host** | `localhost` |
   | **Port** | `5433`. El warehouse se mapea a 5433 en tu máquina. |
   | **Database** | `citybikes` |
   | **Username** | `cb_user` |
   | **Password** | `changeme` |

3. (Opcional) Tildá **"Save password"** para no escribirla cada vez.
4. **Test Connection** → si dice *Connected*, *Finish*.
5. Para ver las tablas: en el árbol → **citybikes → Schemas → `bronze` / `silver` / `gold` → Tables**.

> 🔴 **El error típico**  es poner el puerto **5432**. Tiene que ser **5433** (en `docker-compose.yml` dice `"5433:5432"`: el 5432 es interno del contenedor, el 5433 es el de tu máquina). Y la base/usuario/clave salen del `.env` — si nunca lo creaste, corré `run.ps1` o `cp .env.example .env`.

Sin DBeaver, con **psql** desde otra terminal:
```bash
docker compose exec warehouse psql -U cb_user -d citybikes
# o, si tenés psql instalado en tu máquina:
psql -h localhost -p 5433 -U cb_user -d citybikes     # password: changeme
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
- **DBeaver dice `Connection to localhost:5432 refused`:** pusiste el puerto **5432**. El warehouse se mapea al **5433** en tu máquina (en `docker-compose.yml`: `"5433:5432"` → el 5432 es interno del contenedor). Cambiá el *Port* de la conexión a **5433** y conecta. (Pasa lo mismo con psql: usá `-p 5433`.)
- **Una corrida de `citybikes_gold` en rojo justo al levantar el stack:** es normal en **arranque en frío** — gold puede correr un segundo antes de que el warehouse termine de levantar, y da un error de conexión. Los DAGs tienen **`retries=3`** (espera 30 s y reintenta), así que **se pone verde solo** en el reintento o en la corrida siguiente (cada 15 min). No rompe nada: las tareas son idempotentes. Para confirmar que está sano: en el warehouse, `SELECT max(snapshot_at) FROM gold.station_current;` tiene que dar algo reciente.
- **El dashboard dice "todavía no hay datos":** es normal los primeros minutos. Esperá a que Gold corra (cada 15 min).
- **Reconstruir tras cambios de código:** `docker compose up --build`.

---

## 10. Cosas a tener en cuenta (decisiones y conceptos clave)

- **¿Por qué arquitectura medallion?** Separa responsabilidades: Bronze guarda crudo (trazabilidad/reproceso), Silver limpia y tipa, Gold modela para consumo. Si cambia la lógica de negocio, reproceso desde Bronze sin volver a pegarle a la API.
- **¿Por qué el dashboard consume solo Gold?** Gold es el modelo final, pensado para responder preguntas de negocio rápido. Bronze/Silver son etapas internas del pipeline.
- **¿Cómo evitan duplicados si un DAG corre dos veces?** Idempotencia: watermark en Silver + `ON CONFLICT DO NOTHING`; upsert en las dimensiones de Gold; el hecho se borra y recalcula por ventana de horas.
- **¿Por qué Airflow y no un cron?** Orquestación con dependencias entre tareas, reintentos, visibilidad de corridas, scheduling declarativo y backfill si hiciera falta.
- **¿Cómo arranca solo?** `init.sql` crea schemas/tablas; DAGs despausados (`is_paused_upon_creation=False`) con schedule; el dashboard se conecta y muestra Gold.
- **¿Por qué dos bases Postgres?** Una para metadatos de Airflow, otra para los datos del negocio: aislamiento y prolijidad.
- **¿Qué pasa si la API falla o cambia?** Bronze captura un warning por red caída sin romper el DAG; el resto sigue. Como guardamos crudo, podemos reprocesar.
- **¿Por qué el eje temporal es `ingested_at`?** El `timestamp` de la API era inconsistente; usamos el momento de ingesta, que controlamos nosotros.
- **¿Qué ciudades trackean?** ~20 redes de bici pública de **6 países de Sudamérica**: Argentina (Buenos Aires, Rosario, Nordelta), Brasil (São Paulo, Río…), Chile (Santiago), Colombia (Bogotá, Medellín), Ecuador (Cuenca) y Perú (Lima). Todas por la misma API de CityBikes.
- **¿Por qué Sudamérica? ¿Por qué esas redes?** La consigna no pide un número ("ideas orientativas, no requisitos"). Elegimos **toda Sudamérica** (~22 redes) para comparar la región, quedando **bajo el rate limit** (300 req/h; usamos ~264). Es configurable en el `.env`.
- **Si agregaran más ciudades, ¿hay que cambiar el código?** No. El pipeline es **genérico**: las redes salen de la variable `CITYBIKES_NETWORKS` del `.env`, y cada tabla separa las ciudades por la columna `network_id`. Agregar ciudades = cambiar el `.env`, sin tocar capas ni SQL.
- **¿Los datos son en vivo?** Sí: el **dashboard** consulta la base que el pipeline actualiza cada pocos minutos → los números cambian solos. El **PDF de la presentación** es una foto fija (no se actualiza, es lo normal).
- **¿Cuál fue el hallazgo?** Sudamérica está mayormente bien abastecida (~8% sin bicis entre 20 ciudades). Las más ajustadas hoy: Vitória (~32%) y Medellín (~16%); las más equilibradas: Curitiba, Nordelta, Cuenca (~0%).

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

## 12. Mapa de archivos — qué hace cada uno

| Archivo | Qué hace |
|---|---|
| `docker-compose.yml` | Define los **4 servicios** (warehouse, airflow_db, airflow, dashboard), puertos y volúmenes. |
| `Dockerfile` | Imagen de Airflow (base `apache/airflow:3.1.5` + deps de `requirements.txt`). |
| `init.sql` | Crea los schemas `bronze`/`silver`/`gold` y **todas las tablas** al arrancar el warehouse. |
| `requirements.txt` | Dependencias Python de Airflow (pandas, sqlalchemy, requests…). |
| `.env.example` → `.env` | Variables: credenciales del warehouse + `CITYBIKES_NETWORKS` (las ~22 redes de Sudamérica). |
| `run.ps1` / `run.sh` | Levantan todo con **un comando** (crean el `.env` si falta + `docker compose up`). |
| `dags/citybikes_common.py` | Config compartida: lista de redes (del `.env`) + conexión al warehouse. |
| `dags/01-bronze/citybikes_bronze.py` | **DAG Bronze**: baja el JSON crudo de la API a `bronze` (cada 5 min). |
| `dags/02-silver/citybikes_silver.py` | **DAG Silver**: aplana/tipa/valida y descarta inactivas → `silver` (cada 10 min). |
| `dags/03-gold/citybikes_gold.py` | **DAG Gold**: dimensiones + hecho horario + foto actual → `gold` (cada 15 min). |
| `dashboard/app.py` | **Router** del dashboard (`st.navigation`) + estilos + barra lateral. |
| `dashboard/ui.py` | Estilos de marca (CSS), encabezados, tablas y sidebar con íconos. |
| `dashboard/db.py` | Conexión al warehouse, cacheada (60s). |
| `dashboard/views/inicio.py` | Inicio: arquitectura + KPIs en vivo (totales de todas las ciudades). |
| `dashboard/views/gold.py` | Vistas de negocio: mapa, dona, patrón por hora, críticas, comparación. |
| `dashboard/.streamlit/config.toml` | Tema visual del dashboard (colores, fuente). |
| `docs/presentacion_G04_CityBikes.{html,pdf}` | La presentación (6 diapositivas). |
| `docs/GUIA_G04_CityBikes.md` | **Esta guía** (cómo funciona el proyecto + cómo levantarlo). |
| `docs/DISENO_G04_CityBikes.md` | Documento de diseño del proyecto. |

---

## 13. Checklist para levantar y probar

- [ ] **Docker Desktop abierto** y el stack **levantado** (`docker compose up`).
- [ ] El **dashboard** abre en http://localhost:8501 (probá las páginas **Inicio** y **Gold**).
- [ ] **Airflow** abre en http://localhost:8080 (los 3 DAGs activos y corriendo en verde).
- [ ] Para ver las tablas crudas: conectá **DBeaver** al warehouse (`localhost:5433` — ver sección 9).
