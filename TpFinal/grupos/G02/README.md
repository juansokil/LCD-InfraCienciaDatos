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

El DAG `01_bronze_exchange_rates` corre cada hora, consume `latest.json` y guarda una fila por snapshot real. Para evitar duplicados, calcula un `payload_hash` del JSON canonicamente serializado y hace `ON CONFLICT DO NOTHING`.

Estructura actual de `bronze.exchange_rates_raw`:

- `id`
- `ingested_at`
- `source`
- `base_currency`
- `api_timestamp`
- `raw_json`
- `rates`
- `disclaimer`
- `license`
- `payload_hash`

Bronze funcionara como fuente de verdad: preserva el snapshot original y permite rehacer Silver y Gold si cambia la logica de transformacion.

### Silver

Se aplicaran transformaciones de limpieza y normalizacion:

- parseo del JSON anidado de `rates`
- una fila por moneda por snapshot
- conversion de `timestamp` a `clear_ts` para leerlo mejor
- tipado estricto de timestamp, codigo de moneda y valor
- normalizacion de `base_currency` y `currency_code` con trim + uppercase
- deduplicacion por `api_timestamp` + `currency_code`
- validacion basica de valores nulos o cotizaciones no positivas
- trazabilidad hacia Bronze mediante el id de la fila fuente y el hash del payload

Estructura actual de `silver.exchange_rates`:

- `id`
- `clear_ts`
- `api_timestamp`
- `base_currency`
- `currency_code`
- `exchange_rate`
- `ingested_at`
- `bronze_raw_id`
- `source_payload_hash`

El DAG `02_silver_exchange_rates` desanida `rates` con `jsonb_each_text`, inserta una fila por moneda y usa `UNIQUE (api_timestamp, currency_code)` para evitar duplicados.

### Gold

Se construira un modelo orientado a analisis del peso argentino frente a todas las monedas disponibles en la API.

Tablas Gold:

- `gold.dim_currency`
- `gold.dim_time`
- `gold.fact_ars_exchange_rates`

La API entrega cotizaciones contra USD. Para calcular el valor de cada moneda expresado en pesos argentinos se usa:

```text
ARS por moneda = cotizacion_ARS / cotizacion_moneda
```

Metricas principales:

- tipo de cambio actual de ARS frente a cada moneda
- pesos argentinos necesarios para comprar 1 unidad de cada moneda
- unidades de cada moneda equivalentes a 1 peso argentino
- variacion porcentual contra el snapshot anterior
- ranking de monedas con mayor suba o baja relativa frente al ARS

La pregunta de negocio del dashboard sera:

**Cuantos pesos argentinos se necesitan para comprar 1 unidad de cada moneda y cuales muestran mayor variacion relativa entre snapshots?**

## Como levantar el stack

```bash
cd TpFinal/grupos/G02/
docker compose up -d --build
```

El proyecto incluye un `.env` versionado para que el stack pueda levantarse directamente al clonar el repo.

**Accesos esperados**:
- Airflow UI: `http://localhost:8080`
- Dashboard: `http://localhost:8501`
- Postgres: `localhost:5432`

## Estructura del proyecto

La estructura del grupo seguira el esqueleto pedido en [TpFinal/README.md](../../README.md):

```text
TpFinal/grupos/G02/
|-- README.md
|-- .env
|-- docker-compose.yml
|-- init.sql
|-- requirements.txt
|-- dags/
|   |-- 01-bronze/
|   |   `-- dag_exchange_bronze.py
|   |-- 02-silver/
|   |   `-- dag_exchange_silver.py
|   `-- 03-gold/
|       `-- dag_exchange_gold.py
`-- dashboard/
    |-- Dockerfile
    |-- requirements.txt
    |-- db.py
    |-- app.py
```
