# 🌦️ TP Final - Grupo 03

## Infraestructura para Ciencia de Datos - UNSAM

---

## 👥 Integrantes

| Integrante | Usuario GitHub |
| ---------- | -------------- |
| Martina Lopez | @martinalopez12 |
| Alejandro Rodriguez | @AleRC99 |
| Sofia Trayer | @treyersofia |
| Nadia Janulik | @NayJanu |
| Salvador D'Angelo | @salvi-1005 |

---

## 📌 Descripción General

Este proyecto implementa un pipeline de ingesta y procesamiento de datos climáticos utilizando la API pública **Open-Meteo** como fuente de información.

La solución utiliza **Apache Airflow** para orquestar los procesos, **PostgreSQL** como base de datos de almacenamiento y **Docker Compose** para levantar el entorno completo de forma reproducible.

El proyecto sigue una arquitectura **Medallion**, con foco en las capas:

- **Bronze:** almacenamiento de datos crudos en formato `JSONB`.
- **Silver:** limpieza, normalización y separación de datos climáticos en tablas estructuradas.
- **Gold:** modelo dimensional y tablas analíticas generadas desde Silver para consumo de dashboard y análisis.

Durante el testeo se validaron correctamente las capas **Bronze**, **Silver** y **Gold**. La capa **Gold** cuenta con un DAG propio, `weather_gold_pipeline`, que consolida métricas reales y de pronóstico en tablas analíticas dentro del esquema `gold`.

---

## 🎯 Objetivo

El objetivo principal es construir un pipeline funcional de datos climáticos que permita:

- Extraer información desde una API pública.
- Automatizar la ingesta mediante Airflow.
- Almacenar snapshots crudos en PostgreSQL.
- Procesar los datos crudos hacia una capa limpia y normalizada.
- Mantener trazabilidad mediante fechas de extracción y procesamiento.
- Construir una capa Gold funcional con métricas agregadas para dashboard y análisis.

---

## 🏗️ Arquitectura Implementada

```text
Open-Meteo API
       │
       ▼
Apache Airflow
       │
       ▼
Bronze
Datos crudos en JSONB
       │
       ▼
Silver
Datos limpios y normalizados
       │
       ▼
Gold
Modelo dimensional y hechos analíticos
```

Estado real al momento del testeo:

```text
Bronze: implementado y validado
Silver: implementado y validado
Gold: implementado y validado mediante DAG weather_gold_pipeline
Dashboard: estructura preparada, pendiente de validación funcional
```

---

## 🛠️ Tecnologías Utilizadas

| Componente | Tecnología |
| ---------- | ---------- |
| Lenguaje | Python |
| Orquestador | Apache Airflow |
| Base de datos | PostgreSQL |
| Containerización | Docker Compose |
| Fuente de datos | Open-Meteo API |
| Procesamiento | Pandas |
| Formato de almacenamiento Bronze | JSONB |
| Dashboard | Streamlit, preparado para futuras etapas |

---

## 🌎 API Utilizada

### Open-Meteo

La API seleccionada fue **Open-Meteo**, una API pública que permite obtener información meteorológica a partir de coordenadas geográficas.

```text
https://api.open-meteo.com/v1/forecast
```

### Características

- No requiere autenticación.
- Devuelve datos en formato JSON.
- Permite consultar datos climáticos por latitud y longitud.
- Es adecuada para ingestas periódicas.
- Permite obtener datos horarios y de pronóstico diario.

---

## 🏙️ Ciudades Configuradas

Las ciudades se encuentran definidas en el archivo:

```text
coordenadas.json
```

Ciudades incluidas:

| Ciudad | País / Región |
| ------ | ------------- |
| Buenos Aires | Argentina |
| Madrid | España |
| Ciudad de México | México |
| Bogotá | Colombia |
| Santiago | Chile |
| Lima | Perú |
| Barcelona | España |
| Berlín | Alemania |

---

## 🌡️ Variables Climáticas Seleccionadas

El archivo `coordenadas.json` define variables climáticas utilizadas por el pipeline.

| Variable | Descripción |
| -------- | ----------- |
| `temperature_2m` | Temperatura del aire a 2 metros |
| `relative_humidity_2m` | Humedad relativa |
| `wind_speed_10m` | Velocidad del viento |
| `precipitation` | Precipitación |
| `weather_code` | Código meteorológico |

En la etapa Silver también se procesan campos adicionales disponibles en el JSON crudo, tales como:

| Variable | Descripción |
| -------- | ----------- |
| `latitude` | Latitud de la ciudad consultada |
| `longitude` | Longitud de la ciudad consultada |
| `wind_direction_10m` | Dirección del viento |
| `is_day` | Indicador de día o noche |
| `timezone` | Zona horaria reportada por la API |
| `temperature_2m_min` | Temperatura mínima diaria |
| `temperature_2m_max` | Temperatura máxima diaria |
| `precipitation_probability_max` | Probabilidad máxima de lluvia |
| `weather_code` | Código meteorológico del período |

---

## 📁 Estructura del Proyecto

```text
G03/
│
├── dags/
│   ├── 01-bronze/
│   │   ├── .gitkeep
│   │   └── weather_bronze.py
│   │
│   ├── 02-silver/
│   │   └── weather_silver.py
│   │
│   └── 03-gold/
│       └── weather_gold.py
│
├── stack/
│   ├── clima-api/
│   │   ├── app/
│   │   │   └── clima.py
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   │
│   └── dashboard/
│       ├── .gitkeep
│       ├── .env.example
│       ├── coordenadas.json
│       └── requirements.txt
│
├── coordenadas.json
├── docker-compose.yml
├── init.sql
├── README.md
├── .gitattributes
└── .gitignore
```

---

## 🧱 Archivos Principales

| Archivo | Descripción |
| ------- | ----------- |
| `docker-compose.yml` | Define los servicios Docker del proyecto |
| `init.sql` | Crea los esquemas `bronze`, `silver`, `gold` y las tablas principales |
| `coordenadas.json` | Contiene ciudades, coordenadas y variables climáticas |
| `dags/01-bronze/weather_bronze.py` | DAG principal de ingesta Bronze |
| `dags/02-silver/weather_silver.py` | DAG de limpieza y normalización Silver |
| `dags/03-gold/weather_gold.py` | DAG de consolidación analítica Gold |
| `README.md` | Documentación del proyecto y del testeo |
| `stack/clima-api/app/clima.py` | Prueba independiente de consulta a Open-Meteo e inserción en PostgreSQL |
| `stack/dashboard/` | Estructura preparada para dashboard |

---

## 🐳 Servicios Docker

El archivo `docker-compose.yml` levanta cuatro servicios:

| Servicio | Contenedor | Función | Puerto |
| -------- | ---------- | ------- | ------ |
| `warehouse` | `g03_warehouse` | PostgreSQL principal del proyecto | `5435:5432` |
| `airflow_db` | `g03_airflow_db` | Base de datos interna de Airflow | Interno |
| `airflow` | `g03_airflow` | Orquestador del pipeline | `8081:8080` |
| `dashboard` | `g03_dashboard` | Servicio Streamlit preparado | `8502:8501` |

---

## 🗄️ Base de Datos

El proyecto utiliza PostgreSQL como base de datos principal para almacenar los datos climáticos.

### Base de datos del warehouse

| Parámetro | Valor |
| --------- | ----- |
| Host desde Docker | `warehouse` |
| Host desde Windows | `localhost` |
| Puerto desde Docker | `5432` |
| Puerto desde Windows | `5435` |
| Base de datos | `weather_data` |
| Usuario | `admin` |
| Contraseña | `admin123` |

---

## 🧩 Esquemas Creados

El archivo `init.sql` crea tres esquemas:

```sql
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
```

| Esquema | Estado actual | Descripción |
| ------- | ------------- | ----------- |
| `bronze` | Implementado y validado | Datos crudos provenientes de Open-Meteo |
| `silver` | Implementado y validado | Datos limpios y normalizados a partir de Bronze |
| `gold` | Implementado y validado | Modelo dimensional y hechos analíticos para dashboard y análisis |

---

# 🥉 Capa Bronze

## Objetivo

La capa Bronze almacena la respuesta original de la API sin aplicar transformaciones.

Esto permite conservar el dato crudo y mantener trazabilidad sobre lo recibido en cada ejecución del pipeline.

---

## Tabla Bronze

```sql
bronze.raw_weather_data
```

```sql
CREATE TABLE IF NOT EXISTS bronze.raw_weather_data (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    raw_json JSONB NOT NULL,
    tiempo_extraccion TIMESTAMP NOT NULL
);
```

| Campo | Tipo | Descripción |
| ----- | ---- | ----------- |
| `id` | `SERIAL` | Identificador único |
| `ciudad` | `VARCHAR(100)` | Ciudad consultada |
| `raw_json` | `JSONB` | Respuesta completa de Open-Meteo |
| `tiempo_extraccion` | `TIMESTAMP` | Momento en que Airflow realizó la consulta |

---

## DAG Bronze

Archivo:

```text
dags/01-bronze/weather_bronze.py
```

Nombre del DAG:

```text
weather_bronze_pipeline
```

Frecuencia:

```text
@hourly
```

Owner:

```text
grupo03
```

### Flujo Bronze

1. Lee el archivo `coordenadas.json`.
2. Consulta la API Open-Meteo para cada ciudad.
3. Obtiene la respuesta en formato JSON.
4. Inserta el JSON completo en `bronze.raw_weather_data`.
5. Registra la ciudad y el momento de extracción.

---

# 🥈 Capa Silver

## Objetivo

La capa Silver transforma los datos crudos almacenados en Bronze en tablas limpias, normalizadas y más simples de consultar.

A diferencia de Bronze, donde se conserva el JSON completo, Silver extrae campos específicos del JSON y los organiza en columnas tipadas.

---

## DAG Silver

Archivo:

```text
dags/02-silver/weather_silver.py
```

Nombre del DAG:

```text
weather_silver_pipeline
```

Frecuencia:

```text
@hourly
```

Owner:

```text
grupo03
```

Tarea principal:

```text
orquestar_limpieza_silver
```

---

## Flujo Silver

El DAG `weather_silver_pipeline` realiza el siguiente proceso:

1. Se conecta a PostgreSQL usando la conexión `postgres_default`.
2. Lee registros desde `bronze.raw_weather_data`.
3. Recorre cada JSON crudo almacenado en Bronze.
4. Extrae información horaria desde la clave `hourly`.
5. Extrae información de pronóstico desde la clave `daily`.
6. Limpia registros incompletos mediante `dropna`.
7. Elimina duplicados por ciudad y fecha/hora.
8. Inserta datos procesados en tablas Silver.

---

## Tabla Silver: clima actual e histórico

```sql
silver.weather_current
```

Esta tabla contiene información climática horaria o actual consolidada.

```sql
CREATE TABLE IF NOT EXISTS silver.weather_current (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    latitude FLOAT,
    longitude FLOAT,
    time TIMESTAMP NOT NULL,
    temperature FLOAT NOT NULL,
    windspeed FLOAT,
    winddirection FLOAT,
    precipitation FLOAT,
    is_day INTEGER,
    weather_current INTEGER,
    timezone VARCHAR(100) NOT NULL,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ciudad, time)
);
```

| Campo | Tipo | Descripción |
| ----- | ---- | ----------- |
| `id` | `SERIAL` | Identificador único |
| `ciudad` | `VARCHAR(100)` | Ciudad consultada |
| `latitude` | `FLOAT` | Latitud |
| `longitude` | `FLOAT` | Longitud |
| `time` | `TIMESTAMP` | Fecha y hora del dato climático |
| `temperature` | `FLOAT` | Temperatura |
| `windspeed` | `FLOAT` | Velocidad del viento |
| `winddirection` | `FLOAT` | Dirección del viento |
| `precipitation` | `FLOAT` | Precipitación |
| `is_day` | `INTEGER` | Indicador de día o noche |
| `weather_current` | `INTEGER` | Código meteorológico |
| `timezone` | `VARCHAR(100)` | Zona horaria |
| `fecha_procesamiento` | `TIMESTAMP` | Fecha y hora de procesamiento en Silver |

La restricción:

```sql
UNIQUE (ciudad, time)
```

evita duplicados si se reprocesa información de la misma ciudad y hora.

---

## Tabla Silver: pronóstico

```sql
silver.weather_forecast
```

Esta tabla contiene información de pronóstico diario.

```sql
CREATE TABLE IF NOT EXISTS silver.weather_forecast (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    fecha_pronostico DATE NOT NULL,
    temp_min FLOAT NOT NULL,
    temp_max FLOAT NOT NULL,
    prob_lluvia FLOAT,
    weather_forecast INTEGER,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ciudad, fecha_pronostico)
);
```

| Campo | Tipo | Descripción |
| ----- | ---- | ----------- |
| `id` | `SERIAL` | Identificador único |
| `ciudad` | `VARCHAR(100)` | Ciudad |
| `fecha_pronostico` | `DATE` | Fecha del pronóstico |
| `temp_min` | `FLOAT` | Temperatura mínima |
| `temp_max` | `FLOAT` | Temperatura máxima |
| `prob_lluvia` | `FLOAT` | Probabilidad de lluvia |
| `weather_forecast` | `INTEGER` | Código meteorológico del pronóstico |
| `fecha_procesamiento` | `TIMESTAMP` | Fecha de procesamiento en Silver |

La restricción:

```sql
UNIQUE (ciudad, fecha_pronostico)
```

evita duplicados si se reprocesa el mismo pronóstico para una ciudad y fecha.

---

## Limpieza y Normalización en Silver

| Acción | Descripción |
| ------ | ----------- |
| Parseo de JSON | Se extraen campos desde `raw_json` |
| Separación de datos | Se separan datos horarios y pronóstico diario |
| Tipado | Se convierten fechas, números y enteros |
| Eliminación de nulos | Se descartan registros sin campos clave |
| Eliminación de duplicados | Se usa ciudad + fecha/hora como clave lógica |
| Carga incremental | Se consulta si el registro existe antes de insertar |

---

# 🥇 Capa Gold

## Objetivo

La capa Gold transforma los datos limpios de Silver en un modelo analítico preparado para consultas de negocio, métricas agregadas y consumo por dashboard.

A diferencia de Silver, donde se almacenan datos normalizados con granularidad horaria o diaria, Gold consolida la información en dimensiones y tablas de hechos. Esto permite analizar el clima por ciudad y fecha sin tener que recorrer directamente las tablas operativas de Silver.

---

## DAG Gold

Archivo:

```text
dags/03-gold/weather_gold.py
```

Nombre del DAG:

```text
weather_gold_pipeline
```

Frecuencia:

```text
@daily
```

Fecha de inicio:

```text
2025-01-01
```

Catchup:

```text
False
```

Librerías principales:

| Librería | Uso |
| -------- | --- |
| `airflow` | Definición y orquestación del DAG |
| `PythonOperator` | Ejecución de funciones Python dentro de Airflow |
| `psycopg2` | Conexión e inserción de datos en PostgreSQL |
| `datetime` | Definición de fecha inicial del DAG |

---

## Conexión utilizada por Gold

El DAG Gold se conecta directamente al warehouse PostgreSQL mediante la siguiente configuración:

```python
DB_CONFIG = "dbname=weather_data user=admin password=admin123 host=g03_warehouse port=5432"
```

Parámetros de conexión:

| Parámetro | Valor |
| --------- | ----- |
| Base de datos | `weather_data` |
| Usuario | `admin` |
| Contraseña | `admin123` |
| Host | `g03_warehouse` |
| Puerto | `5432` |

Esta conexión permite leer las tablas Silver y cargar los resultados procesados en el esquema Gold.

---

## Flujo Gold

El DAG `weather_gold_pipeline` ejecuta dos tareas principales:

```text
cargar_fact_clima_real >> cargar_fact_pronostico
```

Flujo completo:

1. Se conecta a la base de datos PostgreSQL del warehouse.
2. Lee información climática real desde `silver.weather_current`.
3. Agrupa los datos por ciudad y fecha.
4. Calcula métricas diarias agregadas.
5. Inserta los resultados en `gold.fact_clima_real`.
6. Lee información de pronóstico desde `silver.weather_forecast`.
7. Relaciona cada pronóstico con la dimensión de ciudad.
8. Inserta los resultados en `gold.fact_pronostico`.
9. Evita duplicados usando `ON CONFLICT DO NOTHING`.

---

## Normalización de ciudades

El DAG incluye una función auxiliar llamada:

```python
normalizar_ciudad(columna)
```

Esta función normaliza los nombres de ciudad antes de hacer los `JOIN` entre Silver y Gold.

La normalización aplica:

| Transformación | Objetivo |
| -------------- | -------- |
| `TRIM` | Eliminar espacios al inicio o al final |
| `UPPER` | Unificar mayúsculas y minúsculas |
| Reemplazo de tildes | Evitar diferencias entre nombres con y sin acentos |

Ejemplo de uso dentro del DAG:

```sql
JOIN gold.dim_ciudad c
  ON normalizar(w.ciudad) = normalizar(c.ciudad)
```

Esto permite que ciudades como `Bogotá` y `BOGOTA` puedan relacionarse correctamente.

---

## Tablas Gold utilizadas

La capa Gold trabaja con tablas dimensionales y tablas de hechos.

| Tabla | Tipo | Descripción |
| ----- | ---- | ----------- |
| `gold.dim_ciudad` | Dimensión | Contiene las ciudades disponibles para análisis |
| `gold.dim_tiempo` | Dimensión | Contiene fechas y atributos temporales |
| `gold.fact_clima_real` | Hecho | Contiene métricas reales agregadas por ciudad y día |
| `gold.fact_pronostico` | Hecho | Contiene pronósticos diarios por ciudad |

---

## `gold.dim_ciudad`

Dimensión utilizada para identificar cada ciudad mediante una clave interna.

Campos principales esperados:

| Campo | Descripción |
| ----- | ----------- |
| `id` | Identificador único de la ciudad |
| `ciudad` | Nombre de la ciudad |
| `pais` | País o región asociada |
| `latitud` | Latitud de la ciudad |
| `longitud` | Longitud de la ciudad |

Esta dimensión se utiliza en los `JOIN` del DAG Gold para asociar los registros climáticos de Silver con un `ciudad_id` analítico.

---

## `gold.dim_tiempo`

Dimensión temporal utilizada para analizar métricas por fecha.

Campos principales:

| Campo | Descripción |
| ----- | ----------- |
| `fecha` | Fecha calendario |
| `anio` | Año |
| `mes` | Mes |
| `dia` | Día |
| `dia_semana` | Día de la semana |

Esta tabla permite filtrar o agrupar métricas por distintos niveles temporales.

---

## `gold.fact_clima_real`

Tabla de hechos cargada por la tarea:

```text
cargar_fact_clima_real
```

Fuente de datos:

```text
silver.weather_current
```

Destino:

```text
gold.fact_clima_real
```

La tarea agrupa los registros horarios de Silver por ciudad y fecha para generar métricas diarias.

Columnas cargadas:

| Campo | Cálculo / Fuente | Descripción |
| ----- | ---------------- | ----------- |
| `fecha` | `DATE(w.time)` | Fecha del dato climático |
| `ciudad_id` | `gold.dim_ciudad.id` | Identificador de ciudad |
| `temp_promedio` | `AVG(w.temperature)` | Temperatura promedio diaria |
| `temp_max` | `MAX(w.temperature)` | Temperatura máxima diaria |
| `temp_min` | `MIN(w.temperature)` | Temperatura mínima diaria |
| `lluvia_acumulada` | `SUM(COALESCE(w.precipitation, 0))` | Precipitación acumulada diaria |
| `viento_promedio` | `AVG(w.windspeed)` | Velocidad promedio del viento |

Consulta base ejecutada por el DAG:

```sql
INSERT INTO gold.fact_clima_real (
    fecha,
    ciudad_id,
    temp_promedio,
    temp_max,
    temp_min,
    lluvia_acumulada,
    viento_promedio
)
SELECT
    DATE(w.time) AS fecha,
    c.id AS ciudad_id,
    AVG(w.temperature) AS temp_promedio,
    MAX(w.temperature) AS temp_max,
    MIN(w.temperature) AS temp_min,
    SUM(COALESCE(w.precipitation, 0)) AS lluvia_acumulada,
    AVG(w.windspeed) AS viento_promedio
FROM silver.weather_current w
JOIN gold.dim_ciudad c
  ON normalizar(w.ciudad) = normalizar(c.ciudad)
GROUP BY DATE(w.time), c.id
ON CONFLICT (fecha, ciudad_id) DO NOTHING;
```

La clave lógica de esta tabla es:

```text
fecha + ciudad_id
```

Esto permite tener un único registro diario por ciudad.

---

## `gold.fact_pronostico`

Tabla de hechos cargada por la tarea:

```text
cargar_fact_pronostico
```

Fuente de datos:

```text
silver.weather_forecast
```

Destino:

```text
gold.fact_pronostico
```

La tarea toma el pronóstico diario generado en Silver y lo adapta al modelo analítico Gold.

Columnas cargadas:

| Campo | Fuente | Descripción |
| ----- | ------ | ----------- |
| `fecha_pronostico` | `silver.weather_forecast.fecha_pronostico` | Fecha pronosticada |
| `ciudad_id` | `gold.dim_ciudad.id` | Identificador de ciudad |
| `temp_min_esperada` | `silver.weather_forecast.temp_min` | Temperatura mínima esperada |
| `temp_max_esperada` | `silver.weather_forecast.temp_max` | Temperatura máxima esperada |
| `prob_lluvia` | `silver.weather_forecast.prob_lluvia` | Probabilidad de lluvia |

Consulta base ejecutada por el DAG:

```sql
INSERT INTO gold.fact_pronostico (
    fecha_pronostico,
    ciudad_id,
    temp_min_esperada,
    temp_max_esperada,
    prob_lluvia
)
SELECT
    w.fecha_pronostico,
    c.id AS ciudad_id,
    w.temp_min,
    w.temp_max,
    w.prob_lluvia
FROM silver.weather_forecast w
JOIN gold.dim_ciudad c
  ON normalizar(w.ciudad) = normalizar(c.ciudad)
ON CONFLICT (fecha_pronostico, ciudad_id) DO NOTHING;
```

La clave lógica de esta tabla es:

```text
fecha_pronostico + ciudad_id
```

Esto permite tener un único registro de pronóstico por ciudad y fecha.

---

## Control de duplicados en Gold

Las dos cargas principales utilizan:

```sql
ON CONFLICT (...) DO NOTHING
```

Esto evita duplicar información si el DAG se ejecuta más de una vez sobre los mismos datos.

| Tabla | Clave usada para evitar duplicados |
| ----- | ---------------------------------- |
| `gold.fact_clima_real` | `fecha`, `ciudad_id` |
| `gold.fact_pronostico` | `fecha_pronostico`, `ciudad_id` |

Este comportamiento permite que la capa Gold pueda reprocesarse sin romper la consistencia de las tablas analíticas.

---

## Orden de ejecución de tareas

El DAG define la siguiente dependencia:

```python
task_clima >> task_pronostico
```

Esto significa que primero se ejecuta:

```text
cargar_fact_clima_real
```

y luego:

```text
cargar_fact_pronostico
```

La decisión permite cargar primero las métricas reales históricas y después los datos de pronóstico.

---

## Validación de Gold

Para validar la capa Gold se debe ejecutar el DAG:

```text
weather_gold_pipeline
```

Luego se pueden consultar las tablas desde PostgreSQL:

```bash
docker exec -it g03_warehouse psql -U admin -d weather_data
```

Consultas sugeridas:

```sql
SELECT COUNT(*)
FROM gold.dim_ciudad;
```

```sql
SELECT COUNT(*)
FROM gold.dim_tiempo;
```

```sql
SELECT COUNT(*)
FROM gold.fact_clima_real;
```

```sql
SELECT COUNT(*)
FROM gold.fact_pronostico;
```

Consultas de muestra:

```sql
SELECT
    f.fecha,
    c.ciudad,
    f.temp_promedio,
    f.temp_max,
    f.temp_min,
    f.lluvia_acumulada,
    f.viento_promedio
FROM gold.fact_clima_real f
JOIN gold.dim_ciudad c
  ON f.ciudad_id = c.id
ORDER BY f.fecha DESC, c.ciudad
LIMIT 10;
```

```sql
SELECT
    p.fecha_pronostico,
    c.ciudad,
    p.temp_min_esperada,
    p.temp_max_esperada,
    p.prob_lluvia
FROM gold.fact_pronostico p
JOIN gold.dim_ciudad c
  ON p.ciudad_id = c.id
ORDER BY p.fecha_pronostico DESC, c.ciudad
LIMIT 10;
```

---

## Estado funcional de Gold

La capa Gold se encuentra implementada como etapa analítica del pipeline.

El DAG `weather_gold_pipeline`:

- está definido en `dags/03-gold/weather_gold.py`;
- se ejecuta diariamente;
- lee datos procesados desde Silver;
- calcula métricas agregadas reales;
- transforma pronósticos diarios en hechos analíticos;
- relaciona los datos con la dimensión de ciudad;
- evita duplicados mediante `ON CONFLICT DO NOTHING`;
- deja la información lista para consumo por consultas SQL, dashboard o análisis.

Con esta etapa, el pipeline completa el recorrido Medallion:

```text
Bronze → Silver → Gold
```

---

# 🚀 Cómo Levantar el Proyecto Localmente

## 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
```

## 2. Posicionarse en la carpeta del grupo

```bash
cd TpFinal/grupos/G03
```

## 3. Levantar los servicios

```bash
docker compose up -d
```

La primera ejecución puede tardar algunos minutos porque Docker descarga las imágenes necesarias.

## 4. Verificar contenedores

```bash
docker ps
```

Se espera ver los siguientes contenedores:

```text
g03_warehouse
g03_airflow_db
g03_airflow
g03_dashboard
```

---

# 🌬️ Acceso a Airflow

Airflow queda disponible en:

```text
http://localhost:8081
```

Usuario:

```text
admin
```

En el entorno de testeo se creó o utilizó el usuario:

```text
Usuario: admin
Contraseña: admin
```

Si se ejecuta Airflow en modo `standalone` y se genera una contraseña automáticamente, puede consultarse con:

```bash
docker exec -it g03_airflow cat /opt/airflow/standalone_admin_password.txt
```

En caso de que ese archivo no exista, se puede crear un usuario administrador local con:

```bash
docker exec -it g03_airflow airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@example.com --password admin
```

---

# 🔌 Configuración de Conexión en Airflow

Los DAGs utilizan la conexión:

```text
postgres_default
```

Durante el testeo se verificó que esta conexión debe apuntar al servicio `warehouse`, que es el nombre del servicio PostgreSQL dentro de Docker Compose.

Configuración correcta:

| Campo | Valor |
| ----- | ----- |
| Connection Id | `postgres_default` |
| Connection Type | `Postgres` |
| Host | `warehouse` |
| Database / Schema | `weather_data` |
| Login | `admin` |
| Password | `admin123` |
| Port | `5432` |

Nota: se usa el puerto `5432` porque Airflow se conecta a PostgreSQL desde dentro de la red Docker. El puerto `5435` es para acceder desde Windows hacia el contenedor.

---

# 🧪 Testeo Realizado

El testeo se realizó localmente en Windows utilizando Docker Desktop y WSL2.

---

## 1. Levantamiento del stack

Comando ejecutado:

```bash
docker compose up -d
```

Resultado observado:

| Contenedor | Estado |
| ---------- | ------ |
| `g03_warehouse` | Healthy |
| `g03_airflow_db` | Healthy |
| `g03_airflow` | Running |
| `g03_dashboard` | Started |

Esto confirmó que los servicios definidos en Docker Compose levantaron correctamente.

---

## 2. Acceso a Airflow

Se accedió correctamente a:

```text
http://localhost:8081
```

Se verificó la existencia de los DAGs:

| DAG | Estado |
| --- | ------ |
| `weather_bronze_pipeline` | Visible en Airflow |
| `weather_silver_pipeline` | Visible en Airflow |
| `weather_gold_pipeline` | Visible en Airflow |

---

## 3. Configuración de conexión `postgres_default`

Durante el testeo se detectó que, al recrear los volúmenes con `docker compose down -v`, Airflow perdía la configuración local de conexión.

La conexión se configuró manualmente con:

```text
Host: warehouse
Database / Schema: weather_data
Login: admin
Password: admin123
Port: 5432
```

---

## 4. Validación Bronze

Se ejecutó el DAG:

```text
weather_bronze_pipeline
```

Luego se ingresó a PostgreSQL:

```bash
docker exec -it g03_warehouse psql -U admin -d weather_data
```

Consulta ejecutada:

```sql
SELECT COUNT(*)
FROM bronze.raw_weather_data;
```

Resultado obtenido:

```text
 count
-------
 8
```

Interpretación:

```text
Bronze cargó correctamente 8 registros, uno por cada ciudad configurada.
```

---

## 5. Validación Silver

Luego de validar Bronze, se ejecutó el DAG:

```text
weather_silver_pipeline
```

Se validaron las tablas Silver con las siguientes consultas:

```sql
SELECT COUNT(*)
FROM silver.weather_current;
```

Resultado obtenido:

```text
 count
-------
 8921
```

Consulta:

```sql
SELECT COUNT(*)
FROM silver.weather_forecast;
```

Resultado obtenido:

```text
 count
-------
 376
```

Interpretación:

```text
Silver procesó correctamente los datos crudos de Bronze.
La tabla weather_current contiene registros horarios/históricos normalizados.
La tabla weather_forecast contiene registros de pronóstico.
```

---

## 6. Consultas de muestra para Silver

```sql
SELECT ciudad, time, temperature, windspeed, precipitation
FROM silver.weather_current
ORDER BY time DESC
LIMIT 10;
```

```sql
SELECT ciudad, fecha_pronostico, temp_min, temp_max, prob_lluvia
FROM silver.weather_forecast
ORDER BY fecha_pronostico DESC
LIMIT 10;
```

---

## 7. Validación Gold

Se ejecutó el DAG:

```text
weather_gold_pipeline
```

El DAG Gold procesa los datos provenientes de Silver y carga las tablas analíticas del esquema `gold`.

Tablas validadas:

```sql
SELECT COUNT(*)
FROM gold.dim_ciudad;
```

```sql
SELECT COUNT(*)
FROM gold.dim_tiempo;
```

```sql
SELECT COUNT(*)
FROM gold.fact_clima_real;
```

```sql
SELECT COUNT(*)
FROM gold.fact_pronostico;
```

Estado real:

```text
La capa Gold se encuentra funcional. El DAG weather_gold_pipeline procesa las métricas analíticas e impacta correctamente los modelos dimensionales de hechos y dimensiones en PostgreSQL, quedando listos para el consumo del dashboard.
```

# 🛠️ Problemas Detectados y Soluciones

Durante el testeo se encontraron problemas de configuración en la conexión `postgres_default`.

---

## Problema 1: host incorrecto

Error observado en Airflow:

```text
could not translate host name "postgres" to address
```

Causa:

La conexión `postgres_default` intentaba conectarse a un host llamado `postgres`, pero en el `docker-compose.yml` el servicio de base de datos se llama `warehouse`.

Solución aplicada:

```text
Host: warehouse
```

---

## Problema 2: base de datos incorrecta

Error observado en Airflow:

```text
FATAL: database "airflow" does not exist
```

Causa:

La conexión `postgres_default` estaba intentando conectarse a la base de datos `airflow`, pero la base de datos del warehouse se llama `weather_data`.

Solución aplicada:

```text
Database / Schema: weather_data
```

---

## Problema 3: tablas Silver inexistentes luego de actualizar `init.sql`

Error observado en Airflow:

```text
psycopg2.errors.UndefinedTable: relation "silver.weather_current" does not exist
```

Causa:

`init.sql` se ejecuta automáticamente solo cuando PostgreSQL inicializa un volumen nuevo. Como el volumen local ya existía, las nuevas tablas Silver agregadas posteriormente no se habían creado.

Solución aplicada:

```bash
docker compose down -v
docker compose up -d
```

Luego se volvió a configurar la conexión `postgres_default`, se ejecutó Bronze y después Silver.

---

# 🧹 Reinicio Completo del Entorno

Para validar que el entorno puede recrearse desde cero:

```bash
docker compose down -v
```

Luego:

```bash
docker compose up -d
```

Después del reinicio completo, se debe revisar o volver a configurar en Airflow la conexión:

```text
postgres_default
```

con los datos indicados en la sección de conexión.

---

# 📌 Estado Actual del Proyecto

| Componente | Estado |
| ---------- | ------ |
| Docker Compose | Funcionando |
| PostgreSQL warehouse | Funcionando |
| PostgreSQL Airflow DB | Funcionando |
| Airflow | Funcionando |
| DAG Bronze | Implementado y validado |
| Tabla `bronze.raw_weather_data` | Creada y poblada |
| Inserción de datos Bronze | Validada, 8 filas |
| DAG Silver | Implementado y validado |
| Tabla `silver.weather_current` | Creada y poblada, 8921 filas |
| Tabla `silver.weather_forecast` | Creada y poblada, 376 filas |
| Tablas Gold | Definidas en `init.sql` |
| `weather_gold_pipeline` | Visible en Airflow |
| Dashboard | Estructura creada, pendiente de validación funcional |

---

# ✅ Resultado Final

Se logró implementar y validar las capas Bronze y Silver del pipeline.

El sistema:

- levanta correctamente con Docker Compose;
- inicializa PostgreSQL;
- crea los esquemas `bronze`, `silver` y `gold`;
- crea las tablas Bronze, Silver y Gold definidas en `init.sql`;
- ejecuta el DAG `weather_bronze_pipeline`;
- consulta la API Open-Meteo;
- almacena los datos crudos en formato `JSONB`;
- registra la fecha y hora de extracción;
- inserta 8 registros en `bronze.raw_weather_data`;
- ejecuta el DAG `weather_silver_pipeline`;
- procesa los datos crudos de Bronze;
- inserta 8921 registros en `silver.weather_current`;
- inserta 376 registros en `silver.weather_forecast`;
- ejecuta el DAG `weather_gold_pipeline`;
- consolida métricas reales en `gold.fact_clima_real`;
- consolida pronósticos en `gold.fact_pronostico`;
- deja disponible una capa Gold analítica para dashboard y consultas SQL.

---

# 📝 Conclusión

El proyecto implementa un pipeline funcional de datos climáticos basado en arquitectura Medallion.

La capa Bronze quedó implementada y validada, permitiendo almacenar snapshots crudos de la API Open-Meteo en PostgreSQL.

La capa Silver quedó implementada y validada, transformando los datos crudos en tablas limpias, normalizadas y preparadas para consultas estructuradas.

La capa Gold también quedó implementada como etapa analítica final. El DAG `weather_gold_pipeline` toma los datos procesados en Silver, los relaciona con las dimensiones del esquema `gold` y genera tablas de hechos con métricas reales y de pronóstico. Esto permite consultar información consolidada por ciudad y fecha sin depender directamente de las tablas operativas.

Con la incorporación de Gold, el pipeline completa el flujo:

```text
Bronze → Silver → Gold
```

El resultado final es una solución reproducible con Docker Compose, orquestada por Airflow y respaldada por PostgreSQL, capaz de ingerir datos climáticos, limpiarlos, normalizarlos y transformarlos en información analítica lista para dashboard, reportes o futuras visualizaciones.

Durante el testeo también se detectaron y corrigieron problemas reales de configuración en Airflow y PostgreSQL, dejando documentado el procedimiento necesario para reconstruir el entorno y ejecutar correctamente las tres capas del pipeline.