# TP Final - Grupo 09

## Integrantes
- Lisandro Farina (@lisandrofarina06)
- Lucas Feller (@lucasfeller)
- Juan Pablo Varini (@JuanPablo0620)
- Matias Bardelli (@stx-06)

## API Elegida
- **Nombre**: Open-Meteo (Historical Weather API)
- **URL**: https://open-meteo.com/en/docs/historical-weather-api
- **Descripción**: datos meteorológicos diarios históricos (temperatura, lluvia, viento, etc.) por coordenadas, con el modelo de reanálisis ERA5.
- **Auth**: sin auth
- **API key**: no necesita
- **Refresh**: la API se actualiza cada hora; Bronze usa la API histórica (ERA5, ~5 días de retraso) y corre una vez al levantar el stack.

## Objetivo

Analizar cómo varían las condiciones climáticas entre distintas regiones de la provincia de Buenos Aires.

Localidades seleccionadas:

- Mar del Plata — Costa.
- Tandil — Interior.
- Bahía Blanca — Sur.

## Arquitectura

El TP tiene su propia infraestructura, definida en el `docker-compose.yml` de esta carpeta. No depende del stack de la materia.

| Servicio | Imagen | Para qué |
|---|---|---|
| `data_warehouse` | `postgres:17-alpine` | Base de datos con los schemas `bronze`, `silver` y `gold` |
| `airflow_db` | `postgres:17-alpine` | Metadatos internos de Airflow |
| `airflow` | `apache/airflow:3.1.5` | Orquestación de los DAGs |
| `dashboard` | Streamlit (`dashboard/Dockerfile`) | Visualización sobre la capa Gold |

Flujo del pipeline:

```text
Open-Meteo (API histórica, ERA5)
   │
   ▼
g09_bronze_open_meteo  ── corre solo al levantar el stack (@once)
   │  emite el asset g09_bronze_open_meteo_raw
   ▼
g09_silver_open_meteo  ── crea silver.clima_diario_clean (SQL)
   │  emite el asset g09_silver_open_meteo_clean
   ▼
g09_gold_open_meteo  ── crea el modelo estrella en gold (SQL)
   │  emite el asset g09_gold_open_meteo_star
   ▼
Dashboard (Streamlit, lee solo Gold)
```

- Los schemas se crean solos al iniciar la base (`init/01_schemas.sql`).
- Los DAGs arrancan activos: no hace falta despausarlos a mano.
- Cada capa dispara a la siguiente mediante assets de Airflow.

## Modelo de datos

### Bronze — `bronze.open_meteo_raw`

Una fila por localidad e ingesta, con la respuesta original de la API en JSONB (`response_payload`) y los parámetros del pedido. No se transforma nada: es la copia fiel de la fuente. Detalle en `docs/ARQUITECTURA_BRONZE.md`.

### Silver — `silver.clima_diario_clean`

**Grano:** una fila por ciudad y día (≈ 4.330 días por ciudad; varía según la fecha de ejecución).

Se construye en SQL a partir de Bronze: toma la ingesta más reciente de cada ciudad (`DISTINCT ON`), recorre los arrays diarios del JSON con `generate_series` y descarta los días sin dato de temperatura.

| Columna | Tipo | Descripción |
|---|---|---|
| `ciudad` | texto | Mar del Plata, Tandil o Bahía Blanca |
| `region` | texto | Costa, Interior o Sur |
| `fecha` | date | Día de la medición |
| `temp_media_c` | numeric | Temperatura media diaria (°C) |
| `temp_max_c` | numeric | Temperatura máxima diaria (°C) |
| `temp_min_c` | numeric | Temperatura mínima diaria (°C) |
| `lluvia_mm` | numeric | Precipitación acumulada del día (mm) |
| `viento_kmh` | numeric | Velocidad media del viento (km/h) |

### Gold — modelo estrella

**Pregunta que responde el dashboard:** ¿cómo varían la temperatura, la lluvia y el viento entre la costa (Mar del Plata), el interior (Tandil) y el sur (Bahía Blanca), y con qué frecuencia hay días de calor extremo y heladas?

```text
                 dim_tiempo
                 (tiempo_id)
                      │
dim_ciudad ──── fact_clima_diario
(ciudad_id)
```

**`gold.fact_clima_diario`** — tabla de hechos. **Grano:** una fila por ciudad y día (≈ 4.330 días por ciudad; varía según la fecha de ejecución).

| Columna | Descripción |
|---|---|
| `tiempo_id` | Fecha; une con `dim_tiempo` |
| `ciudad_id` | Une con `dim_ciudad` |
| `temp_media_c`, `temp_max_c`, `temp_min_c` | Temperaturas del día (°C) |
| `lluvia_mm` | Precipitación del día (mm) |
| `viento_kmh` | Viento medio del día (km/h) |

**`gold.dim_ciudad`** — una fila por ciudad (3 filas): `ciudad_id`, `ciudad`, `region`.

**`gold.dim_tiempo`** — una fila por día (≈ 4.330 filas): `tiempo_id` (la fecha), `anio`, `mes`, `dia`, `nombre_mes`.
## Estructura

```text
G09/
├── README.md
├── docker-compose.yml        # servicios del TP
├── .env                      # credenciales de juguete (van al repo a propósito)
├── .gitignore
├── requirements.txt
├── init/
│   └── 01_schemas.sql        # crea bronze, silver y gold al iniciar
├── airflow/
│   └── passwords.json        # login admin/admin
├── dags/
│   ├── bronze/
│   │   └── dag_g09_bronze_open_meteo.py
│   ├── dag_silver.py
│   └── dag_gold.py
├── dashboard/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
└── docs/
    ├── ARQUITECTURA_BRONZE.md
    └── ESTADO_BRONZE.md
```

## Estado del proyecto

- [x] Infraestructura propia del grupo (Airflow 3.1.5, schemas automáticos, login admin/admin).
- [x] Bronze: ingesta de las tres localidades, automática al levantar el stack.
- [x] Silver: limpieza en SQL, disparada automáticamente por el asset de Bronze.
- [x] Gold: modelo estrella en SQL, disparado automáticamente por el asset de Silver.
- [x] Contenedor del dashboard.
- [x] Dashboard con gráficos sobre Gold.
## Cómo levantarlo

**Requisitos:** Docker Desktop abierto, y los puertos `5432`, `8080` y `8501` libres. Si está corriendo el stack de la materia, apagarlo antes (`docker compose down` en la carpeta `stack/`).

```powershell
cd TpFinal/grupos/G09
docker compose up -d --build
```

No hace falta crear schemas ni activar DAGs: al levantar, Bronze corre solo y dispara las capas siguientes. La primera vez tarda unos minutos, porque descarga las imágenes y construye el dashboard.

| Servicio | Dirección | Usuario | Contraseña |
|---|---|---|---|
| **Airflow** | http://localhost:8080 | `admin` | `admin` |
| Dashboard | http://localhost:8501 | — | — |
| PostgreSQL | `localhost:5432`, base `InfraCienciaDatos` | `admin` | `admin` |

**Verificar que Bronze cargó los datos:**

```powershell
docker compose exec data_warehouse psql -U admin -d InfraCienciaDatos -c "SELECT city, ingested_at FROM bronze.open_meteo_raw;"
```

**Apagar:**

- `docker compose down` apaga y conserva los datos.
- `docker compose down -v` apaga y borra todo; al volver a levantar, el pipeline corre de nuevo desde cero.

## Nota sobre credenciales

El `.env` está en el repositorio **a propósito**, como pide la consigna: contiene solo credenciales de juguete (`admin/admin`) para que el stack levante con un solo comando. Open-Meteo no requiere API key.

El check de **GitGuardian** del PR marca el `.env` como posible secreto. Es esperado: no contiene claves reales.