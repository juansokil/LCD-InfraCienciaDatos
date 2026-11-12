# TP Final - Grupo 09

## Integrantes
* [Lisandro Farina] - [@lisandrofarina06]
* [Lucas Feller] - [lucasfeller]
* Juan Pablo Varini - [JuanPablo0620]
* Matias Bardelli - [@stx-06]

## API Elegida
**Open-Meteo (Clima)**: https://open-meteo.com/

## Idea para Gold
Construir un modelo en estrella con:
* `fact_clima_diario`: temperaturas, lluvia y viento por ciudad y día.
* `dim_ciudad`: nombre de la ciudad, latitud y longitud.
* `dim_tiempo`: fecha, mes y estación del año.
**Dashboard:** Un mapa o gráfico comparativo de temperaturas entre ciudades y alertas de temperaturas extremas.

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
Silver  ──►  Gold  ──►  Dashboard
```

- Los schemas se crean solos al iniciar la base (`init/01_schemas.sql`).
- Los DAGs arrancan activos: no hace falta despausarlos a mano.
- Cada capa dispara a la siguiente mediante assets de Airflow.

## Modelo de datos

**Bronze** — `bronze.open_meteo_raw`: una fila por localidad e ingesta, con la respuesta original de la API en JSONB (`response_payload`) y los parámetros del pedido. Detalle en `docs/ARQUITECTURA_BRONZE.md`.

**Silver y Gold** — en desarrollo (ver *Idea para Gold* arriba).

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
│   └── dag_silver.py
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
- [x] Ingesta Bronze de las tres localidades, automática al levantar el stack.
- [x] Contenedor del dashboard.
- [ ] Silver (transformación en SQL).
- [ ] Gold (modelo estrella).
- [ ] Dashboard con gráficos.

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