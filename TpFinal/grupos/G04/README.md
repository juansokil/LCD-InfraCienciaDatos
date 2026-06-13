# TP Final — G04 — CityBikes

Pipeline de datos end-to-end sobre la **API pública de CityBikes**, con arquitectura
**Medallion (Bronze → Silver → Gold)**, orquestado con **Airflow**, almacenado en
**PostgreSQL** y visualizado con **Streamlit**. Todo containerizado: `docker compose up` y el
pipeline arranca solo.

## Integrantes
- Nombre Apellido — @usuario-github
- Nombre Apellido — @usuario-github
- _(completar)_

## API elegida
- **CityBikes** — `https://api.citybik.es/v2`
- Sin autenticación. Rate limit: 300 req/hora. Refresh real: cada 2–5 min.
- Endpoints usados: `GET /v2/networks/{id}?fields=name,location,stations`.
- Redes trackeadas (configurable en `.env`): `ecobici` (Buenos Aires), `bicing` (Barcelona),
  `divvy` (Chicago).

## Pregunta de negocio
**¿Qué estaciones se saturan o se quedan sin bicis, y a qué horas del día?**
El dashboard muestra el estado actual (mapa), el patrón de disponibilidad por hora y la
comparación entre ciudades, e identifica las estaciones más críticas.

## Modelo de datos

**Bronze** — `bronze.citybikes_stations_raw`: una fila por estación × snapshot con el objeto
JSON crudo (`station_payload JSONB`) + identificadores y `ingested_at`. Datos tal como llegan.

**Silver** — `silver.station_status`: aplanado, tipado y validado. Métricas por snapshot:
`free_bikes`, `empty_slots`, `total_slots`, `occupancy_rate`, flags `is_empty`/`is_full`. PK
`(station_id, snapshot_at)`. Incremental por watermark sobre `ingested_at`.

**Gold** — modelo dimensional para consumo:
- `gold.dim_network`, `gold.dim_station`
- `gold.fact_station_hourly` — grano estación × hora (promedios, mín/máx, % tiempo vacía/llena)
- `gold.station_current` — última foto por estación (para el mapa en vivo)

## Decisiones técnicas
- **El eje temporal es nuestro `ingested_at`, no el `timestamp` de la API**: ese campo viene en
  formato inconsistente y no es confiable. Lo guardamos en Bronze como dato crudo igual.
- **Set fijo de redes** (no las ~560 de la API): permite comparar ciudades y mantiene el uso
  muy por debajo del rate limit (3 redes × 12 corridas/h ≈ 36 req/h de 300).
- **Procesamiento incremental + idempotente**: Silver y Gold usan watermark / `ON CONFLICT`, así
  re-correr un DAG no duplica datos.
- **Transformaciones en SQL sobre JSONB**: limpieza y agregación se hacen en Postgres
  (eficiente y declarativo).
- **`empty_slots` puede ser `null`** → se normaliza en Silver.

## DAGs (Airflow 3.1.5, Task SDK)
Los tres con `is_paused_upon_creation=False` y `schedule` definido (arrancan solos).

| DAG | Schedule | Qué hace |
|---|---|---|
| `citybikes_bronze` | `*/5 * * * *` | Ingesta cruda de la API a Bronze |
| `citybikes_silver` | `*/10 * * * *` | Limpieza/tipado Bronze → Silver |
| `citybikes_gold`   | `*/15 * * * *` | Dimensiones + hecho horario + foto actual |

## Cómo levantar el stack

```bash
# 1. Copiar variables de entorno
cp .env.example .env

# 2. Levantar todo
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
    ├── app.py
    ├── db.py
    ├── requirements.txt
    └── pages/1_Gold.py
```

> Fuente de datos: CityBikes API (https://citybik.es) — capa de display de PyBikes.
