# TP Final - G05 - Pipeline Meteorológico

## Integrantes
- Román Sandoval (@romansandoval)
- Leonel Gimenez (@Leonel-Gimenez)
- Ignacio González Correia (@ignaciogcorreia)

## API elegida
- **Nombre**: Open-Meteo API
- **URL**: `https://api.open-meteo.com/v1/forecast`
- **Descripción**: API meteorológica Open Source que devuelve el estado actual del clima y pronósticos detallados. En este proyecto, extraemos las temperaturas máximas, mínimas y precipitaciones para 4 ciudades argentinas.
- **Auth**: Sin autenticación requerida.
- **Refresh**: Diario. El pipeline está orquestado en Airflow para ejecutarse una vez al día (`@daily`) y capturar el snapshot climático de la jornada.

## Modelo de datos

Para el procesamiento de los datos usamos Python y la librería `pandas`, lo que nos permite limpiar y transformar la información de manera sencilla antes de cargarla en la base de datos.

### Bronze

Se almacena el JSON crudo de cada llamada a la API de Open-Meteo. La idea de esta capa es usarla como fuente de verdad, conservando el dato original tal cual viene para poder rehacer las capas siguientes si es necesario.

- Se almacena el JSON completo sin modificaciones.
- Se agrega la columna `fecha_extraccion` para tener un registro de cuándo se hizo la consulta.

### Silver

Se aplican transformaciones de limpieza y normalización a los datos usando Pandas:

- Desarmado (parseo) del JSON que trajimos de Bronze.
- Tipado de datos: conversión de las fechas a formato `datetime` y las temperaturas a numérico (`float`).
- Limpieza de valores nulos.
- Deduplicación para asegurarnos de tener un solo registro válido por cada día.

### Gold

Se construirá un modelo orientado al análisis de negocio. En lugar de separar los datos en varias tablas, armamos una sola gran tabla consolidada (ABT) que hace más fácil y rápida la lectura para el dashboard.

- Tabla **`gold.clima_kpis`**:
  - Histórico de temperaturas máximas y mínimas.
  - Amplitud térmica calculada por día y ciudad.
  - Alertas climáticas (`Alerta Calor`, `Alerta Frío`, `Alerta Lluvia`).

La pregunta de negocio del dashboard es:

**¿Cómo evolucionan las temperaturas extremas a lo largo del tiempo, y qué días se disparan alertas climáticas en los distintos puntos de Argentina?**

## Cómo levantar el stack

```bash
cd TpFinal/grupos/G05/
docker compose up --build -d
```

Una vez levantado:
- **Airflow**: http://localhost:8080 (usuario: `admin`, contraseña: `admin`)
- **Dashboard**: http://localhost:8501

Los DAGs arrancan activos por default. Bronze corre `@daily` — para ver datos inmediatamente, triggerear los tres DAGs en orden desde Airflow: `01_bronze_clima` → `02_silver_clima` → `03_gold_clima`.