# TP Final - G07

## Integrantes

- Uriel Grochowski (ugro2904)
- Antonella Trinidad Frutos ()
- Maria Sol Ibar Jalil (solibarjalil)
- Lucas Patricio Isla (Lisla23)

## Credenciales de Acceso (Airflow)
  **Usuario:** admin
  **Contraseña:** admin

## API elegida

- **Nombre**: USGS Earthquakes
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- **Descripción**: API pública que proporciona información sobre eventos sísmicos a nivel mundial, incluyendo magnitud, fecha, ubicación geográfica, coordenadas y profundidad.
- **Auth**: Sin autenticación.
- **API key**: No necesita.
- **Refresh**: El DAG de Bronze corre **cada hora** (`@hourly`). La API actualiza más seguido, pero el feed usado (`2.5_month`, sismos M2.5+ de los últimos 30 días) permite tener datos consolidados sin sobrecargar el sistema.

## Modelo de datos

Se implementó la **Arquitectura Medallion (Bronze → Silver → Gold)** utilizando PostgreSQL para el almacenamiento y SQL para las transformaciones, orquestado completamente por Apache Airflow 3.1.5.

### Bronze (Extracción)

Se realiza la extracción de datos desde la API de USGS. La información obtenida se guarda tal cual llega (JSON crudo) en PostgreSQL, dentro de la tabla `bronze.sismos_raw`.

- `id`: número que identifica cada registro.
- `event_id`: identificador del sismo en USGS.
- `payload`: registro original completo en formato JSONB.
- `ingested_at`: fecha y hora en que se guardaron los datos.
- `source_updated_ms`: fecha de última actualización del evento en USGS.

**Proceso**: El script `scripts/ingest_usgs.py` se ejecuta a través del DAG `bronze_usgs_g07`. Evita duplicar registros cuando se vuelve a ejecutar, comparando el `event_id` y su fecha de actualización.

### Silver (Limpieza y Transformación)

Los datos de Bronze se procesan con SQL para extraer los campos necesarios y guardarlos en `silver.sismos`.

**Transformaciones aplicadas**:
- Extracción de campos desde el JSONB original.
- Transformación de fechas en formato Unix a `TIMESTAMPTZ`.
- Conversión de magnitudes, latitud, longitud y profundidad a tipos numéricos.
- Selección de la información más actualizada de cada sismo (`DISTINCT ON`).
- Prevención de duplicados usando `event_id` como clave primaria, con actualización (`ON CONFLICT DO UPDATE`) si USGS reporta una nueva versión.

**Archivos**:
- `sql/02_create_silver.sql`: define el esquema y la tabla.
- `sql/03_transform_silver.sql`: consultas de transformación.
- `dags/silver_usgs_g07.py`: DAG que ejecuta el SQL.

### Gold (Modelado Dimensional)

Los datos de Silver se estructuran en un **Modelo Estrella** para facilitar el análisis de la actividad sismica.

**Tablas**:
- `gold.dim_fecha`: información temporal (fecha, año, mes, día, día de la semana).
- `gold.dim_region`: ubicación geográfica extraída del campo `place` de USGS.
- `gold.fact_sismos`: tabla de hechos que registra el evento, magnitud, profundidad, coordenadas, si generó tsunami y su relación con `fecha_id` y `region_id`.

**Vista:**
- `gold.v_sismos_dashboard`: reúne la información de las tablas Gold para facilitar las consultas del dashboard.

**Proceso**: Las inserciones y actualizaciones usan `INSERT ... ON CONFLICT` para mantener la idempotencia.
El DAG `gold_usgs_g07` incluye una tarea de validación que asegura la integridad referencial (no haya huérfanos) y la reconciliación (misma cantidad de registros que en Silver).

**Archivos**:
- `sql/04_create_gold.sql`: define el esquema y las tablas.
- `sql/05_transform_gold.sql`: consultas de transformación.
- `dags/gold_usgs_g07.py`: DAG de construcción y validación.

## Dashboard

Se desarrolló una aplicación interactiva con **Streamlit** y **Plotly** que consume exclusivamente las tablas de la capa Gold.

**Características principales**:
- KPIs generales: total de sismos, magnitud promedio, magnitud máxima y cantidad de alertas de tsunami.
- Gráfico de serie temporal (sismos por día).
- Histograma de distribución de magnitudes.
- Ranking de las 10 regiones con más sismos.
- Mapa mundial interactivo con los epicentros coloreados por magnitud.
- Filtros por rango de fechas, región y magnitud.

**Archivos**:
- `dashboard/app.py`: código de la aplicación.
- `dashboard/Dockerfile`: imagen de Docker para el servicio.
- `dashboard/requirements.txt`: dependencias de Python.

## Orquestación

El pipeline está completamente automatizado en Airflow 3.1.5:
1. `bronze_usgs_g07` se ejecuta según su horario (o manualmente). Al terminar, dispara automáticamente el siguiente DAG usando `TriggerDagRunOperator`.
2. `silver_usgs_g07` procesa los datos crudos y dispara a Gold.
3. `gold_usgs_g07` construye el modelo estrella y ejecuta las validaciones de calidad.

## Cómo levantar el stack

Desde la carpeta del grupo:
```bash
cd TpFinal/grupos/G07/
docker compose up -d --build

### Accesos

 - **Airflow:** http://localhost:8081
 - **Dashboard:** http://localhost:8501
 - **PostgreSQL:** localhost:5433 (credenciales en `.env`).