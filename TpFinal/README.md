# TP Final - Data Engineering

## Objetivo

Diseñar e implementar un pipeline de datos end-to-end utilizando una **API pública** como fuente de datos. El proyecto debe seguir la **arquitectura medallion** (Bronze → Silver → Gold) y estar completamente containerizado con Docker, de forma que al ejecutar `docker compose up` el stack completo quede operativo.

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Orquestador | Apache Airflow |
| Base de datos | PostgreSQL (schemas: bronze, silver, gold) |
| Dashboard | Streamlit (consume tablas Gold) |
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
3. **DAGs de Airflow**: minimo un DAG por capa (bronze, silver, gold), todos con **schedule definido** y **activos por default** (no en pausa)
4. **Dashboard en Streamlit** sobre las tablas **Gold** (el dashboard consume el modelo final, no Bronze ni Silver)
5. **README** del proyecto explicando: API elegida, modelo de datos, como levantar el stack

> ⚠️ **Importante: el stack tiene que arrancar a correr SOLO**. Cuando se haga `docker compose up`, el pipeline empieza a correr sin que haya que activar DAGs a mano ni crear schemas manualmente:
> - DAGs **activados por default** (en el `@dag(...)` poner `is_paused_upon_creation=False`).
> - Cada DAG con **schedule definido** (NO `schedule=None`) — elegir el intervalo segun el `Refresh` de la API que eligieron (ej: `@hourly` si la API actualiza cada hora, `"*/15 * * * *"` para cada 15 min, `@daily`, etc.).
> - Los schemas `bronze`/`silver`/`gold` se crean solos (via `init.sql` montado al postgres).
> - El dashboard arranca, conecta a Postgres y muestra Gold automaticamente.
>
> Una vez levantado, va a haber datos en las tablas en cuestion de minutos/horas segun el schedule.

## Organizacion y entrega

| | |
|---|---|
| **Donde se entrega** | En **este mismo repo**, en una branch del grupo: `tp-final/G<NN>`. Cada grupo trabaja en su carpeta `TpFinal/grupos/G<NN>/` y entrega via **Pull Request en draft** contra `main`. Ver seccion "Como entregar el TP" mas abajo. |
| **Politica de APIs** | Pueden repetir la misma API entre grupos (no es excluyente). Si quieren proponer una API fuera de la lista, consultar con el docente. |
| **Fecha de entrega** | **17-06-26 hasta 23:59** — entrega = PR del grupo marcado como **"Ready for review"** en GitHub. |
| **Presentacion oral** | **18-06-26 en clase**, **5 a 6 minutos maximo por grupo**. |

> **Sobre `G<NN>`**: `G` = Grupo, `NN` = numero de 2 digitos (`G01`, `G02`, ..., `G99`). El numero te lo asigna el docente cuando abren el PR-draft (mira los grupos ya registrados y confirma el siguiente libre). `G00` es el template de referencia, no es una entrega real.

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
| Dashboard sobre Gold con visualizaciones relevantes |  
| Containerizacion + arranque automatico (`docker compose up` y el pipeline corre solo, sin activar DAGs a mano) |  
| Documentacion y claridad del codigo |  

## Esqueleto de entrega

> 💡 **Template del README**: en [`grupos/G00/README.md`](grupos/G00/README.md) hay una plantilla del README que va al lado del codigo (integrantes, API, modelo de datos, como levantar, decisiones tecnicas). Copienlo a `grupos/G<NN>/README.md` como punto de partida — el resto de los archivos los arman desde cero siguiendo este esqueleto.

Cada grupo trabaja dentro de su propia carpeta `TpFinal/grupos/G<NN>/`. La estructura completa que esperamos:

```
TpFinal/grupos/G<NN>/
├── README.md                       # API elegida + modelo de datos + como levantar el stack
├── docker-compose.yml              # 4 servicios: warehouse + airflow_db + airflow + dashboard
├── Dockerfile                      # imagen Airflow custom (basada en apache/airflow:3.1.5)
├── Dockerfile.postgres             # opcional: si quieren pre-cargar init.sql en la imagen
├── init.sql                        # CREATE SCHEMA bronze, silver, gold
├── requirements.txt                # deps Python para Airflow (pandas, sqlalchemy, requests, etc.)
├── .env.example                    # variables de entorno (cada uno copia a .env)
├── .gitignore                      # ignorar .env, credentials/, __pycache__, etc.
├── dags/
│   ├── 01-bronze/
│   │   └── <api>_bronze.py         # ingesta cruda de la API a schema bronze
│   ├── 02-silver/
│   │   └── <api>_silver.py         # limpieza, validacion, tipos
│   └── 03-gold/
│       └── <api>_gold.py           # agregaciones, modelo dimensional (fact/dim)
└── dashboard/
    ├── Dockerfile                  # imagen del dashboard (basada en python:3.11-slim)
    ├── app.py                      # entrypoint Streamlit (st.set_page_config + intro)
    ├── db.py                       # conexion a Postgres (reusable desde todas las paginas)
    ├── requirements.txt            # streamlit, pandas, sqlalchemy, plotly, etc.
    └── pages/                       # vistas adicionales sobre tablas GOLD
        └── 1_Gold.py                # dashboard de KPIs / vistas de negocio sobre el modelo final
```

> **Patron de referencia**: la estructura sigue la misma logica del [`stack/`](../stack/) del curso (Airflow 3.1.5 + Postgres 17 Alpine + Streamlit). Pueden mirar `stack/` para inspirarse en el `docker-compose.yml`, `Dockerfile`, `init.sql`, etc. 

> **Por que `G<NN>`?** `G` = Grupo y `NN` = numero de 2 digitos (`G01`, `G02`, ..., `G99`). El numero te lo asigna el docente cuando abren el PR-draft (mira los grupos ya registrados y te confirma el siguiente libre). Tiene que coincidir con el nombre de la branch (`tp-final/G01` ↔ `TpFinal/grupos/G01/`) — asi el docente puede comparar branches lado a lado al evaluar.

> **Donde corre el stack del grupo?** En la maquina de cada alumno. Cuando hagan `docker compose up` dentro de `TpFinal/grupos/G<NN>/`, levanta SU propio Postgres, Airflow y Streamlit aislados — no se mezcla con el stack del curso ni con el de otros grupos. **Ojo con los puertos**: si tienen el stack del curso levantado en paralelo, va a haber conflicto en 5432/8080/8501 — apaguen uno antes de levantar el otro, o cambien los mapeos en `docker-compose.yml`.

## Como entregar el TP: branch + PR

El TP se desarrolla y se entrega **en este mismo repo** (no en repo propio). Cada grupo trabaja en su propia branch, y abre un **PR** que oficia como aviso + entrega.

### Paso a paso

**1. Crear la branch** desde `main`:

```bash
git checkout main && git pull
git checkout -b tp-final/G<NN>
# ej: git checkout -b tp-final/G01
```

**2. Crear la subcarpeta del grupo** en `TpFinal/grupos/G<NN>/` y pushear el primer commit con el esqueleto minimo (ver "Esqueleto de entrega" mas abajo):

```bash
mkdir -p TpFinal/grupos/G01
# crear TpFinal/grupos/G01/README.md con: integrantes + API + idea Gold
git add TpFinal/grupos/G01/
git commit -m "tp-final/G01: setup inicial (API: OpenAQ)"
git push -u origin tp-final/G01
```

**3. Abrir un PR** contra `main`:

- **Titulo exacto**: `TP Final - G<NN> - <API>`
  Ejemplo: `TP Final - G01 - OpenAQ`
- **Body sugerido**:
  - **Integrantes**: nombre completo + usuario de GitHub de cada uno.
  - **API elegida**: nombre + URL.
  - **Idea Gold (1-2 oraciones)**: que pregunta de negocio van a responder con su dashboard.

**4. Trabajar en la branch**: commits chicos y frecuentes mejor que pocos grandes. Cada `git push` actualiza el PR automaticamente.

**5. Entrega final (17-06-26 hasta 23:59)**: en el PR, hacer click en el boton **"Ready for review"**. Eso transforma el draft en PR formal — esa accion es la entrega.

**6. Presentacion (18-06-26 en clase)**: 5-6 minutos con el dashboard corriendo en sus maquinas.


> **PR (Pull Request)** = propuesta de mergear los commits de una branch a otra; lleva codigo, se puede revisar linea por linea, tiene aprobaciones y se puede mergear.
> **Branch (rama)** = copia paralela del codigo donde se desarrolla, antes de mergear a `main`.

## Como empezar

1. **Elegir API**: una de la lista (o proponer otra, consultando con el docente).
2. **Explorar la API**: endpoints, estructura de respuesta, rate limits, auth.
3. **Disenar el modelo de datos**: que tablas en bronze, que limpieza en silver, que metricas / fact / dim en gold.
4. **Crear la branch** `tp-final/G<NN>` desde `main` y la carpeta `TpFinal/grupos/G<NN>/` (ver "Como entregar el TP" arriba). **Tip**: arrancá copiando el README template ([`grupos/G00/README.md`](grupos/G00/README.md)) como `TpFinal/grupos/G<NN>/README.md` para tener la plantilla de los datos del proyecto.
5. **Abrir el PR-draft** contra `main` con el titulo y body sugeridos.
6. Armar el `docker-compose.yml` con los 4 servicios: postgres (warehouse), postgres (airflow), airflow, dashboard. Inspirarse en [`stack/docker-compose.yml`](../stack/docker-compose.yml).
7. Desarrollar los DAGs de Airflow para cada capa (1 DAG minimo por capa) — definir `schedule` segun la frecuencia de la API (ver el `Refresh` de cada API en la seccion arriba) y `is_paused_upon_creation=False` para que arranque solo.
8. Construir el dashboard en Streamlit **sobre las tablas Gold** (KPIs / vistas de negocio — no se visualizan Bronze ni Silver, eso es backend del pipeline).
9. Documentar todo en `TpFinal/grupos/G<NN>/README.md`: API elegida, modelo de datos, como levantar el stack, decisiones tecnicas.
10. **Entregar** antes del **17-06-26 hasta 23:59**  y **presentar** el **18-06-26** (5-6 min).
