# TP Final - G02

## Integrantes

- Elian Chokler (@chokler-elian)
- Nicolás Borro (@nborro137)
- Franco Santonastaso (@FranSanto7)
- Hernan Paglione (@hernanpaglione)
- Francisco Spensieri (@FranSpensieri)
- Juan Ignacio Rodriguez (@RodJuani)



## API elegida

- **Nombre**: Open Exchange Rates
- **URL**: `https://openexchangerates.org/api`
- **Descripcion**: API de tipos de cambio que devuelve un snapshot con cotizaciones de multiples monedas respecto de USD.
- **Auth**: API key gratuita
- **Refresh**: cada hora

## Modelo de datos

### Bronze

Se guardara el JSON crudo de cada snapshot de cotizaciones con metadatos de auditoria:

- `ingested_at`
- `source`
- `base_currency`
- `api_timestamp`
- `raw_payload`

Ademas, se evaluará guardar una tabla bronze ya desanidada por moneda para facilitar la capa Silver.

### Silver

Se aplicarán transformaciones de limpieza y normalización:

- parseo del JSON anidado de `rates`
- una fila por moneda por snapshot
- tipado estricto de timestamp, codigo de moneda y valor
- deduplicacion por `api_timestamp` + `currency_code`
- validación basica de valores nulos o cotizaciones no positivas

### Gold

Se construira un modelo orientado a analisis de negocio:

- `gold.dim_currency`
- `gold.dim_time`
- `gold.fact_exchange_rate`

Posibles metricas / vistas Gold:

- evolucion temporal por moneda
- variacion porcentual entre snapshots
- ranking de monedas con mayor suba o baja relativa
- comparacion de monedas seleccionadas contra Peso Argentino

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
├── README.md
├── docker-compose.yml
├── Dockerfile
├── init.sql
├── requirements.txt
├── dags/
│   ├── 01-bronze/
│   ├── 02-silver/
│   └── 03-gold/
└── dashboard/
    ├── app.py
    ├── db.py
    └── pages/
```
