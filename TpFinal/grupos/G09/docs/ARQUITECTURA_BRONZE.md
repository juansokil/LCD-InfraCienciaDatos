# Arquitectura Bronze — G09

## 1. Objetivo

La capa Bronze tiene como objetivo obtener y conservar los datos meteorológicos originales provenientes de Open-Meteo.

Se utilizan tres localidades de la provincia de Buenos Aires:

| Localidad | Región |
|---|---|
| Mar del Plata | Costa |
| Tandil | Interior |
| Bahía Blanca | Sur |

## 2. Fuente de datos

**Open-Meteo Historical Weather API**

Endpoint:

https://archive-api.open-meteo.com/v1/archive

Modelo solicitado: ERA5.

Se utiliza un modelo de reanálisis para mantener una fuente histórica consistente. Los datos representan estimaciones de modelos y no necesariamente mediciones directas de estaciones meteorológicas locales.

## 3. Variables meteorológicas

| Variable | Descripción | Unidad |
|---|---|---|
| temperature_2m_mean | Temperatura media | °C |
| temperature_2m_max | Temperatura máxima | °C |
| temperature_2m_min | Temperatura mínima | °C |
| precipitation_sum | Precipitación acumulada | mm |
| precipitation_hours | Horas con precipitación | h |
| relative_humidity_2m_mean | Humedad relativa media | % |
| wind_speed_10m_mean | Velocidad media del viento | km/h |
| wind_speed_10m_max | Velocidad máxima del viento | km/h |
| wind_direction_10m_dominant | Dirección dominante del viento | ° |
| cloud_cover_mean | Nubosidad media | % |

Zona horaria: America/Argentina/Buenos_Aires.

## 4. Período temporal

La configuración inicial utiliza 2015-01-01 como fecha de inicio provisional.

La fecha final se calcula restando cinco días a la fecha actual, para contemplar el retraso habitual de disponibilidad de ERA5.

El período definitivo deberá ser acordado por los integrantes del grupo.

Se pueden utilizar las variables de entorno G09_START_DATE y G09_END_DATE para modificar el rango.

## 5. Arquitectura

El pipeline reutiliza la infraestructura general de la materia:

- Airflow para la orquestación.
- Docker para ejecutar los servicios.
- PostgreSQL como Data Warehouse.
- Open-Meteo como fuente de información.

No se crean servicios independientes para G09.

## 6. Tabla de destino

Tabla: bronze.open_meteo_raw.

Cada registro representa una captura de la respuesta API para una localidad y una ejecución.

| Campo | Descripción |
|---|---|
| ingestion_id | Identificador de la captura |
| location_id | Identificador de la localidad |
| city | Nombre de la localidad |
| region_type | Clasificación geográfica |
| requested_latitude | Latitud consultada |
| requested_longitude | Longitud consultada |
| requested_start_date | Fecha inicial |
| requested_end_date | Fecha final |
| api_url | Endpoint utilizado |
| request_params | Parámetros de consulta |
| response_payload | Respuesta JSON original |
| ingested_at | Fecha y hora de ingesta |

## 7. Criterios de diseño

- Se conserva la respuesta original de la API.
- No se realizan transformaciones analíticas en Bronze.
- Cada ejecución agrega una nueva captura.
- Se registra la metadata necesaria para auditar la ingesta.
- Las tareas de cada localidad pueden ejecutarse independientemente.
- Se contemplan reintentos ante fallos de conexión o consulta.

## 8. Próximas etapas

1. Acordar el período histórico definitivo.
2. Validar las variables meteorológicas.
3. Diseñar la capa Silver.
4. Expandir los JSON a registros diarios.
5. Controlar valores faltantes y duplicados.
6. Diseñar la capa Gold.
7. Construir visualizaciones y análisis comparativos.

## 9. Referencias

Open-Meteo Historical Weather API:

https://open-meteo.com/en/docs/historical-weather-api