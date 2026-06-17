# TP Final - G10 
## Integrantes

- Alejo Trenti (@alejotrenti)
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

### Bronze

Tabla: `weather_raw`

Se almacenan los datos obtenidos directamente desde la API sin realizar modificaciones.

Columnas principales:

* city
* api_response (JSON completo)
* ingested_at

Objetivo: conservar una copia de los datos originales para auditoría y trazabilidad.

### Silver

Tabla: `weather`

Se realiza la limpieza y transformación de los datos obtenidos en Bronze.

Columnas principales:

* city
* observation_time
* temperature
* humidity
* wind_speed
* ingested_at

Transformaciones aplicadas:

* Extracción de los datos relevantes desde el JSON.
* Conversión de fechas al formato timestamp.
* Validación de tipos de datos.
* Eliminación de registros incompletos.

Objetivo: disponer de datos limpios y estructurados para análisis.

### Gold

Tabla de hechos: `fact_clima_diario`

Dimensiones:

* `dim_ciudad`
* `dim_tiempo`

Métricas principales:

* temperatura_promedio
* temperatura_maxima
* temperatura_minima
* humedad_promedio
* velocidad_viento_promedio

Pregunta de negocio:

¿Cómo varían las condiciones climáticas entre distintas ciudades argentinas a lo largo del tiempo?

El dashboard permitirá comparar temperaturas, humedad y velocidad del viento entre ciudades mediante gráficos y métricas resumidas.

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
- Postgres: `localhost:5432` (user/pass en `.env`)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

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