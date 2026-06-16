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

La implementacion del stack Docker, DAGs de Airflow y dashboard se agregara en los proximos commits.
