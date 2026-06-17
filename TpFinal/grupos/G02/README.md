# TP Final - Grupo 02: ARS Exchange Monitor

## Integrantes
* **Elian Chokler** (@elianchok)
* **Nicolas Borro** (@nborro137)
* **Franco Santonastaso** (@FranSanto7)
* **Hernan Paglione** (@hernanpaglione)
* **Francisco Spensieri** (@FranSpensieri)
* **Juan Ignacio Rodriguez** (@RodJuani)

---

## API elegida

| Propiedad | Detalle |
| :--- | :--- |
| **Nombre** | Open Exchange Rates |
| **URL** | [https://openexchangerates.org/api/latest.json](https://openexchangerates.org/api/latest.json) |
| **Autenticacion** | API Key gratuita |
| **Frecuencia de actualizacion** | Cada 1 hora (`@hourly`) |

> **Descripcion:** API de tipos de cambio que devuelve un snapshot con cotizaciones de multiples monedas respecto de una moneda base (`USD`). En este proyecto consumimos el endpoint `latest.json`, que provee un timestamp Unix, la moneda base y un objeto anidado `rates` con pares `codigo_moneda -> cotizacion`.

---

## Modelo de datos (Arquitectura Medallion)

### Capa Bronze
Se encarga de la ingesta directa de la API conservando el JSON original sin desanidar junto a metadatos de auditoria para asegurar la trazabilidad como fuente de verdad. El DAG `01_bronze_exchange_rates` corre cada hora, calcula un `payload_hash` del JSON serializado y aplica `ON CONFLICT DO NOTHING` para evitar duplicados.

**Estructura de `bronze.exchange_rates_raw`:**

```sql
- id (SERIAL PRIMARY KEY)
- ingested_at (TIMESTAMP)
- source (VARCHAR)
- base_currency (VARCHAR)
- api_timestamp (BIGINT)
- raw_json (JSONB)
- rates (JSONB)
- disclaimer (TEXT)
- license (TEXT)
- payload_hash (VARCHAR UNIQUE)
```

### Capa Silver
Aplica limpieza, tipado y normalizacion. El DAG `02_silver_exchange_rates` desanida `rates` usando `jsonb_each_text` de Postgres, dejando una fila por moneda por snapshot.

**Transformaciones aplicadas:**

* Parseo del JSON anidado y estructuracion tabular.
* Conversion de timestamps crudos a formato legible (`clear_ts`).
* Normalizacion de cadenas (`base_currency` y `currency_code` con `TRIM` + `UPPER`).
* Validacion de consistencia (sin nulos y sin `exchange_rate <= 0`).
* Deduplicacion estricta con `UNIQUE (api_timestamp, currency_code)`.

**Estructura de `silver.exchange_rates`:**

```sql
- id (SERIAL PRIMARY KEY)
- clear_ts (TIMESTAMP)
- api_timestamp (BIGINT)
- base_currency (VARCHAR)
- currency_code (VARCHAR)
- exchange_rate (NUMERIC)
- ingested_at (TIMESTAMP)
- bronze_raw_id (INTEGER)
- source_payload_hash (VARCHAR)
```

### Capa Gold
Esta orientada al analisis del comportamiento del peso argentino (`ARS`) frente al resto de las monedas disponibles. Como la API cotiza de forma nativa contra `USD`, el proyecto deriva tipos de cambio cruzados contra ARS.

**Tablas del esquema Gold:**

* `gold.dim_time`: dimension temporal con desagregacion por fecha y hora.
* `gold.dim_currency`: dimension de monedas con vigencia de registros.
* `gold.fact_ars_exchange_rates`: tabla de hechos con equivalencias cruzadas y variacion porcentual contra el snapshot anterior.

**Metricas principales visualizadas en el dashboard:**

* Ultimo snapshot disponible.
* Cantidad de monedas disponibles.
* Valor de `1 USD` en `ARS`.
* Valor de `1 EUR` en `ARS`.
* Top 5 de monedas mas caras en ARS.
* Ranking de monedas con mayor variacion relativa.
* Alertas por variacion porcentual configurable.
* Comparacion historica de monedas seleccionadas.

> **Pregunta de negocio del dashboard:**
> ?Cuantos pesos argentinos se necesitan para comprar 1 unidad de cada moneda y cuales muestran mayor variacion relativa entre snapshots de la API?

---

## Dashboard

El dashboard esta implementado con Streamlit y se divide en dos secciones de navegacion:

* **Inicio**: portada del proyecto y contexto funcional.
* **Dashboard**: visualizacion de metricas, rankings, alertas, tabla general y comparacion historica.

**Detalles de implementacion actuales:**

* Los nombres de monedas se muestran en espanol, no como codigos ISO, usando `Babel` con fallback manual para algunos casos frecuentes.
* El grafico de monedas mas caras muestra un **top 5** fijo.
* El grafico de variacion muestra porcentajes con un maximo de **2 decimales**.
* El filtro lateral disponible actualmente es el umbral de alertas por variacion.

---

## Como levantar el stack

El stack se levanta con Docker Compose. El servicio de Airflow instala las dependencias listadas en `requirements.txt` al iniciar, y el dashboard se construye desde `dashboard/`.

```bash
cd TpFinal/grupos/G02
docker compose up -d --build
```

Si solo queres reconstruir el dashboard luego de cambios en Streamlit:

```bash
docker compose up -d --build dashboard
```

### Accesos esperados

* **Airflow UI:** http://localhost:8080
* **Streamlit Dashboard:** http://localhost:8501
* **PostgreSQL Warehouse:** `localhost:5432` (base `exchange`)

---

## Estructura del proyecto

La estructura actual relevante del grupo es:

```text
TpFinal/grupos/G02/
|-- README.md                # Documentacion del proyecto
|-- .env                     # Variables de entorno usadas por Docker Compose
|-- .env.example             # Plantilla de referencia de variables
|-- docker-compose.yml       # Orquestacion de servicios
|-- init.sql                 # Inicializacion de esquemas en PostgreSQL
|-- requirements.txt         # Dependencias Python para Airflow
|-- dags/
|   |-- 01-bronze/
|   |   `-- dag_exchange_bronze.py
|   |-- 02-silver/
|   |   `-- dag_exchange_silver.py
|   `-- 03-gold/
|       `-- dag_exchange_gold.py
`-- dashboard/
    |-- Dockerfile           # Imagen del dashboard
    |-- requirements.txt     # Dependencias de Streamlit/Plotly/SQLAlchemy/Babel
    |-- app.py               # Entrypoint con navegacion Streamlit
    |-- home_page.py         # Pagina Inicio
    |-- dashboard_page.py    # Pagina principal del dashboard
    `-- db.py                # Conexion y queries al warehouse
```

---

## Notas

* La carpeta `dashboard/pages/` ya no contiene la implementacion principal del dashboard; la navegacion actual usa `app.py`, `home_page.py` y `dashboard_page.py`.
* Si cambias codigo del dashboard, recorda reconstruir la imagen para ver los cambios en Docker.
