# TP Final - G11 - USGS Earthquakes (sismos)

Pipeline end-to-end sobre la API de sismos del USGS, con arquitectura medallion
(Bronze → Silver → Gold), orquestado con **Airflow 3.1.5**, guardado en
**PostgreSQL** y con un dashboard **Streamlit** sobre Gold. Con
`docker compose up` el stack levanta y empieza a generar datos solo.

---

## Integrantes

- Agustín Simonenco (@AgustinSimonenco)
- Juan Ignacio Simonenco (@simonenconacho)
- Chiara Saggion (@saggionchiara0108-dotcom)
- Fabrizio Parente (@zfabro)

## API elegida

- **Nombre**: USGS Earthquake Hazards Program — feeds GeoJSON
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- **Descripción**: todos los sismos (y otros eventos sísmicos: voladuras de
  cantera, explosiones, sismos glaciares) detectados en el mundo, con
  magnitud, profundidad, coordenadas, lugar, estado de revisión y alerta de
  tsunami. Usamos `all_month` (últimos 30 días) y `all_day` (últimas 24 h).
- **Auth**: sin auth
- **API key**: no necesita
- **Refresh**: tiempo real (el feed se regenera cada minuto); nuestro pipeline
  lo baja **cada 30 minutos**

## Pregunta de negocio

> **¿Dónde se concentra la actividad sísmica, cómo evoluciona día a día y qué
> tan fuertes y profundos son los sismos? Con foco en Sudamérica.**

## Arquitectura

```
                 cron */30 (y al levantar)        asset                asset
 API USGS ──► usgs_bronze ──────────────► usgs_silver ──────────► usgs_gold ──► dashboard
 (GeoJSON)    data/raw + bronze.*   BRONZE_SISMOS   silver.*  SILVER_SISMOS  gold.*   (Streamlit,
                                                                                      solo gold.v_*)
```

- **Un solo reloj, en el borde**: Bronze tiene cron cada 30 minutos (la API no
  avisa cuándo hay sismos nuevos). Silver y Gold **no tienen cron**: se
  disparan por **Assets de Airflow 3** (`@task(outlets=[ASSET])` en el
  productor, `schedule=[ASSET]` en el consumidor; ver `dags/common/assets.py`).
  Si Silver falla, Gold no corre sobre datos viejos.
- **Arranque solo**: los schemas los crea `init.sql`; los DAGs nacen activos
  (`is_paused_upon_creation=False`) y Bronze usa
  `CronTriggerTimetable(..., run_immediately=True)`, que dispara la primera
  corrida apenas Airflow registra el DAG, sin esperar al próximo "y media".
- **Transformaciones en SQL**: Silver y Gold son SQL que corre dentro de
  Postgres. Python solo baja la API y manda las sentencias.

## Modelo de datos

### Bronze — `bronze.usgs_sismos`

El crudo, tal cual lo entrega la API, en **append**:

- El payload completo se guarda en `data/raw/usgs/ds=AAAA-MM-DD/HHMMSS_<feed>.geojson`
  (permite reprocesar sin volver a llamar a la API).
- La tabla aplana cada `Feature` del GeoJSON: `event_id`, `mag`, `place`,
  `time_ms` y `updated_ms` (epoch en ms, como vienen), `status`, `tsunami`,
  `sig`, `net`, `mag_type`, `event_type`, `longitude`, `latitude`, `depth`, etc.
- Auditoría por fila: `feed`, `feed_generated_ms`, `archivo_raw`, `ingested_at`.
- **Primera corrida = `all_month`** (si la tabla está vacía): el dashboard
  arranca con 30 días de historia. Después, `all_day` cada 30 minutos. Las 24 h
  se solapan a propósito: así llegan las correcciones de USGS.

### Silver — `silver.sismos`, `silver.sismos_cuarentena`, `silver.calidad_corridas`

- **Última versión de cada evento**: USGS corrige los sismos después de
  publicarlos (magnitud, `automatic` → `reviewed`), así que en Bronze un mismo
  sismo aparece muchas veces. Silver se queda con la de `updated_ms` más
  reciente (`DISTINCT ON (event_id) ... ORDER BY updated_ms DESC`).
- **Idempotente**: carga con `INSERT ... ON CONFLICT (event_id) DO UPDATE`
  solo si la versión que llega es más nueva. Correrlo N veces da lo mismo.
- **Tipado y limpieza**: epoch ms → `timestamptz`, textos normalizados,
  `tsunami` → booleano.
- **Enriquecimiento**: `region` a partir del texto de `place`
  (`"19 km ESE of Joseph, Oregon"` → `Oregon`; `CA` → `California`) y
  `macrozona` por coordenadas (Sudamérica, Norteamérica, Asia, ...).
- **Cuarentena con motivo**: sin fecha o en el futuro, sin coordenadas o fuera
  de rango, profundidad fuera de −10 a 800 km, magnitud nula o fuera de −2 a 10.
  Las voladuras de cantera o explosiones **no** son errores: quedan en Silver
  con `es_sismo = false`.
- `silver.calidad_corridas`: una fila por corrida (filas leídas, insertados,
  corregidos por USGS, en cuarentena).
- Todo en **una transacción**: nunca queda Silver a medio escribir.

### Gold — modelo estrella

```
                       dim_tiempo
                           │ fecha_key
 dim_region ── region_key ─┤
                     ┌─────┴──────┐
                     │ fact_sismo │  1 fila = 1 evento
                     └─────┬──────┘
 dim_tipo_evento ──────────┤
                           ├── magnitud_key ──── dim_magnitud    (rangos)
                           └── profundidad_key ─ dim_profundidad (rangos)
```

| Tabla | Grano / contenido |
|---|---|
| `fact_sismo` | un evento: magnitud, profundidad, lat/lon, significancia, tsunami, alerta, estado + 5 claves (con PK y FKs declaradas) |
| `dim_tiempo` | un día (sin huecos): año, mes, día de la semana, semana ISO, fin de semana |
| `dim_region` | región, país (los estados de EE.UU. → "Estados Unidos") y macrozona |
| `dim_magnitud` | rangos descriptivos: Micro, Menor, Ligero, Moderado, Fuerte, Mayor, Gran sismo |
| `dim_profundidad` | Superficial (0–70 km), Intermedio (70–300), Profundo (> 300) |
| `dim_tipo_evento` | sismo, voladura de cantera, explosión, sismo glaciar, ... |

Se reconstruye entero en cada corrida, en una transacción (el DDL de Postgres
es transaccional: el dashboard nunca ve el modelo a medio construir). Antes de
publicar el asset se controla que la fact cuadre con Silver y que no haya
claves huérfanas.

**Capa semántica** (lo único que lee el dashboard): `gold.v_sismos`,
`v_kpis`, `v_sismo_mas_fuerte`, `v_sismos_diarios`, `v_actividad_por_region`,
`v_actividad_por_macrozona`, `v_magnitud_profundidad`, `v_sudamerica_por_pais`,
`v_eventos_por_tipo`.

### Dashboard (http://localhost:8501)

- **Inicio**: KPIs, el sismo más fuerte del período, sismos por día.
- **Mapa**: dónde tiembla, con filtros de magnitud, macrozona y período.
- **Regiones y magnitudes**: ranking de regiones, macrozonas, distribución de
  magnitudes (Gutenberg-Richter), cruce magnitud × profundidad, tipos de evento.
- **Sudamérica**: mapa por profundidad, países, y la subducción de la placa de
  Nazca vista en los datos.

## Cómo levantar el stack

> Requisito: Docker Desktop abierto. La API no necesita key.

```bash
cd TpFinal/grupos/G11/
docker compose up -d --build   # el .env ya viene en el repo
```

En ~2 minutos Airflow registra los DAGs, Bronze baja el último mes de sismos y
se encadenan Silver y Gold. No hay que activar nada a mano.

**Accesos**:

- Airflow UI: http://localhost:8080 — usuario **`admin`**, contraseña **`admin`**
- Dashboard (Gold): http://localhost:8501
- Postgres (warehouse): `localhost:5432`, base `sismos`, usuario `admin` / `admin`

Si algún puerto está ocupado (por ejemplo, el stack del curso levantado),
cambialo en el `.env` (`AIRFLOW_PORT`, `DASHBOARD_PORT`, `WAREHOUSE_PORT`).

**Apagar**:

```bash
docker compose down            # apaga, conserva los datos
docker compose down -v         # apaga y BORRA los volúmenes (vuelve a cero)
```

## Estructura

```
TpFinal/grupos/G11/
├── README.md
├── docker-compose.yml       # warehouse + airflow_db + airflow + dashboard
├── Dockerfile               # Airflow 3.1.5 + requirements
├── Dockerfile.postgres      # Postgres con init.sql adentro
├── init.sql                 # CREATE SCHEMA bronze / silver / gold
├── init-airflow.sh          # migra la base, fija admin/admin y arranca Airflow
├── requirements.txt
├── .env                     # credenciales de juguete (va al repo a propósito)
├── dags/
│   ├── common/              # assets.py (encadenado) + db.py (conexión)
│   ├── 01-bronze/usgs_bronze.py
│   ├── 02-silver/usgs_silver.py
│   └── 03-gold/usgs_gold.py
├── data/raw/                # crudo de la API (no se versiona)
└── dashboard/               # Streamlit: app.py (menú) + inicio.py + vistas/ + db.py + theme.py
```
