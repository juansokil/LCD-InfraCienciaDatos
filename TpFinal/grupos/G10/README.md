# TP Final - G10 - LogiWeather

Sistema de alertas climáticas e incentivos para repartidores de una empresa de logística en Estados Unidos.

## Integrantes

- Enzo Herbas (@enzoherbas-cyber)
- Clara Wallach (@ClaraWallach)
- Martina Sposato (@martusposato)
- Matías Bermejo Fernández (@MatttiB)
- Claudia López de Santa Cirila (@)

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

Tabla propuesta: silver.pronosticos_diarios

### Gold

`<modelo dimensional: fact_X + dim_Y, y que pregunta de negocio responde el dashboard>`

## Como levantar el stack

> ⚠️ **Esta API necesita una key.** Antes de levantar, completa `MI_API_KEY` en el
> `.env` con tu propia key — se saca gratis en `<link para pedirla>`. La que viene
> en el repo es un placeholder: no sirve.
>
> *(Si su API no necesita key, borren esta nota.)*

```bash
cd TpFinal/grupos/G<NN>/      # ej: cd TpFinal/grupos/G01/
docker compose up -d --build   # el .env ya viene en el repo
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8080 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` (user/pass en `.env`)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
