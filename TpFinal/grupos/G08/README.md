# TP Final - G08 - Open-Meteo

Pipeline de datos meteorologicos con arquitectura medallion usando Airflow, PostgreSQL, Docker Compose y Streamlit.

## Integrantes

- Tiziano Stacchino
- Elias Romero
- Mariano Fernandez
- Martin Bustamante

## Resumen del proyecto

El objetivo del trabajo es construir un pipeline end-to-end que tome datos de una API publica, los procese en capas Bronze, Silver y Gold, y los exponga en un dashboard.

La API elegida es Open-Meteo, que permite consultar informacion meteorologica por coordenadas geograficas sin usar API key. En este proyecto se consultan datos para tres ciudades argentinas:

- Buenos Aires
- Cordoba
- Mendoza

El resultado final es una tabla analitica diaria por ciudad, `gold.weather_daily_summary`, que alimenta el dashboard de Streamlit.

## API elegida

- **Nombre**: Open-Meteo
- **URL**: https://open-meteo.com/
- **Endpoint usado**: `https://api.open-meteo.com/v1/forecast`
- **Autenticacion**: no requiere API key.
- **Frecuencia de actualizacion**: cada hora.
- **Datos solicitados**:
  - Temperatura actual.
  - Humedad relativa.
  - Sensacion termica.
  - Precipitacion.
  - Viento.
  - Pronostico horario de temperatura, precipitacion y viento.
  - Pronostico diario de temperatura maxima, minima y precipitacion acumulada.

## Arquitectura general

```text
Open-Meteo API
      |
      v
Airflow DAG Bronze
      |
      v
bronze.weather_raw
      |
      v
Airflow DAG Silver
      |
      v
silver.weather_hourly
      |
      v
Airflow DAG Gold
      |
      v
gold.weather_daily_summary
      |
      v
Streamlit Dashboard
```

La solucion sigue el stack del curso:

- **Airflow**: orquestacion de los DAGs.
- **PostgreSQL**: data warehouse con schemas `bronze`, `silver` y `gold`.
- **Streamlit**: dashboard final.
- **Docker Compose**: levanta todos los servicios del proyecto.

## Servicios Docker

El archivo `docker-compose.yml` define cuatro servicios:

- `airflow`: ejecuta los DAGs del pipeline.
- `airflow_db`: base interna de Airflow para metadatos.
- `data_warehouse`: PostgreSQL principal del TP, donde viven Bronze, Silver y Gold.
- `dashboard`: aplicacion Streamlit que consume Gold.

Puertos expuestos:

- Airflow: `localhost:8080`
- Streamlit: `localhost:8501`
- PostgreSQL warehouse: `localhost:5433`

La base de datos principal se llama `TpFinal` y usa:

- Usuario: `admin`
- Password: `admin`

## Capas del pipeline

### Bronze

DAG: `g08_openmeteo_bronze`

Archivo:

```text
dags/01-bronze/openmeteo_bronze.py
```

Schedule:

```text
@hourly
```

Tabla:

```text
bronze.weather_raw
```

Columnas principales:

- `id`
- `city`
- `latitude`
- `longitude`
- `raw_json`
- `ingested_at`

Bronze consulta Open-Meteo para Buenos Aires, Cordoba y Mendoza y guarda la respuesta completa en formato JSON. Esta capa conserva el dato original como fuente de verdad. No limpia ni agrega informacion: solo registra lo que devuelve la API junto con metadatos de auditoria.

### Silver

DAG: `g08_openmeteo_silver`

Archivo:

```text
dags/02-silver/openmeteo_silver.py
```

Schedule:

```text
10 * * * *
```

Tabla:

```text
silver.weather_hourly
```

Columnas principales:

- `city`
- `forecast_time`
- `temperature_2m`
- `precipitation`
- `wind_speed_10m`
- `ingested_at`
- `source_raw_id`

Silver lee `bronze.weather_raw`, desanida el bloque `hourly` del JSON y crea una fila por ciudad y hora pronosticada.

La tabla esta deduplicada con:

```text
PRIMARY KEY (city, forecast_time)
```

Tambien incluye validaciones basicas:

- `precipitation >= 0`
- `wind_speed_10m >= 0`
- `temperature_2m BETWEEN -80 AND 60`

Si el DAG se ejecuta mas de una vez, usa `ON CONFLICT` para actualizar solo cuando el nuevo `ingested_at` es mayor o igual al existente. Esto evita duplicados y mantiene la version mas reciente.

### Gold

DAG: `g08_openmeteo_gold`

Archivo:

```text
dags/03-gold/openmeteo_gold.py
```

Schedule:

```text
20 * * * *
```

Tabla principal:

```text
gold.weather_daily_summary
```

Columnas principales:

- `city`
- `forecast_date`
- `avg_temperature`
- `max_temperature`
- `min_temperature`
- `temperature_range`
- `total_precipitation`
- `rainy_hours`
- `avg_wind_speed`
- `max_wind_speed`
- `hourly_records`
- `weather_category`
- `outdoor_score`
- `outdoor_recommendation`
- `updated_at`

Gold agrega los datos horarios de Silver por ciudad y dia. La fecha se calcula en zona horaria argentina:

```sql
(forecast_time AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
```

La tabla queda con una fila por:

```text
city + forecast_date
```

La clave primaria evita duplicados:

```text
PRIMARY KEY (city, forecast_date)
```

Gold tambien agrega informacion analitica que no existe en Silver:

- Categoria climatica (`weather_category`):
  - `lluvioso`
  - `ventoso`
  - `frio`
  - `caluroso`
  - `agradable`
- Puntaje para actividades al aire libre (`outdoor_score`) de 0 a 100.
- Recomendacion textual (`outdoor_recommendation`).

Esta capa es la que consume el dashboard.

## Dashboard Streamlit

Archivos principales:

```text
dashboard/app.py
dashboard/db.py
dashboard/pages/1_Gold_Clima.py
```

El dashboard consume exclusivamente:

```text
gold.weather_daily_summary
```

No consulta Bronze ni Silver.

Indicadores mostrados:

- Temperatura promedio.
- Temperatura maxima.
- Temperatura minima.
- Precipitacion total.
- Viento promedio.

Visualizaciones:

- Evolucion de temperatura promedio por fecha.
- Precipitacion total por fecha.
- Viento promedio por ciudad.
- Score outdoor promedio por ciudad.
- Tabla final con metricas Gold, categoria climatica y recomendacion.

## Como ejecutar el proyecto

Desde la carpeta del grupo:

```bash
cd TpFinal/grupos/G08
cp .env.example .env
docker compose up -d --build
```

Accesos:

- Airflow: http://localhost:8080
- Streamlit: http://localhost:8501
- PostgreSQL: `localhost:5433`


## Conexion desde DBeaver

Crear una conexion PostgreSQL con:

- Host: `localhost`
- Port: `5433`
- Database: `TpFinal`
- Username: `admin`
- Password: `admin`

Importante: `TpFinal` es la base de datos, no el usuario. Los schemas `bronze`, `silver` y `gold` estan dentro de esa base.

## Notas sobre inicializacion de Postgres

El archivo `init.sql` crea los schemas:

```sql
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
```

Postgres ejecuta `init.sql` solamente cuando el volumen del contenedor esta vacio. Si el volumen `g08_data_warehouse_data` ya existia, el script no vuelve a correr automaticamente.



