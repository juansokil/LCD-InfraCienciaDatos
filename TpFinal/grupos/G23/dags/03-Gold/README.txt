Gold Layer - EcoBici Buenos Aires
Objetivo
La capa Gold toma los datos limpios, validados y tipados de la tabla silver.ecobici_stations y los transforma en un Modelo Dimensional (Modelo Estrella / Star Schema) optimizado para consultas analíticas de Business Intelligence. Esta estructura elimina redundancias repetitivas de telemetría y simplifica la lógica de negocio para alimentar de forma eficiente el Dashboard final en Streamlit.

Arquitectura de Datos (Star Schema)
El Data Mart analítico está estructurado en el esquema gold mediante las siguientes tablas:

gold.dim_station (Estaciones):

Foco: Catálogo maestro y atributos físicos de las terminales de la red.

Campos: station_id (PK), station_name, address, total_capacity, latitude, longitude.

gold.dim_time (Tiempo):

Foco: Estructura cronológica desnormalizada para optimizar agrupaciones temporales.

Campos: time_id (PK - FormatoB YYYYMMDDHHMI), full_timestamp, hour, minute, day_of_week (en español), is_weekend (booleano).

gold.fact_station_availability (Tabla de Hechos Central):

Foco: Registro histórico y métricas de rendimiento en cada snapshot temporal.

Campos: fact_key (PK técnica), time_id (FK), station_id (FK), bikes_available, slots_available, occupancy_ratio.

Transformaciones e Ingeniería de Características
El DAG orquestador en Python (gold_ecobici.py) realiza las siguientes operaciones lógicas:

Fragmentación de Entidades: Descompone la estructura plana de Silver para poblar las dimensiones satélite de forma independiente antes de impactar la tabla de hechos, manteniendo la integridad referencial.

Ingeniería de Atributos Temporales: Extrae componentes del timestamp para calcular dinámicamente las franjas horarias y aislar los patrones de uso mediante el flag de fin de semana (is_weekend).

Consolidación de Métricas: Sincroniza el ratio de ocupación (occupancy_ratio) calculado para asociarlo de manera directa al eje temporal y espacial.

Estrategia de Idempotencia y Carga
Para garantizar que el pipeline sea reproducible y pueda ejecutarse múltiples veces o sufrir interrupciones sin corromper el Data Warehouse, se implementaron estrategias de Upsert:

En dim_station y fact_station_availability, ante colisiones de claves de negocio, se ejecuta un DO UPDATE SET para actualizar el estado más reciente de la terminal.

En dim_time, ante colisiones del identificador temporal, se aplica un DO NOTHING para evitar el procesamiento redundante de registros cronológicos ya existentes.