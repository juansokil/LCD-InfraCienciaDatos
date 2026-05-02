# Stack de Ingenieria de Datos (UN-SAM)

Stack completo de Data Engineering con un solo `docker compose up`. Ingesta datos desde APIs, los procesa en capas (Bronze / Silver / Gold) y los visualiza en dashboards de BI.

## Arquitectura

```
CoinGecko API
      |  (cada 5 min)
      v
  [ Airflow ]  ----->  [ PostgreSQL - data_warehouse ]  ----->  [ Streamlit ]
  orquestador          bronze / silver / gold                    dashboard BI
  puerto 8080          puerto 5432                               puerto 8501
```

## Componentes

| Servicio | Container | Descripcion |
|----------|-----------|-------------|
| **Airflow 3.1.5** | `airflow_standalone` | Orquestador de pipelines (LocalExecutor, Python 3.11) |
| **Airflow Metadata DB** | `airflow_db` | PostgreSQL 17 Alpine para metadatos internos de Airflow (no expuesto al host) |
| **Data Warehouse** | `data_warehouse` | PostgreSQL 17 Alpine con arquitectura Medallon (Bronze / Silver / Gold). Expuesto en `localhost:5432` |
| **Streamlit** | `dashboard` | Dashboard BI automatico (lee de gold schema, sin configuracion manual) |

Todos los servicios se comunican a traves de la red `de_stack_network` (bridge).

## Pipeline de Datos (Crypto)

El pipeline principal ingesta datos de criptomonedas desde la API de CoinGecko y los procesa en 3 capas:

| Capa | DAG | Tablas | Que hace |
|------|-----|--------|----------|
| **Bronze** | `crypto_bronze` | `bronze.crypto_markets`, `bronze.global_market` | Ingesta cruda cada 5 min (top 50 cryptos + mercado global) |
| **Silver** | `crypto_silver` | `silver.crypto_markets`, `silver.quarantine_crypto_markets` | Limpieza, dedup, validacion, columnas derivadas (spread, ATH distance, supply ratio) |
| **Gold** | `crypto_gold` | `gold.dim_crypto`, `gold.dim_tiempo`, `gold.fact_crypto_markets`, `gold.fact_global_market`, `gold.gold_abt_crypto` | Star schema + ABT para analytics/ML |

Tambien existe `crypto_pipeline_completo` que ejecuta Bronze -> Silver -> Gold en un solo DAG.

## DAGs incluidos

```
dags/
├── 00-playground/              # DAGs de aprendizaje (TaskFlow API, branching, ingesta multi-formato)
├── 01-bronze/                  # Ingesta: CSV/JSON/APIs -> bronze
├── 02-silver/                  # Refinamiento: limpieza, validacion, cuarentena
└── 03-gold/                    # Analitica: star schema, ABT, pipeline completo
```

## Base de Datos y Schemas

Al levantar el stack, se crea automaticamente:

- **Base de datos** `InfraCienciaDatos`: creada por la variable `POSTGRES_DB` en el docker-compose
- **Schemas**: creados por `init.sql` (montado en `/docker-entrypoint-initdb.d/`)

| Schema | Proposito |
|--------|-----------|
| `InfraCienciaDatos` | Simulacion de sistema origen |
| `bronze` | Datos crudos tal cual llegan |
| `silver` | Datos limpiados, normalizados y validados |
| `gold` | Star schema, KPIs, ABT para analytics y ML |

## Como Empezar

```bash
docker compose up --build
```

> La primera vez tarda unos minutos mientras construye la imagen y migra la base de datos.

## Accesos

| Servicio | URL / Host | Usuario | Password |
|----------|------------|---------|----------|
| Airflow UI | http://localhost:8080 | (sin login) | (sin login) |
| Data Warehouse (PostgreSQL) | localhost:5432 | admin | admin |
| Dashboard (Streamlit) | http://localhost:8501 | (sin login) | (sin login) |

El dashboard de Streamlit se conecta automaticamente al schema `gold` y muestra los datos sin configuracion manual.

## Conectarse con DBeaver

[DBeaver](https://dbeaver.io/download/) es un cliente SQL gratuito que permite explorar la base de datos visualmente, ejecutar queries, ver tablas y schemas. Es la herramienta recomendada para inspeccionar los datos de Bronze, Silver y Gold mientras desarrollas DAGs.

### Pasos

1. **Database** -> **New Database Connection** -> **PostgreSQL**

2. Completar los campos con estos valores:

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `InfraCienciaDatos` |
| Username | `admin` |
| Password | `admin` |

3. (Opcional) Click en **Test Connection** para verificar.
   - Si pide bajar el driver de PostgreSQL, aceptar.
4. Click en **Finish**.

### Que vas a ver

Una vez conectado, en el panel izquierdo expandi:

```
InfraCienciaDatos
└── Schemas
    ├── bronze              <-- datos crudos de la API
    ├── silver              <-- datos limpios y validados
    ├── gold                <-- star schema y ABT
    └── public              <-- (vacio por defecto)
```

Para ver las tablas, click derecho sobre el schema -> **View Diagram** o expandi `Tables`.

### Tips

- **Los datos cambian cada 5 minutos** (cuando corre el DAG `crypto_bronze`). Refrescá las queries para ver datos nuevos.
- Si **no ves los schemas bronze/silver/gold**: probablemente todavia no corrio ningun DAG. Andá a Airflow UI (http://localhost:8080) y disparalos manualmente.
- **Atajo de query**: `SELECT * FROM bronze.crypto_markets ORDER BY ingested_at DESC LIMIT 10;` para ver los ultimos snapshots de cripto.
- Si **el host no responde**: verificar que el container este levantado con `docker compose ps`. Solo `data_warehouse` expone el puerto 5432 al host (el `airflow_db` queda en la red interna).

## Estructura del Proyecto

```
stack/
├── credentials/                # Credenciales GCP (opcional)
├── dags/                       # DAGs de Airflow
│   ├── 00-playground/          # DAGs de aprendizaje
│   ├── 01-bronze/              # Capa de ingesta
│   ├── 02-silver/              # Capa de refinamiento
│   └── 03-gold/                # Capa de analitica
├── data/                       # Datos de trabajo
│   ├── landing/                # Archivos de entrada (se procesan y mueven)
│   ├── playground/             # Datos de ejemplo
│   ├── processed/              # Archivos procesados (ds=YYYY-MM-DD)
│   └── quarantine/             # Archivos con errores + .error.json
├── dashboard/                  # Dashboard Streamlit
│   ├── Dockerfile              # Imagen del dashboard
│   ├── app.py                  # Codigo del dashboard (lee de gold.*)
│   └── requirements.txt        # Dependencias (streamlit, plotly, pandas)
├── .env                        # Variables de entorno
├── docker-compose.yml          # Orquestacion de servicios
├── Dockerfile                  # Imagen custom de Airflow
├── Dockerfile.postgres         # Imagen custom de Postgres (bakea init.sql, evita bind mount en Windows)
├── init-airflow.sh             # Script de arranque de Airflow
├── init.sql                    # Creacion de schemas en PostgreSQL (copiado a la imagen via Dockerfile.postgres)
└── requirements.txt            # Dependencias Python
```

## Ciclo de Vida de Archivos

```
1. Depositar archivo en ./data/landing/
                |
2. Airflow lo lee, hashea (SHA256) y carga en PostgreSQL (bronze.*)
                |
        --------+--------
        v                v
   EXITO                ERROR
   ./data/processed/     ./data/quarantine/
   ds=YYYY-MM-DD/        ds=YYYY-MM-DD/
   {hash}__{archivo}     {hash}.ext + {hash}.ext.error.json
```

## Dependencias Principales

| Paquete | Uso |
|---------|-----|
| pandas | Procesamiento de DataFrames |
| polars | DataFrames de alto rendimiento (Rust) |
| duckdb | Analitica SQL en memoria |
| SQLAlchemy + psycopg2 | Conexion a PostgreSQL |
| apache-airflow-providers-postgres | Hooks y operadores para Postgres |

## Configuracion Cloud (Opcional)

Para usar BigQuery / GCS, colocar el archivo JSON de Service Account en `./credentials/google_key.json` y ajustar las variables `GCP_*` en `.env`.

## Notas

- **DAGs**: Se leen de `./dags`. Los cambios se reflejan automaticamente (refresco cada 10s).
- **Data**: Los archivos de entrada van en `./data/landing/`.
- **Red Interna**: Airflow y Streamlit se conectan a PostgreSQL usando el host `data_warehouse` (el nombre del servicio en `docker-compose.yml`).
- **Conexion configurable**: Los DAGs leen el host desde la variable de entorno `SOURCE_DB_HOST` (default `data_warehouse`). Los notebooks de verificacion usan `localhost` porque corren en tu maquina y se conectan al puerto expuesto.
- **Init SQL**: Los esquemas se crean automaticamente via `init.sql`, que se copia adentro de la imagen Postgres mediante `Dockerfile.postgres` (asi evitamos bind mounts problematicos en Windows).
- **Reset completo**: `docker compose down -v && docker compose up --build`
