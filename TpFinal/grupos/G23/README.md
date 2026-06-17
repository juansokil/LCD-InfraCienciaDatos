# TP Final - G23 - CityBikes EcoBici Buenos Aires

## Integrantes

- Facundo Pellicori (@FacundoPellicori)
- Marcos Benson (@marcosbenson)
- Nombre Apellido (@usuario-github)

## API elegida

- **Nombre**: CityBikes - EcoBici Buenos Aires
- **URL**: https://api.citybik.es/v2/networks/ecobici-buenos-aires
- **Descripcion**: Devuelve el estado actualizado de las estaciones de EcoBici Buenos Aires, incluyendo ubicacion, bicicletas disponibles, espacios libres y timestamp de actualizacion por estacion.
- **Auth**: Sin auth
- **Refresh**: La API devuelve datos actualizados de disponibilidad por estacion. No se especifica una frecuencia exacta de actualizacion; el pipeline tomara snapshots cada 15 minutos respetando el limite de 300 requests por hora.

## Modelo de datos

### Bronze

Se guardaran snapshots crudos de estaciones EcoBici Buenos Aires desde el endpoint de CityBikes.

Tabla principal:

`bronze.ecobici_stations_raw`

Grano: una fila por estacion por snapshot de ingesta.

Columnas principales:

- `snapshot_id`: identificador de la ingesta.
- `ingested_at`: fecha y hora en que el DAG ingirio el dato.
- `source`: fuente de datos (`citybikes`).
- `network_id`: identificador de la red (`ecobici-buenos-aires`).
- `station_id`: identificador de la estacion.
- `station_name`: nombre de la estacion.
- `latitude`: latitud.
- `longitude`: longitud.
- `free_bikes`: bicicletas disponibles.
- `empty_slots`: espacios libres.
- `station_timestamp`: timestamp informado por la API.
- `extra_json`: campo `extra` completo de la estacion.
- `raw_json`: registro completo de la estacion tal como llego desde la API.

### Silver

Se construira una tabla limpia:

`silver.ecobici_stations`

Transformaciones previstas:

- Parsear `station_timestamp`, `last_updated` e `ingested_at` como timestamps.
- Tipar `latitude`, `longitude`, `free_bikes`, `empty_slots`, `slots` y `normal_bikes` como numericos.
- Normalizar `station_name` y `address` quitando espacios extra.
- Extraer campos utiles desde `extra_json`: `uid`, `renting`, `returning`, `last_updated`, `address`, `slots`, `normal_bikes`, `virtual`.
- Validar que `free_bikes`, `empty_slots`, `slots` y `normal_bikes` no sean negativos.
- Validar coordenadas dentro de un rango razonable para Buenos Aires.
- Deduplicar por `snapshot_id` + `station_id`.
- Crear metricas tecnicas como `total_capacity` y `occupancy_ratio`.
- Enviar a cuarentena registros con datos invalidos o incompletos criticos.

### Gold

Se construira un modelo dimensional orientado al dashboard:

- `gold.dim_station`: dimension de estaciones, con `station_id`, `station_name`, `address`, `latitude`, `longitude`, `slots` y estado operativo.
- `gold.dim_time`: dimension temporal, con fecha, hora, dia de semana y franja horaria.
- `gold.fact_station_availability`: tabla de hechos con una fila por estacion y snapshot, incluyendo `free_bikes`, `empty_slots`, `total_capacity`, `occupancy_ratio` y `availability_ratio`.
- `gold.abt_station_usage`: tabla analitica desnormalizada por estacion, con metricas agregadas como disponibilidad promedio, ocupacion promedio, cantidad de snapshots, minimos/maximos de bicicletas disponibles y flags de estacion critica.

El dashboard buscara responder preguntas como:

- Que estaciones tienen mayor o menor disponibilidad de bicicletas.
- Que estaciones suelen estar llenas o vacias.
- Como cambia la disponibilidad por hora del dia.
- Cuales son las estaciones criticas para redistribucion de bicicletas.

## Como levantar el stack

```bash
cd TpFinal/grupos/G23/
cp .env.example .env
docker compose up -d --build
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8080 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` (user/pass en `.env`)

**Apagar**:
```bash
docker compose down
docker compose down -v
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md).
