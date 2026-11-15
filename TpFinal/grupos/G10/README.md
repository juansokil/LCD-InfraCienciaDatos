# LogiWeather - TP Final G10

## Integrantes

- Enzo Herbas (@enzoherbas-cyber)
- Clara Wallach (@ClaraWallach)
- Martina Sposato (@martusposato)
- Matías Bermejo Fernández (@MatttiB)
- Claudia López de Santa Cirila (@claudiadesanta)

## 1. Descripción del proyecto

LogiWeather es una plataforma de apoyo a la toma de decisiones
para empresas de logística y reparto.

Su objetivo es anticipar condiciones meteorológicas que podrían
afectar las operaciones de distribución y la disponibilidad
de repartidores.

A partir de pronósticos obtenidos de Open-Meteo, el sistema
identifica riesgos por lluvia y calor, genera alertas
meteorológicas y recomienda incentivos adicionales para
las operaciones de reparto.

La solución implementa un pipeline de datos end-to-end
con arquitectura Medallion, orquestado mediante Apache Airflow,
almacenado en PostgreSQL y visualizado mediante Streamlit.

Todo el entorno se encuentra containerizado mediante
Docker Compose.

### Objetivos

- Anticipar condiciones meteorológicas desfavorables.
- Identificar ciudades y fechas que requieren atención.
- Clasificar los riesgos por lluvia y calor.
- Recomendar incentivos adicionales para repartidores.
- Facilitar la planificación operativa de los próximos siete días.

## 2. API elegida

- Nombre: Open-Meteo.
- Documentación: https://open-meteo.com/en/docs
- Endpoint: https://api.open-meteo.com/v1/forecast
- Autenticación: no requiere para el uso previsto.
- API key: no necesaria.
- Frecuencia de ingesta: cada una hora.
- Horizonte de pronóstico: siete días.

### Ciudades monitoreadas

| Ciudad | País | Zona horaria |
|---|---|---|
| New York | Estados Unidos | America/New_York |
| Miami | Estados Unidos | America/New_York |
| Chicago | Estados Unidos | America/Chicago |
| Houston | Estados Unidos | America/Chicago |
| Los Angeles | Estados Unidos | America/Los_Angeles |

Las ciudades y sus coordenadas se encuentran configuradas
en config/ciudades.json.

### Variables utilizadas

| Variable API | Descripción | Unidad |
|---|---|---|
| temperature_2m_max | Temperatura máxima diaria | °C |
| temperature_2m_min | Temperatura mínima diaria | °C |
| precipitation_probability_max | Probabilidad máxima de precipitación | % |
| precipitation_sum | Precipitación acumulada diaria | mm |
| weather_code | Condición meteorológica | Código WMO |


## 3. Arquitectura

    flowchart LR 
        A[Open-Meteo API] --> B[Bronze]
        B --> C[Silver]
        C --> D[Gold]
        D --> E[Streamlit]

        F[Airflow 3.1.5] -. Orquestación .-> B
        F -. Orquestación .-> C
        F -. Orquestación .-> D

        subgraph PostgreSQL Warehouse
            B
            C
            D
        end


El proyecto utiliza arquitectura Medallion:

- Bronze: almacenamiento de las respuestas originales
de la API en formato JSONB.
- Silver: transformación, normalización y validación
de los pronósticos mediante SQL.
- Gold: construcción del modelo dimensional y cálculo
de alertas e incentivos mediante SQL.

El dashboard consulta exclusivamente las tablas de Gold.

### Tecnologías

| Tecnología | Función |
|---|---|
| Docker Compose | Infraestructura y containerización |
| Apache Airflow 3.1.5 | Orquestación |
| PostgreSQL 17 | Almacenamiento y transformaciones |
| Python 3.11 | Ingesta y ejecución de tareas |
| Requests | Consumo de la API |
| Psycopg2 | Conexión con PostgreSQL |
| SQL | Transformaciones y reglas de negocio |
| Streamlit | Dashboard |
| Pandas | Preparación de datos para visualización |
| Plotly | Gráficos y mapa interactivo |

## 4. Modelo de datos

### Bronze

**Tabla:** `bronze.pronosticos_raw`

Almacena las respuestas originales de Open-Meteo
junto con los metadatos de cada ingesta.

| Campo | Descripción |
|---|---|
| id | Identificador del registro |
| ciudad_id | Identificador de ciudad |
| ciudad | Nombre de ciudad |
| latitud | Latitud solicitada |
| longitud | Longitud solicitada |
| fuente | Origen de los datos |
| run_id | Identificador de ejecución de Airflow |
| ingested_at | Fecha y hora de ingesta |
| payload | Respuesta original en JSONB |

La granularidad es una respuesta de la API por ciudad
y ejecución del DAG.

La combinación `ciudad_id` y `run_id` es única,
evitando duplicaciones dentro de una misma ejecución.

### Silver

**Tabla:** `silver.pronosticos_diarios`

Transforma los datos JSONB de Bronze en registros
estructurados mediante SQL.

Cada respuesta válida de Bronze genera siete
pronósticos diarios en Silver.

| Campo | Descripción |
|---|---|
| id | Identificador Silver |
| bronze_id | Identificador del registro de origen |
| ciudad_id | Identificador de ciudad |
| ciudad | Nombre de ciudad |
| fecha_consulta | Fecha de ingesta en UTC |
| fecha_pronostico | Fecha pronosticada |
| temperatura_max | Temperatura máxima |
| temperatura_min | Temperatura mínima |
| probabilidad_lluvia | Probabilidad de precipitación |
| precipitacion_mm | Precipitación acumulada |
| weather_code | Código meteorológico |
| ingested_at | Fecha y hora de ingesta |
| procesado_at | Fecha y hora de procesamiento |

Transformaciones y controles:

- Extracción de las variables desde JSONB.
- Conversión a tipos de datos estructurados.
- Validación de los siete días de pronóstico.
- Probabilidad de precipitación entre 0 y 100.
- Precipitación no negativa.
- Temperatura mínima menor o igual a la máxima.
- Prevención de duplicados mediante `bronze_id`
  y `fecha_pronostico`.

Todas las transformaciones se realizan mediante SQL.

### Gold

La capa Gold implementa un modelo dimensional
en estrella (Star Schema), compuesto por dos
dimensiones y una tabla de hechos.

    erDiagram

        DIM_CIUDAD ||--o{ FACT_ALERTAS_INCENTIVOS : ciudad_id
        DIM_FECHA ||--o{ FACT_ALERTAS_INCENTIVOS : fecha
    
        DIM_CIUDAD {
            varchar ciudad_id PK
            varchar ciudad
            float latitud
            float longitud
        }
    
        DIM_FECHA {
            date fecha PK
            integer anio
            integer mes
            integer dia
            integer dia_semana
        }
    
        FACT_ALERTAS_INCENTIVOS {
            varchar ciudad_id PK,FK
            date fecha_pronostico PK,FK
            numeric temperatura_max
            numeric temperatura_min
            integer probabilidad_lluvia
            numeric precipitacion_mm
            integer weather_code
            bigint bronze_id
            timestamptz ingested_at
            varchar nivel_alerta_lluvia
            numeric incentivo_lluvia
            varchar nivel_alerta_calor
            numeric incentivo_calor
            varchar nivel_alerta
            numeric incentivo_recomendado
        }


#### Dimensiones

- `gold.dim_ciudad`: identificadores, nombres
  y coordenadas de las ciudades.

- `gold.dim_fecha`: fechas y atributos de calendario,
  incluyendo año, mes, día y día de la semana.

#### Tabla de hechos

`gold.fact_alertas_incentivos`

Contiene las variables meteorológicas, niveles
de alerta e incentivos recomendados.

Su granularidad es una fila por ciudad y fecha
de pronóstico.

La clave primaria está compuesta por:

- `ciudad_id`
- `fecha_pronostico`

Para cada combinación se conserva la versión más
reciente del pronóstico.

Las actualizaciones se realizan mediante SQL,
utilizando operaciones de inserción y actualización
que evitan duplicaciones.

Gold conserva también pronósticos de fechas anteriores.

Estos registros representan pronósticos almacenados,
no mediciones meteorológicas efectivamente observadas.


## 5. Reglas de negocio

Las reglas se encuentran en:

`config/reglas_negocio.json`

Los umbrales y porcentajes son configurables
y se aplican mediante SQL en Gold.

### Alertas por lluvia

| Nivel | Probabilidad | Precipitación diaria | Incentivo |
|---|---:|---:|---:|
| SIN_ALERTA | No cumple los umbrales | — | 0 % |
| BAJA | >= 50 % | >= 10 mm | 25 % |
| MEDIA | >= 50 % | >= 20 mm | 50 % |
| ALTA | >= 75 % | >= 25 mm | 75 % |

Deben cumplirse ambas condiciones de cada regla.

Las condiciones se evalúan en orden descendente
de gravedad: ALTA, MEDIA y BAJA.

### Alertas por calor

| Nivel | Temperatura máxima | Incentivo |
|---|---|---:|
| SIN_ALERTA | Menor a 30 °C | 0 % |
| BAJA | Desde 30 °C y menor a 35 °C | 25 % |
| MEDIA | Desde 35 °C y menor a 40 °C | 50 % |
| ALTA | Desde 40 °C | 75 % |

### Incentivo general

Las alertas e incentivos por lluvia y calor
se calculan de forma independiente.

El nivel de alerta general corresponde al mayor
nivel de riesgo.

El incentivo general recomendado corresponde al
mayor porcentaje entre lluvia y calor.

Los incentivos no se acumulan.

Por ejemplo, un incentivo por lluvia del 75 %
y uno por calor del 50 % generan una recomendación
general del 75 %.


## 6. Orquestación

El pipeline está compuesto por tres DAGs de Airflow:

| DAG | Función | Programación |
|---|---|---|
| logiweather_bronze | Ingesta de Open-Meteo | Cada hora |
| logiweather_silver | Transformaciones SQL | Disparado por Bronze |
| logiweather_gold | Modelo dimensional y alertas | Disparado por Silver |

    flowchart TD
        A[Inicio del stack] --> B[Bootstrap]
        B --> C[Bronze]
        H[Scheduler cada hora] --> C
        C --> D[Silver]
        D --> E[Gold]
        E --> F[Dashboard Streamlit]


El servicio `airflow-bootstrap` espera a que Airflow
registre Bronze y solicita su primera ejecución
durante la inicialización.

Posteriormente, Bronze se ejecuta automáticamente
cada hora.

Al finalizar correctamente, Bronze dispara Silver
mediante `TriggerDagRunOperator`, y Silver dispara Gold.

No es necesario activar los DAGs manualmente.

Los esquemas de PostgreSQL se crean automáticamente
mediante `init.sql`.

Los DAGs cuentan con reintentos automáticos
y utilizan `catchup=False`.

## 7. Dashboard LogiWeather

El dashboard fue desarrollado mediante Streamlit
y Plotly.

Consulta exclusivamente el modelo dimensional Gold
mediante SQL.

Pandas se utiliza para preparar los resultados
de las consultas y facilitar su visualización,
sin reemplazar las transformaciones SQL
del pipeline.

### Indicadores principales

- Ciudades monitoreadas.
- Cantidad de pronósticos.
- Pronósticos con alerta.
- Incentivo máximo recomendado.

### Mapa operativo

Mapa interactivo de Estados Unidos con las ciudades
monitoreadas y su nivel de alerta.

Permite seleccionar una fecha y consultar las
condiciones meteorológicas y recomendaciones
de cada ciudad.

### Pronóstico por ciudad

Presenta tarjetas meteorológicas diarias,
temperaturas máximas y mínimas, probabilidad
de lluvia, precipitación acumulada e incentivos.

Incluye gráficos de evolución meteorológica
para el período seleccionado.

### Alertas e incentivos

Identifica las situaciones que requieren atención,
ordenadas por incentivo recomendado.

Permite consultar las alertas independientes
por lluvia y calor, las condiciones que las originan
y el incentivo general.

### Datos de Gold

Presenta los pronósticos almacenados en el
modelo dimensional.

Permite descargar los resultados filtrados
en formato CSV.

### Filtros

- Ciudad.
- Próximos siete días.
- Pronósticos anteriores.
- Todos los registros.
- Rango de fechas.

El dashboard muestra la última fecha y hora
de ingesta disponible y permite actualizar
los resultados.


## 8. Cómo levantar el stack

### Requisitos

- Docker Desktop o Docker Engine con Compose v2.
- Git.
- Conexión a internet.

No es necesario instalar Airflow, PostgreSQL
ni Python de manera local.

### Descargar el proyecto

```bash
git clone -b tpfinal/G10 https://github.com/juansokil/LCD-InfraCienciaDatos.git
cd LCD-InfraCienciaDatos/TpFinal/grupos/G10
```

El archivo `.env` se encuentra versionado con
credenciales de demostración, según la consigna.

No es necesario configurar una API key.

### Iniciar el stack

```bash
docker compose up
```

Alternativamente, para ejecutar en segundo plano:

```bash
docker compose up -d
```

La primera ejecución puede demorar varios minutos
debido a la descarga de imágenes, instalación
de dependencias e inicialización de servicios.

El pipeline comienza a ejecutarse automáticamente.

Una vez finalizadas las primeras ejecuciones de
Bronze, Silver y Gold, los datos estarán disponibles
en Streamlit.

### Accesos

| Servicio | URL | Credenciales |
|---|---|---|
| Airflow | http://localhost:8080 | admin / admin |
| Streamlit | http://localhost:8501 | No requiere |
| PostgreSQL | localhost:5432 | Definidas en .env |

La base de datos del Warehouse se denomina
`logiweather`.

### Verificar los servicios

```bash
docker compose ps -a
```

Los servicios permanentes deben encontrarse activos
y las bases de datos saludables.

Los servicios de inicialización
`airflow-init`, `airflow-permissions`
y `airflow-bootstrap` deben finalizar con código 0.

### Verificar la inicialización

```bash
docker compose logs --tail=50 airflow-bootstrap
```

### Verificar los datos

```bash
docker compose exec warehouse psql -U logiweather -d logiweather -c "SELECT (SELECT COUNT(1) FROM bronze.pronosticos_raw) AS bronze, (SELECT COUNT(1) FROM silver.pronosticos_diarios) AS silver, (SELECT COUNT(1) FROM gold.fact_alertas_incentivos) AS gold;"
```

Con una ingesta exitosa de las cinco ciudades,
se esperan:

| Capa | Registros |
|---|---:|
| Bronze | 5 |
| Silver | 35 |
| Gold | 35 |

Bronze y Silver conservan las distintas ingestas.
Gold conserva el pronóstico más reciente por
ciudad y fecha.

Los valores pueden variar según la cantidad
de ejecuciones y fechas acumuladas.

### Puertos ocupados

Si algún puerto se encuentra ocupado, pueden
modificarse las variables del puerto externo:

- POSTGRES_PORT
- AIRFLOW_PORT
- DASHBOARD_PORT

Ejemplo desde Git Bash:

```bash
POSTGRES_PORT=5433 AIRFLOW_PORT=8081 DASHBOARD_PORT=8502 docker compose up -d
```

Los puertos internos de los contenedores
no necesitan modificarse.

### Reconstruir imágenes

Cuando se modifican Dockerfiles o dependencias:

```bash
docker compose up -d --build
```

### Detener el entorno

```bash
docker compose down
```

Los datos se conservan en los volúmenes
de PostgreSQL.

**Advertencia:** `docker compose down -v`
elimina los volúmenes y los datos persistidos.

## 9. Estructura del proyecto

    G10/
    ├── README.md
    ├── docker-compose.yml
    ├── Dockerfile
    ├── requirements.txt
    ├── init.sql
    ├── .env
    ├── .env.example
    ├── .gitignore
    ├── config/
    │   ├── ciudades.json
    │   └── reglas_negocio.json
    ├── dags/
    │   ├── 01-bronze/
    │   │   └── openmeteo_bronze.py
    │   ├── 02-silver/
    │   │   └── openmeteo_silver.py
    │   └── 03-gold/
    │       └── openmeteo_gold.py
    └── dashboard/
        ├── Dockerfile
        ├── requirements.txt
        ├── db.py
        ├── app.py
        └── .streamlit/
            └── config.toml


## 10. Validaciones realizadas

- Ingesta de pronósticos para las cinco ciudades.
- Conservación de las respuestas originales.
- Transformación de siete registros diarios
  por cada respuesta Bronze.
- Prevención de duplicados.
- Actualización del modelo dimensional.
- Ejecución automática y encadenada de los DAGs.
- Cálculo de alertas independientes por lluvia y calor.
- Ausencia de registros pendientes de clasificación
  en las ejecuciones verificadas.
- Validación del incentivo general como máximo
  de los incentivos individuales.
- Conexión de Streamlit con Gold.
- Funcionamiento de filtros, mapa, gráficos,
  tarjetas y exportación CSV.

## 11. Alcance y mejoras futuras

El proyecto permite anticipar riesgos meteorológicos
y recomendar incentivos para las operaciones de reparto.


Como posibles mejoras futuras se propone:

- Incorporación de datos meteorológicos observados.
- Evaluación de la precisión de los pronósticos.
- Incorporación de viento, humedad y sensación térmica.
- Ampliación de las ciudades monitoreadas.
- Validación de las reglas con datos reales de operaciones.

## 12. Conclusión

LogiWeather demuestra cómo una solución de ingeniería
de datos puede transformar información meteorológica
de una API pública en recomendaciones de negocio.

Mediante Airflow, PostgreSQL, SQL, Docker y Streamlit,
se implementó un pipeline automatizado con arquitectura
Medallion y un dashboard orientado a la planificación
operativa.

La solución permite identificar riesgos, anticipar
situaciones desfavorables y facilitar la toma
de decisiones en empresas de logística y reparto.


