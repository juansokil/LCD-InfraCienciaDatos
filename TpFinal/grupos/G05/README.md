# TP Final - G05 - Pipeline Meteorológico

## Integrantes
- Román Sandoval (@romansandoval)
- Leonel Gimenez (@Leonel-Gimenez)
- Ignacio González Correia (@ignaciogcorreia)

## API elegida
- **Nombre**: Open-Meteo API
- **URL**: `https://api.open-meteo.com/v1/forecast`
- **Descripción**: API meteorológica Open Source que devuelve el estado actual del clima y pronósticos detallados. En este proyecto, extraemos la temperatura actual, las máximas y las mínimas de nuestra ciudad.
- **Auth**: Sin autenticación requerida.
- **Refresh**: Diario. El pipeline está orquestado en Airflow para ejecutarse una vez al día (`@daily`) y capturar el snapshot climático de la jornada.

## Modelo de datos

Para el procesamiento de los datos usamos Python y la librería `pandas`, lo que nos permite limpiar y transformar la información de manera sencilla antes de cargarla en la base de datos.

### Bronze

Se guardará el JSON crudo de cada llamada a la API de Open-Meteo. La idea de esta capa es usarla como fuente de verdad, conservando el dato original tal cual viene para poder rehacer las capas siguientes si es necesario.

- Se almacena el JSON completo sin modificaciones.
- Se agrega la columna `fecha_extraccion` para tener un registro de cuándo se hizo la consulta.

### Silver

Se aplicarán transformaciones de limpieza y normalización a los datos usando Pandas:

- Desarmado (parseo) del JSON que trajimos de Bronze.
- Tipado de datos: conversión de las fechas a formato `datetime` y las temperaturas a numérico (`float`).
- Limpieza de valores nulos.
- Deduplicación para asegurarnos de tener un solo registro válido por cada día.

### Gold

Se construirá un modelo orientado al análisis de negocio. En lugar de separar los datos en varias tablas, armamos una sola gran tabla consolidada (ABT) que hace más fácil y rápida la lectura para el dashboard.

- Tabla **`gold.abt_clima`**:
  - Histórico de temperaturas máximas y mínimas.
  - Métricas calculadas (como la amplitud térmica).
  - Alertas climáticas (`Alerta Calor`, `Alerta Frío`).

La pregunta de negocio del dashboard será:

**¿Cómo evolucionan las temperaturas extremas a lo largo del tiempo, y qué días se disparan alertas climáticas en los distintos puntos de Argentina?**

## Cómo levantar el stack

```bash
cd TpFinal/grupos/G05/
docker compose up -d