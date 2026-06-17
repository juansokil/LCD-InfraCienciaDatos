# TP Final - G10 
## Integrantes

- Alejo Trenti 
- Abigail Lezcano Garcia
- Nicolas Ezequiel Lombisano
- Thiago Daian Sosa Elizaincin
- Rodrigo Romero
- Samir Almuiña 

## API elegida

* **Nombre**: Open-Meteo
* **URL**: https://open-meteo.com
* **Descripcion**: API pública que proporciona información meteorológica actual y pronósticos del tiempo para distintas ubicaciones geográficas. Permite obtener datos como temperatura, humedad, velocidad del viento y precipitaciones.
* **Auth**: Sin autenticación.
* **Refresh**: Cada hora.

## Modelo de datos

---

## 🥉 Bronze Layer

**Tabla:** `bronze.weather_raw`

Se almacenan los datos crudos tal como llegan desde la API.

**Campos:**
- city
- api_response (JSON completo)
- ingested_at

**Objetivo:**  
Tener trazabilidad completa de los datos originales.

---

## 🥈 Silver Layer

**Tabla:** `silver.weather`

Se realiza limpieza y estructuración del JSON.

**Campos principales:**
- city
- temperature
- precipitation
- windspeed
- timestamp
- ingested_at

**Transformaciones:**
- Parseo del JSON
- Conversión de tipos
- Eliminación de valores nulos
- Normalización de estructura

---

## 🥇 Gold Layer

**Tabla:** `gold.weather_summary`

Tabla agregada por ciudad para análisis.

**Columnas:**

- city  
- avg_temp_max  
- avg_temp_min  
- max_temp_max  
- min_temp_min  
- total_precipitation  
- rainy_days  

---

## 📊 Pregunta de negocio

> ¿Cómo varían las condiciones climáticas entre distintas ciudades argentinas?

El objetivo del dashboard es comparar:
- temperaturas promedio
- extremos térmicos
- precipitaciones
- cantidad de días lluviosos

---

## Como levantar el stack

```bash
cd TpFinal/grupos/G10/      
cp .env.example .env
docker compose up -d --build
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8080 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432`

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y elimina volúmenes
```

## Estructura del proyecto

```
TpFinal/grupos/G10/
├── README.md
├── docker-compose.yml
├── Dockerfile
├── init.sql
├── requirements.txt
├── .env.example
├── .gitignore
├── dags/
│   ├── 01-bronze/
│   │   └── openmeteo_bronze.py
│   │       # Obtiene datos de Open-Meteo y guarda el JSON original en bronze.weather_raw
│   │
│   ├── 02-silver/
│   │   └── openmeteo_silver.py
│   │       # Extrae temperatura, humedad, viento y fechas desde Bronze
│   │       # Guarda datos limpios en silver.weather
│   │
│   └── 03-gold/
│       └── openmeteo_gold.py
│           # Genera métricas diarias y tablas para el dashboard
│           # Guarda resultados en gold.fact_clima_diario
│
└── dashboard/
    ├── Dockerfile
    ├── app.py
    ├── db.py
    ├── requirements.txt
    └── pages/
        └── 1_Gold.py
```
