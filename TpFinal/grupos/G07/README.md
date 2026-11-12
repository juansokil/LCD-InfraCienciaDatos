# TP Final - G07

## Integrantes

- Uriel Grochowski (ugro2904)
- Antonella Trinidad Frutos ()
- Maria Sol Ibar Jalil (solibarjalil)
- Lucas Patricio Isla (lisla23)

## API elegida

- **Nombre**: USGS Earthquakes
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- **Descripcion**: API pública que proporciona información sobre eventos sísmicos a nivel mundial, incluyendo magnitud, fecha, ubicación geográfica, coordenadas y profundidad.
- **Auth**: Sin autenticación.
- **API key**: No necesita.
- **Refresh**: Cada minuto.

## Modelo de datos

### Bronze

Se realizó la extracción de datos sobre los sismos desde la API de USGS Earthquakes. La información obtenida se guarda en una base de datos PostgreSQL, dentro de la tabla `bronze.sismos_raw`.

**La tabla contiene los siguientes datos:

- `id`: número que identifica cada registro.
- `event_id`: identificador del sismo en USGS.
- `payload`: registro original completo en formato JSONB.
- `ingested_at`: fecha y hora en que se guardaron los datos.
- `source_updated_ms`: fecha de última actualización del evento en USGS.

Para obtener los datos utilizamos el archivo `scripts/ingest_usgs.py`, que se ejecuta automaticamente a través del DAG `bronze_usgs_g07` en Airflow.

Este proceso permite guardar la información orginal sin modificarla y evita duplicar registros cuando se vuelve a ejecutar, siempre que el sismo y su fecha de actualizacion sean los mismos.

### Silver

En esta etapa, los datos almacenados en Bronze se procesan a traves de consultas SQL y se guardan en la tabla `silver.sismos`.

Los procesos realizados son:
    - Obtención de los campos necesarios a partir del JSONB original.+
    - Transformacion de las fechas en formato Unix a TIMESTAMPT.
    - Conversion de los datos de magnitud, latitud, longitus, profundidad a valores numericos.
    - Identificacion y seleccion de la informacion más actualizada de cada sismo.
    - Prevención de registros duplicados utilizando `event_id` como primary key.
    - Actualizacón de los datos existentes cuando USGS informa una nueva versión de un evento.

Archivos ulitizados:
    - `sql/02_create_silver.sql`: define el schema y crea la tabla correspondiente a Silver.
    - `sql/03_transform_silver.sql`: contiene las consultas SQL necesarias para transformar los datos.
    - `dags/silver_usgs_g07.py`: permite ejecutar el procesamiento de Silver mediante Airflow.

Una vez que el DAG de bronze termina su ejecucion de manera exitosa, se inicia automaticamente en DAG de silver.

### Gold

En esta etapa, los datos provenientes de Silver se estructuran mediante un modelo dimensional tipo estrella.

El esquema `gold`está compuesto por tres tablas:
    - `gold.dim_fecha`: contiene la información temporal de cada sismo (fecha, año, mes y día)
    - `gold.dim_region`: guarda la ubicación informada por USGS para cada sismo.
    - `gold.fact_sismos`: tabla principal que registra el identificador de cada sismo, su magnitud, profunidad y cantidad. Se vincula con las otras dos tablas con `fecha_id` y `region_id`.

El procesamiento de los datos slo hacemos con consultas SQL ejecutadas en PostgreSQL. 
Para insertar y actualizar los registros utilizamos `INSERT` y `ON CONFLICT`, para evitar duplicar la información.

Archivos utilizados:
    - `sql/04_create_gold.sql`: define y crea el esquma gold y las tablas
    - `sql/05_transform_gold.sql`: las consultas necesarias para transformar silver a gold
    - `dags/gold_usgs_g07.py`: permite ejecutar las transformaciones automaticamente en Airflow

Las distintas etapas estan conectadas a traves de Airflow. Una vez que termina bronze, empieza silver y cuando termina arranca gold.

## Como levantar el stack

Desde la carpeta del grupo:
```bash
cd TpFinal/grupos/G07/
docker compose up -d --build
```

**Accesos:**

- **Airflow UI:** http://localhost:8081 (`admin` / `admin`)
- **Postgres:** `localhost:5433` (usuario y contraseña definidos en `.env`).

**Apagar:**

```bash
docker compose down
```

Para eliminar también los volúmenes:
```bash
docker compose down -v
```

## Estructura del proyecto

- `docker-compose.yml`: configuración de los servicios de PostgreSQL y Airflow.
- `.env`: variables de entorno.
- `airflow_passwords.json`: credenciales de acceso a Airflow.
- `scripts/ingest_usgs.py`: obteniene y carga los datos de USGS.
- `sql/01_create_bronze.sql`: define y crea la tabla correspondiente a Bronze.
- `sql/02_create_silver.sql`: define y crea la tabla correspondiente a Silver.
- `sql/03_transform_silver.sql`: consultas para transformar los datos de Bronze a Silver.
- `sql/04_create_gold.sql`: define y crea las tablas del esquema Gold.
- `sql/05_transform_gold.sql`: consultas para transformar los datos de Silver a Gold.
- `dags/bronze_usgs_g07.py`: DAG de carga de datos.
- `dags/silver_usgs_g07.py`: DAG de transformaciones de Silver.
- `dags/gold_usgs_g07.py`: DAG de transformaciones de Gold.
- `dags/prueba_g07.py`: DAG de prueba.