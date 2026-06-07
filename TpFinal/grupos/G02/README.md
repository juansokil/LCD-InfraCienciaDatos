# TP Final - G02

## Integrantes

- Elian Chokler (@chokler-elian)
- Nicolas Borro (@nborro137)
- Franco Santonastaso (@FranSanto7)
- Hernan Paglione (@hernanpaglione)
- Francisco Spensieri (@FranSpensieri)
- Juan Ignacio Rodriguez (@RodJuani)

## API elegida

- **Nombre**: Open Exchange Rates
- **URL**: `https://openexchangerates.org/api/latest.json`
- **Descripcion**: API de tipos de cambio que devuelve un snapshot con cotizaciones de multiples monedas respecto de una moneda base. En este proyecto usaremos el endpoint `latest.json`, que devuelve un `timestamp` Unix, una moneda `base` y un objeto `rates` con pares `codigo_moneda -> cotizacion`.
- **Auth**: API key gratuita
- **Refresh**: cada hora

## Modelo de datos

### Bronze

Se guardara el JSON crudo de cada llamada a la API con metadatos de auditoria. El payload real tiene esta forma:

- `disclaimer`
- `license`
- `timestamp`
- `base`
- `rates` (objeto JSON anidado con una clave por moneda)

En Bronze la idea es conservar una fila por llamada a la API, sin desanidar todavia el objeto `rates`.

Columnas candidatas para Bronze:

- `ingested_at`
- `source`
- `base_currency`
- `api_timestamp_unix`
- `raw_payload`
- `disclaimer`
- `license`

Bronze funcionara como fuente de verdad: preserva el snapshot original y permite rehacer Silver y Gold si cambia la logica de transformacion.

### Silver

Se aplicaran transformaciones de limpieza y normalizacion:

- parseo del JSON anidado de `rates`
- una fila por moneda por snapshot
- conversion de `api_timestamp_unix` a `snapshot_ts`
- tipado estricto de timestamp, codigo de moneda y valor
- deduplicacion por `api_timestamp_unix` + `currency_code`
- validacion basica de valores nulos o cotizaciones no positivas

Propuesta de estructura Silver:

- `snapshot_ts`
- `api_timestamp_unix`
- `base_currency`
- `currency_code`
- `exchange_rate`
- `ingested_at`

### Gold

Se construira un modelo orientado a analisis de negocio:

- `gold.dim_currency`
- `gold.dim_time`
- `gold.fact_exchange_rate`

Posibles metricas / vistas Gold:

- evolucion temporal por moneda
- variacion porcentual entre snapshots
- ranking de monedas con mayor suba o baja relativa
- comparacion de monedas seleccionadas contra ARS
- analisis de tipo de cambio cruzado derivado entre monedas seleccionadas

La pregunta de negocio del dashboard sera:

**Como evolucionan distintas monedas a lo largo del tiempo y cuales muestran mayor variacion relativa entre snapshots?**

## Como levantar el stack

```bash
cd TpFinal/grupos/G02/
cp .env.example .env
docker compose up -d --build
```

**Accesos esperados**:
- Airflow UI: `http://localhost:8080`
- Dashboard: `http://localhost:8501`
- Postgres: `localhost:5432`

## Estructura del proyecto

La estructura del grupo seguira el esqueleto pedido en [TpFinal/README.md](../../README.md):

```text
TpFinal/grupos/G02/
|-- README.md
|-- docker-compose.yml
|-- Dockerfile
|-- init.sql
|-- requirements.txt
|-- dags/
|   |-- 01-bronze/
|   |-- 02-silver/
|   `-- 03-gold/
`-- dashboard/
    |-- app.py
    |-- db.py
    `-- pages/
```
