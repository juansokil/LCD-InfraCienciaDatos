# Diseño TP Final — G04 — CityBikes

Pipeline de datos end-to-end con arquitectura **Medallion (Bronze → Silver → Gold)**,
orquestado con **Airflow**, almacenado en **PostgreSQL** y visualizado con **Streamlit**,
todo containerizado con **Docker Compose**.

- **API:** CityBikes — `https://api.citybik.es/v2`
- **Auth:** sin auth. **Rate limit:** 300 req/hora.
- **Refresh real:** cada 2–5 min (datos de disponibilidad de bicicletas en tiempo casi real).

---

## 0. La API en 1 minuto

Dos endpoints:

| Endpoint | Devuelve |
|---|---|
| `GET /v2/networks` | Lista de ~560 redes (sistemas de bici pública) del mundo: `id`, `name`, `company`, `location{city,country,latitude,longitude}` |
| `GET /v2/networks/{id}` | Una red con su array `stations[]`. Filtrable con `?fields=stations` para bajar el payload. |

Estructura de cada **station**:

```json
{
  "id": "000db9b6e3849926d4868caf7096780d",
  "name": "Calumet Ave & 21st St",
  "latitude": 41.854184,
  "longitude": -87.619153,
  "timestamp": "2025-04-17T16:41:02505032+00:00Z",   // OJO: formato inconsistente
  "free_bikes": 13,
  "empty_slots": 1,                                    // puede venir null
  "extra": {
    "uid": "...",
    "slots": 14,
    "has_ebikes": true,
    "ebikes": 1,
    "renting": 1,
    "returning": 1
  }
}
```

### Decisiones que nacen de la API
1. **Trackear un set fijo de redes**, no las 560. Lo definimos por `.env` (`CITYBIKES_NETWORKS`).
   Recomendado: 2–4 redes para poder comparar ciudades/zonas en el dashboard.
   Ej: `ecobici` (Buenos Aires), `bicing` (Barcelona), `divvy` (Chicago).
2. **Eje temporal = nuestro `ingested_at`**, no el `timestamp` de la API (ese campo viene
   con microsegundos sin punto y `Z` después del offset → no parsea limpio). El `timestamp`
   de la API se guarda igual en Bronze como dato crudo, pero no se usa como reloj.
3. **`empty_slots` puede ser `null`** → se normaliza en Silver.
4. **Presupuesto de requests:** con 3 redes y schedule `*/5` = 3 req × 12 corridas/h = **36 req/h**
   (de 300). Holgado.

---

## 1. Arquitectura

```
                 ┌──────────────────────────────┐
   cada 5 min →  │  DAG bronze_citybikes        │  GET /v2/networks/{id}?fields=stations
                 └──────────────┬───────────────┘
                                ▼
                 bronze.citybikes_stations_raw   (JSON crudo + auditoría)
                                │
                 cada 10 min →  │  DAG silver_citybikes  (limpieza + tipado + métricas)
                                ▼
                 silver.station_status            (1 fila por estación × snapshot, limpia)
                                │
                 cada hora →    │  DAG gold_citybikes    (modelo dimensional + agregados)
                                ▼
                 gold.dim_station · gold.dim_network · gold.fact_station_hourly
                                │
                                ▼
                       Streamlit  (consume SOLO Gold)
```

### Stack (4 servicios en `docker-compose.yml`)
| Servicio | Imagen base | Rol |
|---|---|---|
| `warehouse` | `postgres:17-alpine` | DB de datos (schemas bronze/silver/gold). Monta `init.sql`. |
| `airflow_db` | `postgres:17-alpine` | Metadata de Airflow (separada del warehouse). |
| `airflow` | `apache/airflow:3.1.5` (custom) | Scheduler + webserver + DAGs. |
| `dashboard` | `python:3.11-slim` | Streamlit sobre Gold. |

> Cuidado con puertos 5432/8080/8501 si tenés el stack del curso levantado en paralelo.

---

## 2. Modelo de datos (DDL completo)

### `init.sql` — se monta en el warehouse y crea los schemas solos
```sql
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
```

### BRONZE — datos crudos tal como llegan
```sql
CREATE TABLE IF NOT EXISTS bronze.citybikes_stations_raw (
    ingestion_id    BIGSERIAL   PRIMARY KEY,
    network_id      TEXT        NOT NULL,
    network_name    TEXT,
    city            TEXT,
    country         TEXT,
    station_id      TEXT        NOT NULL,
    station_payload JSONB       NOT NULL,            -- objeto "station" crudo completo
    source          TEXT        NOT NULL DEFAULT 'api.citybik.es/v2',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bronze_ingested_at
    ON bronze.citybikes_stations_raw (ingested_at);
CREATE INDEX IF NOT EXISTS ix_bronze_network
    ON bronze.citybikes_stations_raw (network_id);
```
**Principio Bronze:** se extrae solo lo mínimo para particionar/unir (`network_id`, `station_id`,
`ingested_at`); todo lo demás queda en `station_payload` (JSONB). Si mañana querés un campo
nuevo, ya lo tenés guardado sin re-ingestar.

### SILVER — limpio, tipado y validado
```sql
CREATE TABLE IF NOT EXISTS silver.station_status (
    network_id     TEXT        NOT NULL,
    network_name   TEXT,
    city           TEXT,
    country        TEXT,
    station_id     TEXT        NOT NULL,
    station_name   TEXT,
    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION,
    free_bikes     INTEGER,
    empty_slots    INTEGER,
    total_slots    INTEGER,                  -- free_bikes + empty_slots (o extra.slots)
    ebikes         INTEGER,
    has_ebikes     BOOLEAN,
    occupancy_rate NUMERIC(5,4),             -- free_bikes / NULLIF(total_slots,0)
    is_empty       BOOLEAN,                  -- free_bikes = 0
    is_full        BOOLEAN,                  -- empty_slots = 0
    snapshot_at    TIMESTAMPTZ NOT NULL,     -- = ingested_at del bronze (reloj confiable)
    PRIMARY KEY (station_id, snapshot_at)
);

CREATE INDEX IF NOT EXISTS ix_silver_network_time
    ON silver.station_status (network_id, snapshot_at);
```
**Limpieza en Silver:**
- Descartar filas inválidas (`free_bikes < 0`, lat/long fuera de rango, sin `station_id`).
- `empty_slots` null → `COALESCE(..., 0)` (o dejar null + flag, según prefieran).
- `total_slots = free_bikes + empty_slots` (fallback a `extra.slots` si está).
- `occupancy_rate` redondeada; cuidado con división por cero (`NULLIF`).
- Tipar `latitude/longitude` a número, `has_ebikes` a boolean.

### GOLD — modelo dimensional para el dashboard
```sql
-- Dimensión estación (última foto conocida de cada estación)
CREATE TABLE IF NOT EXISTS gold.dim_station (
    station_id   TEXT PRIMARY KEY,
    network_id   TEXT NOT NULL,
    station_name TEXT,
    city         TEXT,
    country      TEXT,
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    total_slots  INTEGER,
    first_seen   TIMESTAMPTZ,
    last_seen    TIMESTAMPTZ
);

-- Dimensión red / ciudad
CREATE TABLE IF NOT EXISTS gold.dim_network (
    network_id TEXT PRIMARY KEY,
    name       TEXT,
    city       TEXT,
    country    TEXT
);

-- HECHO: estado agregado por estación y hora
CREATE TABLE IF NOT EXISTS gold.fact_station_hourly (
    station_id      TEXT        NOT NULL,
    network_id      TEXT        NOT NULL,
    hour_bucket     TIMESTAMPTZ NOT NULL,   -- date_trunc('hour', snapshot_at)
    snapshots       INTEGER,                -- cuántas mediciones en esa hora
    avg_free_bikes  NUMERIC(8,2),
    min_free_bikes  INTEGER,
    max_free_bikes  INTEGER,
    avg_empty_slots NUMERIC(8,2),
    avg_occupancy   NUMERIC(5,4),
    pct_time_empty  NUMERIC(5,4),           -- % snapshots con free_bikes = 0
    pct_time_full   NUMERIC(5,4),           -- % snapshots con empty_slots = 0
    PRIMARY KEY (station_id, hour_bucket)
);

CREATE INDEX IF NOT EXISTS ix_gold_hour
    ON gold.fact_station_hourly (hour_bucket);
```

> El DDL de bronze/silver/gold puede vivir en `init.sql` (creación de schemas) + creación de
> tablas dentro de cada DAG con `CREATE TABLE IF NOT EXISTS` (más robusto: el DAG garantiza
> que su tabla existe antes de escribir).

---

## 3. Diseño de los DAGs

Los 3 con `is_paused_upon_creation=False` y `schedule` definido (nunca `None`).

### `bronze_citybikes` — `schedule="*/5 * * * *"`
```
para cada network_id en CITYBIKES_NETWORKS (env):
    GET https://api.citybik.es/v2/networks/{network_id}?fields=stations,location,name
    para cada station en stations:
        insert en bronze.citybikes_stations_raw (
            network_id, network_name, city, country,
            station_id, station_payload=<json station>, ingested_at=now()
        )
```
- Insert puro (append). Bronze es inmutable: cada corrida agrega un snapshot nuevo.
- Manejo de errores: si una red falla, loguear y seguir con las demás (no romper el DAG entero).
- Respetar rate limit: `time.sleep` corto entre redes si agregás muchas.

### `silver_citybikes` — `schedule="*/10 * * * *"`
```
watermark = SELECT max(snapshot_at) FROM silver.station_status   (o '-infinity' si vacío)
rows = SELECT * FROM bronze.citybikes_stations_raw WHERE ingested_at > watermark
para cada row:
    parsear station_payload (JSONB → campos)
    validar (descartar inválidos)
    calcular total_slots, occupancy_rate, is_empty, is_full
    snapshot_at = row.ingested_at
UPSERT en silver.station_status ON CONFLICT (station_id, snapshot_at) DO NOTHING
```
- Incremental por watermark → no reprocesa todo cada vez.
- Idempotente: re-correr no duplica.

### `gold_citybikes` — `schedule="@hourly"`
```
-- dimensiones (upsert siempre con la última info)
UPSERT gold.dim_network  desde silver (distinct network)
UPSERT gold.dim_station  desde silver (última foto por station + first/last seen)

-- hecho: recomputar las últimas ~3 horas (por si llegaron datos tarde)
DELETE FROM gold.fact_station_hourly WHERE hour_bucket >= now() - interval '3 hours'
INSERT INTO gold.fact_station_hourly
SELECT
    station_id, network_id,
    date_trunc('hour', snapshot_at) AS hour_bucket,
    count(*)                        AS snapshots,
    avg(free_bikes), min(free_bikes), max(free_bikes),
    avg(empty_slots),
    avg(occupancy_rate),
    avg((free_bikes = 0)::int),     AS pct_time_empty,
    avg((empty_slots = 0)::int)     AS pct_time_full
FROM silver.station_status
WHERE snapshot_at >= now() - interval '3 hours'
GROUP BY station_id, network_id, date_trunc('hour', snapshot_at);
```

### (Opcional, más prolijo) Encadenar con Datasets
En vez de schedules sueltos, podés usar *data-aware scheduling*: bronze produce un Dataset,
silver se dispara cuando ese Dataset se actualiza, y gold cuando se actualiza el de silver.
Para el TP, schedules independientes alcanzan y cumplen la consigna.

---

## 4. Estructura de carpetas (`TpFinal/grupos/G04/`)

```
TpFinal/grupos/G04/
├── README.md                  # API + modelo de datos + cómo levantar + decisiones
├── docker-compose.yml         # warehouse + airflow_db + airflow + dashboard
├── Dockerfile                 # Airflow custom (FROM apache/airflow:3.1.5)
├── init.sql                   # CREATE SCHEMA bronze/silver/gold
├── requirements.txt           # pandas, sqlalchemy, requests, psycopg2-binary
├── .env.example               # CITYBIKES_NETWORKS, credenciales Postgres, etc.
├── .gitignore                 # .env, __pycache__, credentials/
├── dags/
│   ├── 01-bronze/
│   │   └── citybikes_bronze.py
│   ├── 02-silver/
│   │   └── citybikes_silver.py
│   └── 03-gold/
│       └── citybikes_gold.py
└── dashboard/
    ├── Dockerfile             # FROM python:3.11-slim
    ├── app.py                 # intro + st.set_page_config
    ├── db.py                  # conexión Postgres reutilizable
    ├── requirements.txt       # streamlit, pandas, sqlalchemy, plotly
    └── pages/
        └── 1_Gold.py          # KPIs y vistas sobre Gold
```

### `.env.example` (propuesta)
```
# Warehouse (datos)
WAREHOUSE_DB=citybikes
WAREHOUSE_USER=cb_user
WAREHOUSE_PASSWORD=cb_pass
WAREHOUSE_HOST=warehouse
WAREHOUSE_PORT=5432

# Redes a trackear (coma-separadas, ids de /v2/networks)
CITYBIKES_NETWORKS=ecobici,bicing,divvy
```

---

## 5. Dashboard (Streamlit, solo Gold)

`pages/1_Gold.py` — ideas de vistas que responden la pregunta de negocio:

1. **KPIs arriba:** total estaciones, % estaciones vacías ahora, % llenas ahora, bicis disponibles totales.
2. **Mapa de disponibilidad** (`st.map` o `plotly.scatter_mapbox`): última foto, color = occupancy_rate.
3. **Heatmap hora-del-día × estación** de `pct_time_empty` → dónde y cuándo se quedan sin bicis.
4. **Ranking** de estaciones más saturadas (más `pct_time_full`) y más vacías (`pct_time_empty`).
5. **Comparación entre ciudades/redes:** occupancy promedio por `network_id` a lo largo del día.

Todo se lee de `gold.fact_station_hourly` + `gold.dim_station` / `dim_network`. Nada de Bronze/Silver en el dashboard.

---

## 6. Pregunta de negocio (para el body del PR)

> **¿Qué estaciones se saturan o se quedan sin bicis, y a qué horas del día?**
> El dashboard muestra el patrón de disponibilidad por hora y por zona/ciudad, identificando
> estaciones críticas (mucho tiempo vacías o llenas) — útil para rebalanceo operativo.

---

## 7. Checklist de la consigna (que no falte nada)

- [ ] `docker compose up` levanta todo solo, sin tocar nada a mano.
- [ ] Schemas bronze/silver/gold creados por `init.sql` (no manuales).
- [ ] 3 DAGs (uno por capa), todos con `schedule` definido y `is_paused_upon_creation=False`.
- [ ] Schedule de Bronze acorde al refresh de la API (`*/5`).
- [ ] Dashboard consume **solo** tablas Gold.
- [ ] README con API, modelo de datos, cómo levantar y decisiones técnicas.
- [ ] Branch `tp-final/G04` + carpeta `TpFinal/grupos/G04/` + PR `TP Final - G04 - CityBikes`.
- [ ] Entrega = PR en "Ready for review" antes del 17-06-26 23:59.

---

## 8. Orden sugerido para programar

1. `docker-compose.yml` + `init.sql` + `Dockerfile` → que levante el stack vacío.
2. `bronze_citybikes.py` → ver datos cayendo en `bronze.citybikes_stations_raw`.
3. `silver_citybikes.py` → validar `silver.station_status`.
4. `gold_citybikes.py` → poblar dim/fact.
5. `dashboard/` → conectar y graficar Gold.
6. README final + PR Ready for review + ensayar la demo (5–6 min).
```
