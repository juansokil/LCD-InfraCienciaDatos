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

Se guardaran respuestas crudas de la API de Open-Meteo para un conjunto de ciudades seleccionadas, junto con metadatos de auditoria como fecha de ingesta, ciudad, coordenadas y fuente.

### Silver

Se parsearan los JSON crudos, se tiparan fechas y variables meteorologicas, se normalizaran unidades y se separaran mediciones actuales de pronosticos diarios.

### Gold

Se construiran tablas analiticas para comparar clima entre ciudades, detectar alertas meteorologicas y alimentar el dashboard final.

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
