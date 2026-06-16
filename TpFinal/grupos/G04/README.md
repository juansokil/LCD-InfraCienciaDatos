# TP Final — G04 — CityBikes

Pipeline de datos end-to-end sobre la **API pública de CityBikes**, con arquitectura
**Medallion (Bronze → Silver → Gold)**, orquestado con **Airflow**, almacenado en
**PostgreSQL** y visualizado con **Streamlit**. Todo containerizado: `docker compose up` y el
pipeline arranca solo.

## Integrantes
- Di Lacio, Lautaro — @DiLacio-Lautaro
- Lust, Tobias — @lust-tobias
- Melograna, Federico — @Melograma-Federico
- Quinteros Amicone, Lautaro — @Quinteros-Lautaro
- Rial, Alejo — @Alejo-Rial
- Romero, Manuel — @romero-rodrigo

## API elegida
- **CityBikes** — `https://api.citybik.es/v2`
- Sin autenticación. **Rate limit: 300 req/hora** — límite oficial documentado (docs.citybik.es/api/), verificable en el header de respuesta `x-ratelimit-limit-hour: 300`. Refresh real: cada 2–5 min.
- Endpoints usados: `GET /v2/networks/{id}?fields=name,location,stations`.
- Redes trackeadas (configurable en `.env`): **Latinoamérica Sur** — ~20 redes de bici pública de
  6 países: Argentina (Buenos Aires, Rosario, Nordelta), Brasil (São Paulo, Río, Curitiba…), Chile
  (Santiago), Colombia (Bogotá, Medellín), Ecuador (Cuenca) y Perú (Lima).

## Pregunta de negocio
**¿Qué estaciones se saturan o se quedan sin bicis, y a qué horas del día?**
El dashboard muestra el estado actual (mapa), el patrón de disponibilidad por hora y la
comparación entre ciudades, e identifica las estaciones más críticas.

## Modelo de datos

**Bronze** — `bronze.citybikes_stations_raw`: una fila por estación × snapshot con el objeto
JSON crudo (`station_payload JSONB`) + identificadores y `ingested_at`. Datos tal como llegan.

**Silver** — `silver.station_status`: aplanado, tipado, validado y filtrado de estaciones inactivas. Métricas por snapshot:
`free_bikes`, `empty_slots`, `total_slots`, `occupancy_rate`, flags `is_empty`/`is_full`. PK
`(station_id, snapshot_at)`. Incremental por watermark sobre `ingested_at`.

**Gold** — modelo dimensional para consumo:
- `gold.dim_network`, `gold.dim_station`
- `gold.fact_station_hourly` — grano estación × hora (promedios, mín/máx, % tiempo vacía/llena)
- `gold.station_current` — última foto por estación (para el mapa en vivo)

## Decisiones técnicas
- **El eje temporal es nuestro `ingested_at`, no el `timestamp` de la API**: ese campo viene en
  formato inconsistente y no es confiable. Lo guardamos en Bronze como dato crudo igual.
- **Set fijo de redes** (no las ~560 de la API): trackeamos las redes de **Sudamérica** para comparar
  ciudades de la región, quedando bajo el rate limit (~22 redes × 12 corridas/h ≈ 264 req/h de 300).
- **Procesamiento incremental + idempotente**: Silver y Gold usan watermark / `ON CONFLICT`, así
  re-correr un DAG no duplica datos.
- **Transformaciones en SQL sobre JSONB**: limpieza y agregación se hacen en Postgres
  (eficiente y declarativo).
- **`empty_slots` puede ser `null`** → se normaliza en Silver.
- **Descartamos estaciones inactivas**: varias redes marcan `extra.renting = 0` o `extra.online = false` cuando una estación no opera. Se filtran en Silver para que las métricas de *sin bicis* / *saturada* reflejen solo estaciones operativas — una estación cerrada no es lo mismo que una que se quedó sin bicis.

## DAGs (Airflow 3.1.5, Task SDK)
Los tres con `is_paused_upon_creation=False` y `schedule` definido (arrancan solos).

| DAG | Schedule | Qué hace |
|---|---|---|
| `citybikes_bronze` | `*/5 * * * *` | Ingesta cruda de la API a Bronze |
| `citybikes_silver` | `*/10 * * * *` | Limpieza/tipado Bronze → Silver |
| `citybikes_gold`   | `*/15 * * * *` | Dimensiones + hecho horario + foto actual |

## Cómo levantar el stack

> **Requisito:** tener **Docker Desktop** abierto y corriendo.

**Opción A — un solo comando (recomendado, no hay nada que olvidarse):**

```bash
# Windows (PowerShell), parado en esta carpeta:
.\run.ps1
# Mac / Linux:
./run.sh
```

El script crea el `.env` solo (si falta) y levanta todo.

**Opción B — manual (3 pasos):**

```bash
cd TpFinal/grupos/G04
cp .env.example .env          # Windows: copy .env.example .env  
docker compose up --build
```

Accesos:
- **Airflow UI** → http://localhost:8080
  Usuario `admin`. La contraseña la genera Airflow standalone:
  `docker compose logs airflow | grep -i password`
- **Dashboard Streamlit** → http://localhost:8501
- **Warehouse Postgres** → `localhost:5433` (db `citybikes`)

> ⚠️ Si tenés el stack del curso levantado en paralelo puede haber conflicto de puertos
> (8080 / 8501). Apagá uno o cambiá los mapeos en `docker-compose.yml`.

Una vez arriba, los datos empiezan a aparecer en minutos: Bronze a los ~5 min, Silver a los
~10 min, Gold a los ~15 min. El dashboard se va poblando a medida que Gold tiene datos.

### Si algo falla

- **`Database is uninitialized ... must specify POSTGRES_PASSWORD`** → falta el archivo `.env`.
  Corré `cp .env.example .env` (o usá `run.ps1` / `run.sh`) y volvé a levantar.
- **Puertos ocupados (`8080` / `8501` / `5433`)** →  stack del curso levantado en paralelo.
  Apagalo, o cambiá los mapeos de puertos en `docker-compose.yml`.
- **PowerShell bloquea `run.ps1`** (`running scripts is disabled`) →
  `powershell -ExecutionPolicy Bypass -File .\run.ps1`, o usá la Opción B manual.
- **Empezar de cero** (borrar los datos y re-crear la DB con `init.sql`) →
  `docker compose down -v` y después `docker compose up`.

## Estructura
```
TpFinal/grupos/G04/
├── docker-compose.yml      # warehouse + airflow_db + airflow + dashboard
├── Dockerfile              # Airflow 3.1.5 + deps
├── init.sql                # schemas + tablas bronze/silver/gold
├── requirements.txt        # deps de Airflow
├── .env.example
├── dags/
│   ├── citybikes_common.py # conexión + config compartida
│   ├── 01-bronze/citybikes_bronze.py
│   ├── 02-silver/citybikes_silver.py
│   └── 03-gold/citybikes_gold.py
└── dashboard/
    ├── Dockerfile
    ├── app.py              # router (st.navigation) + estilos + barra lateral
    ├── ui.py               # estilos de marca (CSS) + header/panel + sidebar
    ├── db.py               # conexión + queries cacheadas
    ├── requirements.txt
    └── views/
        ├── inicio.py       # vista de inicio (arquitectura + pipeline en números)
        └── gold.py         # vista Gold (KPIs, mapa, patrón, críticas, comparación)
```

> Fuente de datos: CityBikes API (https://citybik.es) — capa de display de PyBikes.
