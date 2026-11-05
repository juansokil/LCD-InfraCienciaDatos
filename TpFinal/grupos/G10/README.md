# TP Final - G10 - LogiWeather

Sistema de alertas climáticas e incentivos para repartidores de una empresa de logística en Estados Unidos.

## Integrantes

- Enzo Herbas (@enzoherbas-cyber)
- Clara Wallach (@ClaraWallach)
- Martina Sposato (@martusposato)
- Matías Bermejo Fernández (@MatttiB)
- Claudia López de Santa Cirila (@claudiadesanta)

## API elegida

- **Nombre**: Open-Meteo (Weather Forecast API)
- **URL**: https://open-meteo.com/en/docs
- **Descripcion**:
API meteorológica que permite consultar pronósticos climáticos mediante coordenadas geográficas. Proporciona información sobre temperaturas, probabilidad de precipitaciones, cantidad de lluvia prevista y condiciones meteorológicas, entre otras variables.
Para este proyecto se consultarán pronósticos de los próximos 7 días correspondientes a cinco ciudades de Estados Unidos:
    - Nueva York
    - Miami
    - Chicago
    - Houston
    - Los Ángeles
      
El objetivo es identificar condiciones climáticas que puedan afectar las operaciones de una empresa de logística, generando alertas por lluvia y temperaturas máximas elevadas y recomendaciones de incentivos para los repartidores.

- **Auth**: Sin autenticación para el uso académico/no comercial.
- **API key**: No necesita.
- **Refresh**: Se propone ejecutar la ingesta automáticamente de manera diaria mediante Apache Airflow. La frecuencia definitiva quedará documentada al implementar los DAGs.

## Modelo de datos

El proyecto utilizará una arquitectura Medallion, organizada en tres capas dentro de PostgreSQL: Bronze, Silver y Gold.

### Bronze

La capa Bronze almacenará las respuestas originales de Open-Meteo, conservando los datos crudos sin aplicar transformaciones de negocio.

Tabla propuesta: bronze.pronosticos_raw

Columnas principales:
- id: identificador único de la ingesta.
- ciudad: nombre de la ciudad consultada.
- latitude: latitud de la ciudad.
- longitude: longitud de la ciudad.
- payload: respuesta JSON original de la API.
- ingested_at: fecha y hora de ingesta.
- source: API de origen.
- run_id: identificador de la ejecución del pipeline.
Se conservarán los distintos pronósticos obtenidos en cada ejecución para permitir trazabilidad y análisis de sus cambios.

### Silver

La capa Silver transformará los datos crudos en información estructurada y validada, lista para su análisis.

**Tabla propuesta: `silver.pronosticos_diarios`**

Columnas principales:

- `ciudad`: ciudad a la que corresponde el pronóstico.
- `fecha_pronostico`: fecha del día pronosticado.
- `fecha_consulta`: fecha y hora en que se obtuvo el pronóstico.
- `temperatura_max`: temperatura máxima prevista en °C.
- `temperatura_min`: temperatura mínima prevista en °C.
- `probabilidad_precipitacion`: probabilidad máxima diaria de precipitación en %.
- `precipitacion_mm`: precipitación total prevista en milímetros.
- `weather_code`: código de la condición meteorológica.

**Transformaciones previstas:**

- Extracción y normalización de los campos del JSON.
- Conversión y validación de tipos de datos.
- Normalización de fechas y zonas horarias.
- Control de valores nulos, rangos válidos y registros duplicados.
- Conservación de la fecha de consulta para distinguir versiones del pronóstico.
- Preparación de los datos para las reglas de negocio.

### Gold

La capa Gold contendrá la información analítica destinada al dashboard de logística.

**Modelo dimensional propuesto:**

- `gold.dim_ciudad`: información de las ciudades analizadas.
- `gold.dim_fecha`: calendario de fechas pronosticadas.
- `gold.fact_alertas_incentivos`: indicadores climáticos y recomendaciones de incentivos por ciudad y fecha.

**Indicadores previstos:**

- Probabilidad máxima diaria de precipitación.
- Cantidad de lluvia pronosticada.
- Temperatura máxima prevista.
- Nivel de alerta por lluvia.
- Nivel de alerta por temperatura.
- Bono adicional recomendado para los repartidores.
- Fecha y hora de actualización del pronóstico.

Las reglas para establecer los niveles de alerta y los porcentajes de los bonos serán definidas antes de implementar la lógica de negocio.

**Pregunta de negocio que responde el dashboard:**

¿En qué ciudades y fechas conviene ofrecer incentivos adicionales a los repartidores según el pronóstico de lluvia, y qué alertas por temperaturas elevadas deben considerarse para planificar las operaciones logísticas?

El dashboard se desarrollará en Streamlit y consumirá exclusivamente información de la capa Gold.

## Como levantar el stack

El proyecto utilizará Docker Compose para iniciar automáticamente los servicios necesarios: PostgreSQL, Apache Airflow y Streamlit.

Una vez implementada la infraestructura, el procedimiento previsto será:

```bash
cd TpFinal/grupos/G<NN>/
docker compose up -d --build
```

El stack deberá inicializar los esquemas de PostgreSQL y ejecutar automáticamente el pipeline Bronze → Silver → Gold, sin intervención manual.

**Accesos previstos:**

- Airflow UI: http://localhost:8080
- Dashboard (Gold): http://localhost:8501
- PostgreSQL: `localhost:5432` (credenciales configuradas mediante variables de entorno).

**Apagar:**

```bash
docker compose down
```

**Apagar y eliminar los volúmenes:**

```bash
docker compose down -v
```

**Nota:** La configuración Docker, las credenciales locales y el arranque automático se completarán y verificarán durante el desarrollo. Las contraseñas reales no se almacenarán en GitHub.

## Estructura del proyecto

La estructura inicial prevista es:

```text
G<NN>/
├── README.md
├── docker-compose.yml
├── Dockerfile
├── init.sql
├── requirements.txt
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
    ├── app.py
    ├── db.py
    └── pages/
        └── 1_Gold.py
```

