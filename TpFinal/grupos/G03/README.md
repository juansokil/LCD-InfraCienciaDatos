# 🌦️ TP Final - Grupo 03

## Infraestructura para Ciencia de Datos - UNSAM

---

## 👥 Integrantes

| Integrante          | Usuario GitHub  |
| -------------       | --------------- |
| Martina Lopez       | @martinalopez12 |
| Alejandro Rodriguez | @AleRC99        |
| Sofia Trayer        | @treyersofia    |
| Nadia Janulik       | @NayJanu        |
| Salvador D'Angelo   | @salvi-1005     |

---

## 📌 Descripción General

Este proyecto implementa un pipeline de ingesta de datos climáticos utilizando la API pública **Open-Meteo** como fuente de información.

La solución utiliza **Apache Airflow** para orquestar la extracción de datos y **PostgreSQL** como base de datos de almacenamiento. El entorno se ejecuta mediante **Docker Compose**, permitiendo levantar los servicios necesarios de forma reproducible.

Para esta entrega se implementó la **Capa Bronze** de una arquitectura Medallion. Esta capa almacena los datos crudos obtenidos desde la API, conservando la respuesta original en formato `JSONB` junto con metadatos de auditoría.

---

## 🎯 Objetivo

El objetivo principal es construir una primera etapa funcional de un pipeline de datos que permita:

* Extraer información climática desde una API pública.
* Automatizar la ingesta mediante Airflow.
* Almacenar snapshots crudos en PostgreSQL.
* Guardar los datos en una capa Bronze.
* Mantener trazabilidad mediante fecha y hora de extracción.
* Dejar preparada la estructura para futuras capas Silver y Gold.

---

## 🏗️ Arquitectura Implementada

```text
Open-Meteo API
       │
       ▼
Apache Airflow
       │
       ▼
PostgreSQL
Esquema Bronze
```

El flujo implementado corresponde a la primera etapa de la arquitectura Medallion:

```text
Bronze: datos crudos provenientes de la API
Silver: estructura creada para futuras transformaciones
Gold: estructura creada para futuros modelos analíticos
```

En el estado actual del proyecto, la capa funcional y testeada es **Bronze**.

---

## 🛠️ Tecnologías Utilizadas

| Componente                | Tecnología                               |
| ------------------------- | ---------------------------------------- |
| Lenguaje                  | Python                                   |
| Orquestador               | Apache Airflow                           |
| Base de datos             | PostgreSQL                               |
| Containerización          | Docker Compose                           |
| Fuente de datos           | Open-Meteo API                           |
| Formato de almacenamiento | JSONB                                    |
| Dashboard                 | Streamlit, preparado para futuras etapas |

---

## 🌎 API Utilizada

### Open-Meteo

La API seleccionada fue **Open-Meteo**, una API pública que permite obtener información meteorológica a partir de coordenadas geográficas.

```text
https://api.open-meteo.com/v1/forecast
```

### Características

* No requiere autenticación.
* Devuelve datos en formato JSON.
* Permite consultar datos climáticos por latitud y longitud.
* Es adecuada para ingestas periódicas.

---

## 🏙️ Ciudades Configuradas

Las ciudades se encuentran definidas en el archivo:

```text
coordenadas.json
```

Ciudades incluidas:

| Ciudad           | País / Región |
| ---------------- | ------------- |
| Buenos Aires     | Argentina     |
| Madrid           | España        |
| Ciudad de México | México        |
| Bogotá           | Colombia      |
| Santiago         | Chile         |
| Lima             | Perú          |
| Barcelona        | España        |
| Berlín           | Alemania      |

---

## 🌡️ Variables Climáticas Seleccionadas

El archivo `coordenadas.json` define las siguientes variables climáticas:

| Variable               | Descripción                     |
| ---------------------- | ------------------------------- |
| `temperature_2m`       | Temperatura del aire a 2 metros |
| `relative_humidity_2m` | Humedad relativa                |
| `wind_speed_10m`       | Velocidad del viento            |
| `precipitation`        | Precipitación                   |
| `weather_code`         | Código meteorológico            |

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
│   │
│   └── 03-gold/
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

| Archivo                            | Descripción                                                             |
| ---------------------------------- | ----------------------------------------------------------------------- |
| `docker-compose.yml`               | Define los servicios Docker del proyecto                                |
| `init.sql`                         | Crea los esquemas `bronze`, `silver`, `gold` y la tabla Bronze          |
| `coordenadas.json`                 | Contiene ciudades, coordenadas y variables climáticas                   |
| `dags/01-bronze/weather_bronze.py` | DAG principal de ingesta Bronze                                         |
| `README.md`                        | Documentación del proyecto y del testeo                                 |
| `stack/clima-api/app/clima.py`     | Prueba independiente de consulta a Open-Meteo e inserción en PostgreSQL |
| `stack/dashboard/`                 | Estructura preparada para dashboard                                     |

---

## 🐳 Servicios Docker

El archivo `docker-compose.yml` levanta cuatro servicios:

| Servicio     | Contenedor       | Función                           | Puerto      |
| ------------ | ---------------- | --------------------------------- | ----------- |
| `warehouse`  | `g03_warehouse`  | PostgreSQL principal del proyecto | `5435:5432` |
| `airflow_db` | `g03_airflow_db` | Base de datos interna de Airflow  | Interno     |
| `airflow`    | `g03_airflow`    | Orquestador del pipeline          | `8081:8080` |
| `dashboard`  | `g03_dashboard`  | Servicio Streamlit preparado      | `8502:8501` |

---

## 🗄️ Base de Datos

El proyecto utiliza PostgreSQL como base de datos principal para almacenar los datos climáticos.

### Base de datos del warehouse

| Parámetro            | Valor          |
| -------------------- | -------------- |
| Host desde Docker    | `warehouse`    |
| Host desde Windows   | `localhost`    |
| Puerto desde Docker  | `5432`         |
| Puerto desde Windows | `5435`         |
| Base de datos        | `weather_data` |
| Usuario              | `admin`        |
| Contraseña           | `admin123`     |

---

## 🧩 Esquemas Creados

El archivo `init.sql` crea tres esquemas:

```sql
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
```

| Esquema  | Estado actual | Descripción                                 |
| -------- | ------------- | ------------------------------------------- |
| `bronze` | Implementado  | Datos crudos provenientes de Open-Meteo     |
| `silver` | Preparado     | Pendiente para futuras transformaciones     |
| `gold`   | Preparado     | Pendiente para futuras métricas o dashboard |

---

## 🥉 Capa Bronze

La capa Bronze almacena la respuesta original de la API sin aplicar transformaciones.

### Tabla principal

```sql
bronze.raw_weather_data
```

### Estructura

```sql
CREATE TABLE IF NOT EXISTS bronze.raw_weather_data (
    id SERIAL PRIMARY KEY,
    ciudad VARCHAR(100) NOT NULL,
    raw_json JSONB NOT NULL,
    tiempo_extraccion TIMESTAMP NOT NULL
);
```

### Campos

| Campo               | Tipo           | Descripción                      |
| ------------------- | -------------- | -------------------------------- |
| `id`                | `SERIAL`       | Identificador único              |
| `ciudad`            | `VARCHAR(100)` | Ciudad consultada                |
| `raw_json`          | `JSONB`        | Respuesta completa de Open-Meteo |
| `tiempo_extraccion` | `TIMESTAMP`    | Fecha y hora de extracción       |

---

## 🔄 DAG Implementado

El DAG principal se encuentra en:

```text
dags/01-bronze/weather_bronze.py
```

Nombre del DAG:

```text
weather_bronze_pipeline
```

Frecuencia de ejecución:

```text
@hourly
```

Owner:

```text
grupo03
```

---

## ⚙️ Flujo del DAG

El DAG contiene dos tareas principales.

### 1. `cargar_coordenadas`

Esta tarea lee el archivo:

```text
/opt/airflow/coordenadas.json
```

El archivo se monta desde Docker mediante el volumen definido en `docker-compose.yml`.

La tarea obtiene:

* lista de ciudades;
* latitud;
* longitud;
* variables climáticas a consultar.

---

### 2. `extraer_e_ingresar_bronze`

Esta tarea realiza la ingesta principal.

Para cada ciudad:

1. Construye los parámetros de consulta.
2. Consulta la API Open-Meteo.
3. Obtiene la respuesta en formato JSON.
4. Inserta la respuesta completa en la tabla `bronze.raw_weather_data`.
5. Registra la fecha y hora de extracción.

---

## 🚀 Cómo Levantar el Proyecto Localmente

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
```

### 2. Posicionarse en la carpeta del grupo

```bash
cd TpFinal/grupos/G03
```

### 3. Levantar los servicios

```bash
docker compose up -d
```

La primera ejecución puede tardar algunos minutos porque Docker descarga las imágenes necesarias.

### 4. Verificar contenedores

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

## 🌬️ Acceso a Airflow

Airflow queda disponible en:

```text
http://localhost:8081
```

Usuario:

```text
admin
```

La contraseña se obtiene ejecutando:

```bash
docker exec -it g03_airflow cat /opt/airflow/standalone_admin_password.txt
```

Luego se ingresa a Airflow con:

```text
Usuario: admin
Contraseña: la generada por el comando anterior
```

---

## 🔌 Configuración de Conexión en Airflow

El DAG utiliza la conexión:

```text
postgres_default
```

Durante el testeo se verificó que esta conexión debe apuntar al servicio `warehouse`, que es el nombre del servicio PostgreSQL dentro de Docker Compose.

Configuración correcta:

| Campo           | Valor              |
| --------------- | ------------------ |
| Connection Id   | `postgres_default` |
| Connection Type | `Postgres`         |
| Host            | `warehouse`        |
| Schema          | `weather_data`     |
| Login           | `admin`            |
| Password        | `admin123`         |
| Port            | `5432`             |

Nota: se usa el puerto `5432` porque Airflow se conecta a PostgreSQL desde dentro de la red Docker. El puerto `5435` es para acceder desde Windows hacia el contenedor.

---

## 🧪 Testeo Realizado

El testeo se realizó localmente en Windows utilizando Docker Desktop y WSL2.

### 1. Levantamiento del stack

Comando ejecutado:

```bash
docker compose up -d
```

Resultado observado:

| Contenedor       | Estado  |
| ---------------- | ------- |
| `g03_warehouse`  | Healthy |
| `g03_airflow_db` | Healthy |
| `g03_airflow`    | Running |
| `g03_dashboard`  | Started |

Esto confirmó que los servicios definidos en Docker Compose levantaron correctamente.

---

### 2. Acceso a Airflow

Se accedió correctamente a:

```text
http://localhost:8081
```

Se verificó la existencia del DAG:

```text
weather_bronze_pipeline
```

El DAG se encontraba activo.

---

### 3. Ejecución del DAG

Dentro de Airflow se observaron las tareas:

| Tarea                       | Resultado inicial |
| --------------------------- | ----------------- |
| `cargar_coordenadas`        | Success           |
| `extraer_e_ingresar_bronze` | Failed            |

La primera tarea ejecutaba correctamente, por lo que se validó que Airflow podía leer el archivo `coordenadas.json`.

La falla ocurría en la segunda tarea, durante la conexión a PostgreSQL.

---

## 🛠️ Problemas Detectados y Soluciones

Durante el testeo se encontraron problemas de configuración en la conexión `postgres_default`.

---

### Problema 1: host incorrecto

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

### Problema 2: base de datos incorrecta

Error observado en Airflow:

```text
FATAL: database "airflow" does not exist
```

Causa:

La conexión `postgres_default` estaba intentando conectarse a la base de datos `airflow`, pero la base de datos del warehouse se llama `weather_data`.

Solución aplicada:

```text
Schema: weather_data
```

---

## ✅ Validación Final de la Carga

Luego de corregir la conexión `postgres_default`, se ejecutó nuevamente el DAG desde Airflow.

Para validar la carga en PostgreSQL se ingresó al contenedor del warehouse:

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

Esto confirma que se insertaron 8 registros, uno por cada ciudad configurada en `coordenadas.json`.

---

## 🔍 Consulta de Validación General

Consulta solicitada para verificar la capa Bronze:

```sql
SELECT *
FROM bronze.raw_weather_data;
```

Aspectos a verificar:

| Validación                                              | Resultado esperado |
| ------------------------------------------------------- | ------------------ |
| Existen filas                                           | Sí                 |
| `ciudad` contiene nombres de ciudades                   | Sí                 |
| `raw_json` contiene la respuesta completa de Open-Meteo | Sí                 |
| `tiempo_extraccion` contiene fecha y hora de carga      | Sí                 |

---

## 🧹 Reinicio Completo del Entorno

Para validar que el entorno puede recrearse desde cero:

```bash
docker compose down -v
```

Luego:

```bash
docker compose up -d
```

Este proceso elimina contenedores y volúmenes, y permite verificar nuevamente la creación automática de esquemas y tablas.

---

## 📌 Estado Actual del Proyecto

| Componente                      | Estado                                         |
| ------------------------------- | ---------------------------------------------- |
| Docker Compose                  | Funcionando                                    |
| PostgreSQL warehouse            | Funcionando                                    |
| PostgreSQL Airflow DB           | Funcionando                                    |
| Airflow                         | Funcionando                                    |
| DAG Bronze                      | Funcionando                                    |
| Tabla `bronze.raw_weather_data` | Creada                                         |
| Inserción de datos Bronze       | Validada                                       |
| Silver                          | Estructura creada, pendiente de implementación |
| Gold                            | Estructura creada, pendiente de implementación |
| Dashboard                       | Estructura creada, pendiente de integración    |

---

## ✅ Resultado Final

Se logró implementar y validar la capa Bronze del pipeline.

El sistema:

* levanta correctamente con Docker Compose;
* inicializa PostgreSQL;
* crea los esquemas `bronze`, `silver` y `gold`;
* crea la tabla `bronze.raw_weather_data`;
* ejecuta el DAG `weather_bronze_pipeline`;
* consulta la API Open-Meteo;
* almacena los datos crudos en formato `JSONB`;
* registra la fecha y hora de extracción;
* inserta 8 registros correspondientes a las ciudades configuradas.

---

## 📝 Conclusión

El proyecto implementa una primera etapa funcional de un pipeline de datos climáticos basado en arquitectura Medallion.

La capa Bronze quedó implementada y validada, permitiendo almacenar snapshots crudos de la API Open-Meteo en PostgreSQL. Esta base permite continuar el desarrollo de futuras capas Silver y Gold, donde se podrán limpiar, transformar y modelar los datos para análisis y visualización.

El testeo permitió además detectar y corregir problemas reales de configuración en Airflow, dejando documentado el procedimiento necesario para reproducir el entorno y llegar al mismo resultado.
