# TP Final - Grupo 02: ARS Exchange Monitor


## Integrantes
* **Elian Chokler** (@chokler-elian)
* **Nicolas Borro** (@nborro137)
* **Franco Santonastaso** (@FranSanto7)
* **Hernan Paglione** (@hernanpaglione)
* **Francisco Spensieri** (@FranSpensieri)
* **Juan Ignacio Rodriguez** (@RodJuani)


---


## API Elegida


| Propiedad | Detalle |
| :--- | :--- |
| **Nombre** | Open Exchange Rates |
| **URL** | [https://openexchangerates.org/api/latest.json](https://openexchangerates.org/api/latest.json) |
| **Autenticación** | API Key Gratuita |
| **Frecuencia de actualización** | Cada 1 hora (@hourly) |


> **Descripción:** API de tipos de cambio que devuelve un snapshot con cotizaciones de múltiples monedas respecto de una moneda base (USD). En este proyecto consumimos el endpoint latest.json, el cual provee un timestamp Unix, la moneda base y un objeto anidado rates con pares codigo_moneda -> cotizacion.


---


## Modelo de Datos (Arquitectura Medallion)


### Capa Bronze (Datos Crudos)
Se encarga de la ingesta directa de la API conservando el JSON original sin desanidar junto a metadatos de auditoría para asegurar la trazabilidad como fuente de verdad. El DAG `01_bronze_exchange_rates` corre cada hora, calcula un `payload_hash` del JSON canónicamente serializado y aplica un mecanismo de `ON CONFLICT DO NOTHING` para evitar duplicaciones.


**Estructura de la tabla bronze.exchange_rates_raw:**
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

### Capa Silver (Datos Limpios y Validados)


Aplica procesos de limpieza, tipado estricto y normalización de los datos de la capa anterior. El DAG `02_silver_exchange_rates` desanida el objeto *rates* utilizando la función nativa de Postgres *jsonb_each_text*, transformando la estructura a una fila por moneda por cada snapshot.


**Transformaciones aplicadas:**


* **Parseo** del JSON anidado y estructuración tabular.
* **Conversión** de timestamps crudos a formato legible (*clear_ts*).
* **Normalización** de cadenas de texto (*base_currency* y *currency_code* con *TRIM* + *UPPER*).
* **Validación relacional** de consistencia (filtros contra valores nulos o cotizaciones *exchange_rate* <= 0).
* **Deduplicación estricta** aplicando un índice compuesto *UNIQUE* (*api_timestamp*, *currency_code*).


**Estructura de la tabla silver.exchange_rates:**
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

### Capa Gold (Modelo Analítico de Negocio)


Diseñada bajo un enfoque dimensional orientado a resolver la lógica del negocio. Nos enfocamos en el análisis del comportamiento del Peso Argentino (ARS) frente a todas las divisas globales disponibles. Dado que la API cotiza de forma nativa contra el USD, derivamos el tipo de cambio cruzado mediante la fórmula:


$$\text{ARS por moneda} = \frac{\text{cotización ARS}}{\text{cotización moneda}}$$


**Tablas del esquema Gold:**


* **gold.dim_time**: Dimensión temporal detallando día de la semana, hora, mes y año.
* **gold.dim_currency**: Dimensión de monedas para auditoría de vigencia de registros.
* **gold.fact_ars_exchange_rates**: Tabla de hechos que calcula las variaciones porcentuales frente al snapshot previo y procesa las equivalencias cruzadas de valor.

**Métricas principales visualizadas:**

* Tipo de cambio actual de ARS frente a cada moneda.
* Pesos argentinos necesarios para comprar 1 unidad de cada moneda.
* Unidades de cada moneda equivalentes a 1 peso argentino.
* Variación porcentual contra el snapshot anterior.
* Ranking de monedas con mayor suba o baja relativa frente al ARS.

----

> **Pregunta de negocio del Dashboard:
> ¿Cuántos pesos argentinos se necesitan para comprar 1 unidad de cada moneda y cuáles muestran mayor variación relativa entre snapshots de la API?**


---


## Cómo levantar el Stack


El proyecto incluye configuradas todas las variables de entorno necesarias dentro del archivo `.env` versionado para posibilitar el despliegue directo inmediatamente después de clonar el repositorio.


```bash
# 1. Navegá hasta la carpeta del grupo
cd TpFinal/grupos/G02/

# 2. Construí y levantá todo el ecosistema en segundo plano
docker compose up -d --build
```


### Accesos Esperados


* **Airflow UI:** http://localhost:8080
* **Streamlit Dashboard:** http://localhost:8501
* **PostgreSQL Warehouse:** localhost:5432 (Database: exchange)


---


## Estructura del Proyecto


La estructura sigue el esqueleto pedido en [TpFinal/README.md](../../README.md):


```text
TpFinal/grupos/G02/
├── README.md               # Documentación del proyecto
├── .env                    # Variables de entorno pre-configuradas
├── .env.example            # Plantilla de referencia de variables
├── docker-compose.yml      # Orquestación de los 4 servicios del stack
├── init.sql                # Inicialización automatizada de esquemas de la base
├── requirements.txt        # Dependencias Python para el entorno de Airflow
├── dags/
│   ├── 01-bronze/
│   │   └── dag_exchange_bronze.py  # DAG de Ingesta cruda
│   ├── 02-silver/
│   │   └── dag_exchange_silver.py  # DAG de Limpieza e idempotencia
│   └── 03-gold/
│       └── dag_exchange_gold.py    # DAG del Modelo Dimensional
└── dashboard/
    ├── Dockerfile          # Imagen optimizada para el frontend
    ├── requirements.txt    # Librerías (Streamlit, Plotly, SQLAlchemy)
    ├── db.py               # Módulo reutilizable de conexión y queries
    ├── app.py              # Entrypoint formal y portada de bienvenida
    └── pages/
        └── 1_Gold.py       # Interfaz y lógicas de visualización de métricas