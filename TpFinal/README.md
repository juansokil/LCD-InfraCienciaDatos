# TP Final - Data Engineering

## Objetivo

Diseñar e implementar un pipeline de datos end-to-end utilizando una **API pública** como fuente de datos. El proyecto debe seguir la **arquitectura medallion** (Bronze → Silver → Gold) y estar completamente containerizado con Docker, de forma que al ejecutar `docker compose up` el stack completo quede operativo.

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Orquestador | Apache Airflow |
| Base de datos | PostgreSQL (schemas: bronze, silver, gold) |
| Dashboard | Streamlit |
| Containerizacion | Docker Compose |

## Arquitectura Medallion

```
API publica  →  [Airflow DAG]  →  Bronze (datos crudos)
                                      ↓
                                  Silver (datos limpios)
                                      ↓
                                  Gold (agregados de negocio)
                                      ↓
                                  [Streamlit Dashboard]
```

### Bronze
Ingesta cruda de la API a la base. Datos tal como llegan, con metadatos de auditoria (timestamp, fuente).

### Silver
Datos limpios, tipados y validados. Una version de los datos lista para analisis.

### Gold
Datos modelados para consumo: tablas pensadas para responder preguntas de negocio o alimentar el dashboard.

## Entregables

1. **Repositorio** con el codigo completo
2. **docker-compose.yml** funcional: `docker compose up` y listo
3. **DAGs de Airflow**: minimo un DAG por capa (bronze, silver, gold)
4. **Dashboard en Streamlit** con una vista por capa (Bronze, Silver, Gold)
5. **README** del proyecto explicando: API elegida, modelo de datos, como levantar el stack

## APIs publicas disponibles

A continuacion se listan APIs gratuitas que pueden utilizarse como fuente de datos. Cada grupo debe elegir **una** API y construir su pipeline completo.

Solo se incluyen APIs con datos que se actualizan al menos cada hora, lo que justifica tener Airflow corriendo y acumulando snapshots continuamente. Para cada API se incluyen **ideas orientativas** de como aplicar Bronze / Silver / Gold — son sugerencias, no requisitos. Cada grupo decide que transformaciones tienen sentido segun su caso.

---

> **Nota:** En clase usaremos **CoinGecko** (api.coingecko.com/api/v3) como ejemplo de referencia para mostrar el pipeline completo. Por lo tanto, **no se puede elegir CoinGecko ni ninguna API de crypto** para el TP.

---

### 1. Open Exchange Rates — Divisas
- **URL:** openexchangerates.org/api
- **Auth:** API key gratis | **Refresh:** Cada hora

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Tipos de cambio de ~170 monedas contra USD. Un snapshot por ingesta.
> - **Silver:** Pivotear la tabla (una columna por moneda → filas), calcular tipo de cambio cruzado (ej: EUR/ARS).
> - **Gold:** `fact_tipo_cambio_diario` (apertura, cierre, variacion), `dim_moneda`. Dashboard: evolucion de monedas seleccionadas, volatilidad, comparacion regional.

---

### 2. Open-Meteo — Clima
- **URL:** open-meteo.com
- **Auth:** Sin auth, sin limite | **Refresh:** Cada hora

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Clima actual + forecast 7 dias para N ciudades elegidas. Temperatura, lluvia, humedad, viento.
> - **Silver:** Normalizar unidades (Celsius, km/h), separar forecast de medicion real, calcular sensacion termica.
> - **Gold:** `fact_clima_diario` (temp promedio, maxima, minima, lluvia acumulada por ciudad), `dim_ciudad`, `dim_tiempo`. Dashboard: comparacion entre ciudades, alertas de temperatura extrema, historico de lluvia.

---

### 3. OpenWeatherMap — Clima (alternativa)
- **URL:** api.openweathermap.org
- **Auth:** API key gratis | **Refresh:** Cada 10 min

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Clima actual + pronostico 5 dias para ciudades configuradas.
> - **Silver:** Parsear JSON anidado, extraer condiciones (nublado, lluvia, despejado), convertir timestamps UTC a local.
> - **Gold:** `fact_pronostico_vs_real` (comparar forecast con lo que realmente paso), `dim_condicion_climatica`. Dashboard: precision del pronostico, patrones por estacion.

---

### 4. OpenAQ — Calidad del Aire
- **URL:** api.openaq.org/v2
- **Auth:** Sin auth | **Refresh:** Cada hora

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Mediciones de PM2.5, PM10, CO, NO2, O3 por estacion de monitoreo global.
> - **Silver:** Filtrar mediciones invalidas (negativos, outliers), estandarizar unidades (ug/m3), enriquecer con pais/ciudad.
> - **Gold:** `fact_calidad_aire_diaria` (indice AQI calculado, promedio por contaminante), `dim_estacion`, `dim_ciudad`. Dashboard: ranking de ciudades mas contaminadas, evolucion AQI, mapa de calor.

---

### 5. USGS Earthquakes — Sismos
- **URL:** earthquake.usgs.gov/fdsnws
- **Auth:** Sin auth | **Refresh:** Tiempo real

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Sismos del ultimo dia/semana en formato GeoJSON. Magnitud, profundidad, coordenadas, tsunami.
> - **Silver:** Parsear GeoJSON a tabular, clasificar por escala (leve/moderado/fuerte), asignar region/pais por coordenadas.
> - **Gold:** `fact_sismos_diarios` (cantidad por region, magnitud promedio/maxima), `dim_region`. Dashboard: mapa de sismos, frecuencia por zona tectonica, distribucion de magnitudes.

---

### 6. GitHub Events — Actividad Open Source
- **URL:** api.github.com
- **Auth:** Sin auth (60 req/h) | **Refresh:** Tiempo real

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Eventos publicos: PushEvent, PullRequestEvent, IssuesEvent, ForkEvent, etc.
> - **Silver:** Clasificar por tipo de evento, extraer lenguaje del repo, parsear actor (usuario), filtrar bots.
> - **Gold:** `fact_actividad_diaria` (eventos por lenguaje, por tipo), `dim_lenguaje`, `dim_tipo_evento`. Dashboard: lenguajes mas activos, horarios pico de actividad, ratio PRs/issues.

---

### 7. Citybikes — Bicicletas Publicas
- **URL:** api.citybik.es/v2
- **Auth:** Sin auth | **Refresh:** Cada 2-5 min

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Snapshot de estaciones de bicicletas publicas (EcoBici, Citi Bike, etc): bikes disponibles, slots vacios, coordenadas, timestamp.
> - **Silver:** Enriquecer con barrio/zona por coordenadas, calcular porcentaje de ocupacion, filtrar estaciones inactivas.
> - **Gold:** `fact_ocupacion_por_hora` (bikes promedio, ocupacion pico por estacion/zona), `dim_estacion`, `dim_zona`. Dashboard: estaciones mas saturadas, patron de uso por hora del dia, mapa de disponibilidad.

---

### 8. OpenSky Network — Trafico Aereo
- **URL:** opensky-network.org/api
- **Auth:** Sin auth (anonimo) | **Refresh:** Cada 10s

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Snapshot de aviones en vuelo: latitud, longitud, altitud, velocidad, rumbo, pais de origen, indicativo de vuelo.
> - **Silver:** Filtrar por region geografica, clasificar fase de vuelo (ascenso/crucero/descenso por altitud), enriquecer con pais/continente.
> - **Gold:** `fact_trafico_por_hora` (cantidad de vuelos por region, altitud promedio, velocidad promedio), `dim_vuelo`, `dim_region`. Dashboard: mapa de vuelos activos, densidad por zona, horarios pico de trafico aereo.

## Criterios de evaluacion

| Criterio 
|---|
| Pipeline funcional (Bronze → Silver → Gold) | 
| Calidad del modelo de datos y transformaciones | 
| Dashboard con visualizaciones relevantes |  
| Containerizacion (docker compose up y funciona) |  
| Documentacion y claridad del codigo |  

## Estructura sugerida del proyecto

```
mi-proyecto/
├── docker-compose.yml
├── Dockerfile               # imagen de Airflow (mismo patron que stack/)
├── init.sql                 # schemas bronze/silver/gold
├── requirements.txt
├── dags/
│   ├── 01-bronze/
│   ├── 02-silver/
│   └── 03-gold/
└── dashboard/
    ├── Dockerfile
    ├── app.py
    ├── db.py
    ├── requirements.txt
    └── pages/
```

## Como empezar

1. Elegir una API de la lista (o proponer otra, consultando con el docente)
2. Explorar la API: endpoints, estructura de respuesta, limites
3. Disenar el modelo de datos: que tablas en bronze, que limpieza en silver, que metricas en gold
4. Armar el `docker-compose.yml` con los 4 servicios: postgres (warehouse), postgres (airflow), airflow, dashboard
5. Desarrollar los DAGs de Airflow para cada capa
6. Construir el dashboard en Streamlit
7. Documentar todo en un README
