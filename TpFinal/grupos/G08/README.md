# TP Final - G08 - Open-Meteo

## Integrantes

- Tiziano Stacchino
- Elias Romero
- Mariano Fernandez
- Martin Bustamante

## API elegida

- **Nombre**: Open-Meteo
- **URL**: https://open-meteo.com/
- **Descripcion**: API publica de clima que permite consultar condiciones actuales y pronosticos meteorologicos por coordenadas geograficas.
- **Auth**: Sin autenticacion.
- **Refresh**: Cada hora, segun la frecuencia sugerida para el TP.

## Estado del proyecto

Este README inicial se agrega para registrar el comienzo del trabajo del grupo G08.

La idea del proyecto es construir un pipeline de datos end-to-end usando Open-Meteo como fuente publica, siguiendo la arquitectura medallion:

```text
Open-Meteo API -> Bronze -> Silver -> Gold -> Dashboard Streamlit
```

## Modelo de datos propuesto

### Bronze

El DAG `g08_openmeteo_bronze` consulta Open-Meteo cada hora para Buenos Aires, Cordoba y Mendoza. Guarda la respuesta cruda en `bronze.weather_raw` con ciudad, coordenadas, JSON original e instante de ingesta.

### Silver

El DAG `g08_openmeteo_silver` lee `bronze.weather_raw`, desanida el bloque `hourly` del JSON y guarda una tabla limpia en `silver.weather_hourly`. La tabla tiene una fila por ciudad y hora pronosticada, con temperatura, precipitacion, viento, fecha de pronostico e instante de ingesta.

### Gold

El DAG `g08_openmeteo_gold` lee `silver.weather_hourly` y agrega los datos por ciudad y dia en `gold.weather_daily_summary`. Gold aporta una vista analitica lista para consumo: resume temperatura promedio, maxima, minima, amplitud termica, precipitacion total, horas con lluvia, viento promedio y maximo.

Ademas clasifica cada dia con `weather_category`, calcula un `outdoor_score` de 0 a 100 y genera una `outdoor_recommendation`. Esto diferencia Gold de Silver: Silver guarda datos horarios limpios; Gold responde preguntas de analisis y dashboard, por ejemplo si un dia es recomendable para actividades al aire libre.

## Dashboard

El dashboard de Streamlit consumira tablas Gold y mostrara indicadores como temperatura actual, maxima y minima pronosticada, lluvia acumulada, comparacion entre ciudades y alertas por condiciones climaticas extremas.

## Como levantar el stack

```bash
cd TpFinal/grupos/G08
cp .env.example .env
docker compose up -d --build
```

## Accesos

- Airflow UI: http://localhost:8080
- Dashboard Streamlit: http://localhost:8501
- PostgreSQL warehouse: `localhost:5433`

## Conexion desde DBeaver

Crear una conexion PostgreSQL con estos valores:

- Host: `localhost`
- Port: `5433`
- Database: `TpFinal`
- Username: `admin`
- Password: `admin`

Importante: `TpFinal` es el nombre de la base de datos, no el usuario. Si se usa `TpFinal` como username, Postgres rechaza la conexion porque ese rol no existe.

Los schemas `bronze`, `silver` y `gold` se crean dentro de la base `TpFinal`. Si en DBeaver se conecta a la base `postgres`, es normal ver solamente `public`.



## Infraestructura

Esta etapa deja creada la infraestructura base del TP:

- Docker Compose con Airflow, PostgreSQL para metadatos, PostgreSQL para el data warehouse y Streamlit.
- Schemas `bronze`, `silver` y `gold` creados automaticamente por `init.sql`.
- Carpetas de DAGs separadas por capa medallion.
- Dashboard placeholder sin graficos reales.

La logica real de Open-Meteo, Bronze, Silver, Gold y visualizaciones se implementara en proximos commits.
