# G09 – Estado de implementación: Capa Bronze

## 1. Objetivo

Implementar la primera etapa del pipeline de datos del proyecto G09, cuyo objetivo es analizar cómo varían las condiciones meteorológicas entre tres regiones de la provincia de Buenos Aires:

- **Costa:** Mar del Plata.
- **Interior:** Tandil.
- **Sur:** Bahía Blanca.

La fuente de datos seleccionada es la API histórica de [Open-Meteo](https://open-meteo.com/).

La implementación utiliza el Docker Compose propio del grupo (`TpFinal/grupos/G09/docker-compose.yml`), con Airflow 3.1.5 y PostgreSQL.

## 2. Estado actual

**Primera ingesta Bronze ejecutada correctamente.**

Se verificó que:

- Airflow detecta los DAGs ubicados en la carpeta de G09.
- Airflow puede conectarse al servicio PostgreSQL `data_warehouse`.
- Se creó el esquema `bronze`.
- Se creó la tabla `bronze.open_meteo_raw`.
- Bronze corre solo al levantar el stack (`schedule="@once"`), sin activar el DAG a mano.
- Se ejecutaron correctamente las tres tareas de ingesta.
- Las respuestas de Open-Meteo quedaron almacenadas en PostgreSQL.
- Al terminar las tres ingestas, se publica el Asset `g09_bronze_open_meteo_raw`.
- Se verificó mediante consultas SQL la presencia de las tres localidades.

## 3. Arquitectura implementada

El flujo de datos es:

```text
Open-Meteo API
      |
      v
Apache Airflow
      |
      | DAG: g09_bronze_open_meteo
      |
      +---- Mar del Plata
      |
      +---- Tandil
      |
      +---- Bahía Blanca
      |
      v
PostgreSQL
      |
      v
bronze.open_meteo_raw
```

### Componentes utilizados

| Componente | Función |
|---|---|
| Open-Meteo | Proveedor de datos meteorológicos |
| Docker Compose | Administración de los servicios |
| Apache Airflow | Orquestación de las ingestas |
| Python | Extracción y carga de datos |
| Requests | Consumo de la API |
| SQLAlchemy | Conexión e interacción con PostgreSQL |
| PostgreSQL | Almacenamiento de los datos originales |

## 4. Fuente de datos

**API:** Open-Meteo Historical Weather API.

Endpoint:

```text
https://archive-api.open-meteo.com/v1/archive
```

Modelo meteorológico solicitado: ERA5.

Zona horaria: `America/Argentina/Buenos_Aires`.

### Localidades

| Identificador | Localidad | Región | Latitud | Longitud |
|---|---|---|---:|---:|
| mar_del_plata | Mar del Plata | Costa | -38.0055 | -57.5426 |
| tandil | Tandil | Interior | -37.3217 | -59.1332 |
| bahia_blanca | Bahía Blanca | Sur | -38.7196 | -62.2724 |

### Variables meteorológicas solicitadas

- Temperatura media diaria.
- Temperatura máxima diaria.
- Temperatura mínima diaria.
- Precipitación acumulada diaria.
- Horas de precipitación.
- Humedad relativa media.
- Velocidad media del viento.
- Velocidad máxima del viento.
- Dirección predominante del viento.
- Nubosidad media.

Las unidades solicitadas son Celsius, milímetros, kilómetros por hora y porcentajes, según corresponda.

## 5. Implementación del DAG

**Identificador:** `g09_bronze_open_meteo`

**Ubicación del archivo:**

```text
TpFinal/
└── grupos/
    └── G09/
        └── dags/
            └── bronze/
                └── dag_g09_bronze_open_meteo.py
```

El DAG tiene tres etapas:

1. `create_bronze_table`: crea el esquema y la tabla de almacenamiento si todavía no existen.
2. `ingest_location`: obtiene los datos de cada localidad y almacena la respuesta de la API.
3. `publish_bronze_asset`: se ejecuta cuando terminaron las tres ingestas y publica el Asset de salida.

La segunda tarea utiliza mapeo dinámico de Airflow, por lo que se generan tres instancias independientes, una por localidad.

Bronze corre una vez al levantar el stack (`schedule="@once"`). Al finalizar, `publish_bronze_asset` publica el Asset `g09_bronze_open_meteo_raw`, que dispara la capa Silver.

El Asset se publica una sola vez, después de las tres ingestas, para que Silver no arranque con datos incompletos.

## 6. Modelo de almacenamiento Bronze

Tabla:

```sql
bronze.open_meteo_raw
```

La tabla conserva la respuesta original de la API en formato JSONB.

Principales campos:

| Campo | Descripción |
|---|---|
| ingestion_id | Identificador único de la ingesta |
| location_id | Identificador de la localidad |
| city | Nombre de la localidad |
| region_type | Costa, Interior o Sur |
| requested_latitude | Latitud solicitada |
| requested_longitude | Longitud solicitada |
| requested_start_date | Fecha inicial solicitada |
| requested_end_date | Fecha final solicitada |
| api_url | Endpoint consultado |
| request_params | Parámetros enviados a la API |
| response_payload | Respuesta original en JSONB |
| ingested_at | Fecha y hora de ingesta |

### Criterio de almacenamiento

Se decidió conservar la respuesta original de la API en Bronze, sin realizar transformaciones ni normalizaciones.

Por lo tanto, cada fila representa una ingesta completa de una localidad y no una observación meteorológica diaria.

Esta decisión permite conservar la fuente original y realizar las transformaciones posteriormente en Silver.

## 7. Primera ingesta: resultados

**Período solicitado:** 01/01/2015 al 05/11/2026.

| Localidad | Región | Cantidad de días | Ingestas |
|---|---|---:|---:|
| Mar del Plata | Costa | 4327 | 1 |
| Tandil | Interior | 4327 | 1 |
| Bahía Blanca | Sur | 4327 | 1 |
| **Total** | | **12.981** | **3** |

La tabla contiene actualmente tres filas, cada una con su correspondiente respuesta JSON.

La ejecución del DAG finalizó correctamente y las cinco tareas (una de creación, tres de ingesta y otra de publicación del Asset) quedaron en estado exitoso.

**Importante:** el período utilizado corresponde a la primera carga de prueba funcional. Todavía debe acordarse con el grupo si será el período definitivo del análisis.

## 8. Cómo levantar el entorno

Desde la carpeta del grupo (`TpFinal/grupos/G09`):

```powershell
cd TpFinal/grupos/G09
docker compose up -d
```

Verificar los servicios:

```powershell
docker compose ps
```

Se deben encontrar activos:

- `airflow`
- `airflow_db`
- `data_warehouse`

El servicio `data_warehouse` debe estar en estado `healthy`.

No hace falta activar ningún DAG: Bronze arranca solo.

Airflow se encuentra disponible en:

```text
http://localhost:8080
```

Usuario y contraseña: `admin` / `admin`.

### Consultar los datos almacenados

Para acceder a PostgreSQL:

```powershell
docker compose exec data_warehouse psql -U admin -d InfraCienciaDatos
```

Consulta para verificar las ingestas:

```sql
SELECT
    ingestion_id,
    city,
    region_type,
    requested_start_date,
    requested_end_date,
    jsonb_array_length(
        response_payload->'daily'->'time'
    ) AS cantidad_dias,
    ingested_at
FROM bronze.open_meteo_raw
ORDER BY ingested_at DESC;
```

Para salir de PostgreSQL:

```sql
\q
```

## 9. Decisiones pendientes y próximos pasos

La implementación Bronze está funcionando, pero todavía no representa el pipeline completo del proyecto.

Antes de avanzar, el grupo debería acordar:

1. **Período de análisis:** definir las fechas inicial y final definitivas.
2. **Variables meteorológicas:** confirmar si todas las variables seleccionadas son necesarias para responder la pregunta del proyecto.
3. **Modelo de datos Silver:** definir la estructura tabular que utilizarán los análisis posteriores.
4. **Calidad de datos:** establecer controles para valores faltantes, duplicados y consistencia temporal.

### Próximas etapas propuestas

- [x] Encadenar Bronze con Silver mediante Assets.
- [ ] Validar la integridad de las respuestas almacenadas en Bronze.
- [ ] Acordar el período definitivo con el grupo.
- [ ] Diseñar la transformación Bronze → Silver.
- [ ] Implementar la capa Silver.
- [ ] Diseñar la capa Gold y las métricas de comparación.
- [ ] Realizar análisis exploratorio.
- [ ] Desarrollar visualizaciones y dashboard.

## 10. Referencias

- Open-Meteo: https://open-meteo.com/
- Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
- Apache Airflow: https://airflow.apache.org/docs/
- PostgreSQL: https://www.postgresql.org/docs/
- SQLAlchemy: https://docs.sqlalchemy.org/