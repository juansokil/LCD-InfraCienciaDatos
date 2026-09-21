# TP Final — Data Engineering

## Objetivo

- Construir un pipeline de datos **end-to-end** sobre **una API pública**, con
  arquitectura medallion: **Bronze** (crudo) → **Silver** (limpio y validado) →
  **Gold** (modelado para responder preguntas de negocio).
- Orquestarlo con **Airflow**, guardarlo en **PostgreSQL** y mostrar Gold en un
  dashboard de **Streamlit**.
- Que todo esté containerizado: con `docker compose up` el stack levanta y
  **empieza a generar datos solo**.

## Qué tiene que tener

1. **Un `docker-compose.yml`** que levante todo: la base, Airflow **3.1.5** y el
   dashboard.
2. ⚠️ **El stack tiene que arrancar a correr SOLO.** Cuando se haga
   `docker compose up`, el pipeline empieza a correr sin que haya que activar
   DAGs a mano ni crear schemas manualmente: **Bronze corre al levantar el
   stack y, cuando termina, dispara Silver y después Gold.**
3. **Un dashboard en Streamlit** sobre las tablas Gold.
4. **Un README del grupo**: API elegida, modelo de datos, cómo levantarlo,
   usuario y contraseña de Airflow, e integrantes.
5. **Trabajo repartido en git**: commits de varios integrantes, repartidos en el
   tiempo.
6. **La presentación**, subida al campus en un formato descargable.

## Fuentes posibles

Elijan **una**. Todas se actualizan al menos cada hora, así que tiene sentido
dejar Airflow corriendo y acumulando. Las ideas por capa son orientativas.
Pueden repetir API entre grupos, o proponer otra consultando con el docente.

> **No vale crypto**: CoinGecko es el ejemplo que usamos en clase.

---

### 1. Open-Meteo — Clima
- **URL:** open-meteo.com
- **Auth:** Sin auth, sin limite | **Refresh:** Cada hora

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Clima actual + forecast 7 dias para N ciudades elegidas. Temperatura, lluvia, humedad, viento.
> - **Silver:** Normalizar unidades (Celsius, km/h), separar forecast de medicion real, calcular sensacion termica.
> - **Gold:** `fact_clima_diario` (temp promedio, maxima, minima, lluvia acumulada por ciudad), `dim_ciudad`, `dim_tiempo`. Dashboard: comparacion entre ciudades, alertas de temperatura extrema, historico de lluvia.

---

### 2. OpenWeatherMap — Clima (alternativa)
- **URL:** api.openweathermap.org
- **Auth:** API key gratis | **Refresh:** Cada 10 min

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Clima actual + pronostico 5 dias para ciudades configuradas.
> - **Silver:** Parsear JSON anidado, extraer condiciones (nublado, lluvia, despejado), convertir timestamps UTC a local.
> - **Gold:** `fact_pronostico_vs_real` (comparar forecast con lo que realmente paso), `dim_condicion_climatica`. Dashboard: precision del pronostico, patrones por estacion.

---

### 3. OpenAQ — Calidad del Aire
- **URL:** api.openaq.org/v2
- **Auth:** Sin auth | **Refresh:** Cada hora

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Mediciones de PM2.5, PM10, CO, NO2, O3 por estacion de monitoreo global.
> - **Silver:** Filtrar mediciones invalidas (negativos, outliers), estandarizar unidades (ug/m3), enriquecer con pais/ciudad.
> - **Gold:** `fact_calidad_aire_diaria` (indice AQI calculado, promedio por contaminante), `dim_estacion`, `dim_ciudad`. Dashboard: ranking de ciudades mas contaminadas, evolucion AQI, mapa de calor.

---

### 4. USGS Earthquakes — Sismos
- **URL:** earthquake.usgs.gov/fdsnws
- **Auth:** Sin auth | **Refresh:** Tiempo real

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Sismos del ultimo dia/semana en formato GeoJSON. Magnitud, profundidad, coordenadas, tsunami.
> - **Silver:** Parsear GeoJSON a tabular, clasificar por escala (leve/moderado/fuerte), asignar region/pais por coordenadas.
> - **Gold:** `fact_sismos_diarios` (cantidad por region, magnitud promedio/maxima), `dim_region`. Dashboard: mapa de sismos, frecuencia por zona tectonica, distribucion de magnitudes.

---

### 5. GitHub Events — Actividad Open Source
- **URL:** api.github.com
- **Auth:** Sin auth (60 req/h) | **Refresh:** Tiempo real

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Eventos publicos: PushEvent, PullRequestEvent, IssuesEvent, ForkEvent, etc.
> - **Silver:** Clasificar por tipo de evento, extraer lenguaje del repo, parsear actor (usuario), filtrar bots.
> - **Gold:** `fact_actividad_diaria` (eventos por lenguaje, por tipo), `dim_lenguaje`, `dim_tipo_evento`. Dashboard: lenguajes mas activos, horarios pico de actividad, ratio PRs/issues.

---

### 6. Citybikes — Bicicletas Publicas
- **URL:** api.citybik.es/v2
- **Auth:** Sin auth | **Refresh:** Cada 2-5 min

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Snapshot de estaciones de bicicletas publicas (EcoBici, Citi Bike, etc): bikes disponibles, slots vacios, coordenadas, timestamp.
> - **Silver:** Enriquecer con barrio/zona por coordenadas, calcular porcentaje de ocupacion, filtrar estaciones inactivas.
> - **Gold:** `fact_ocupacion_por_hora` (bikes promedio, ocupacion pico por estacion/zona), `dim_estacion`, `dim_zona`. Dashboard: estaciones mas saturadas, patron de uso por hora del dia, mapa de disponibilidad.

---

### 7. OpenSky Network — Trafico Aereo
- **URL:** opensky-network.org/api
- **Auth:** Sin auth (anonimo) | **Refresh:** Cada 10s

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Snapshot de aviones en vuelo: latitud, longitud, altitud, velocidad, rumbo, pais de origen, indicativo de vuelo.
> - **Silver:** Filtrar por region geografica, clasificar fase de vuelo (ascenso/crucero/descenso por altitud), enriquecer con pais/continente.
> - **Gold:** `fact_trafico_por_hora` (cantidad de vuelos por region, altitud promedio, velocidad promedio), `dim_vuelo`, `dim_region`. Dashboard: mapa de vuelos activos, densidad por zona, horarios pico de trafico aereo.

---

### 8. NASA FIRMS — Focos de incendio (satelital)
- **URL:** firms.modaps.eosdis.nasa.gov/api/area
- **Auth:** MAP_KEY gratis | **Refresh:** Near real-time (~cada hora, tras cada pasada satelital)

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Detecciones de fuego activo (lat, lon, brillo, confianza, FRP, satelite, fecha/hora) filtradas por un bounding box de Argentina. Respuesta en CSV.
> - **Silver:** Filtrar por nivel de confianza, deduplicar detecciones entre satelites, clasificar intensidad por FRP/brillo, asignar provincia por coordenadas.
> - **Gold:** `fact_focos_diarios` (cantidad e intensidad por provincia/dia), `dim_provincia`, `dim_satelite`. Dashboard: mapa de incendios activos, provincias mas afectadas, evolucion temporal de focos.

---

### 9. API Transporte Buenos Aires — Transporte en tiempo real
- **URL:** api-transporte.buenosaires.gob.ar
- **Auth:** Registro gratis (client_id + client_secret) | **Refresh:** Tiempo real (~30s)

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Posiciones GPS de colectivos / subte via GTFS-realtime (parsear el protobuf a tabular): linea, vehiculo, lat/lon, velocidad, timestamp. (El portal tambien expone arribos, alertas y EcoBici.)
> - **Silver:** Filtrar por linea/zona, calcular velocidad y estado, enriquecer con el GTFS estatico (nombre de linea, recorrido).
> - **Gold:** `fact_posiciones_por_hora` (vehiculos activos por linea, velocidad promedio), `dim_linea`, `dim_franja_horaria`. Dashboard: mapa de unidades en vivo, velocidad por corredor, horas pico.
> - ⚠️ **Mas setup que las demas:** requiere registrarse para obtener las credenciales y parsear GTFS-realtime (protobuf, con `gtfs-realtime-bindings`). Recomendada para grupos que quieran un desafio extra.

---

### 10. Where the ISS at? — Estacion Espacial Internacional
- **URL:** api.wheretheiss.at/v1/satellites/25544
- **Auth:** Sin auth | **Refresh:** Tiempo real (posicion instantanea)

> 💡 **Ideas orientativas** (no son requisitos):
> - **Bronze:** Snapshot de la posicion de la ISS (lat, lon, altitud, velocidad, visibilidad dia/noche, timestamp) en cada ingesta.
> - **Silver:** Determinar si esta sobre oceano o tierra / que pais por coordenadas, fase dia/noche, deltas de posicion entre snapshots.
> - **Gold:** `fact_paso_por_region` (tiempo y orbitas sobre cada continente o pais, altitud/velocidad promedio), `dim_region`. Dashboard: traza orbital en el mapa, % de tiempo sobre tierra vs oceano, pasos sobre Argentina.
> - ℹ️ **La mas simple en datos** (pocos campos): el valor esta en acumular la trayectoria con el tiempo. Buena para un grupo que quiera algo liviano.

## Criterios de evaluación

| # | Criterio | Qué se mira |
|---|---|---|
| 1 | **Pipeline funcional** | Corre solo, produce datos reales y está encadenado bronze → silver → gold. Correrlo dos veces no duplica filas. |
| 2 | **Modelo y transformaciones** | Modelo dimensional (fact/dim), tipado, validación, deduplicación. **Acá se sube el techo.** |
| 3 | **Dashboard sobre Gold** | Lee solo `gold.*`, responde preguntas de negocio y no se rompe sin datos. |
| 4 | **Containerización y arranque** | `docker compose up` y corre solo. Airflow 3.1.5, healthchecks, `init.sql`. **El más discriminante.** |
| 5 | **Documentación y trabajo del grupo** | README completo, código legible, historial de git con varios autores. |

**Suman, sin ser obligatorios**: contratos de datos con cuarentena (clase 04),
métricas de calidad en el tiempo (clase 04), y una capa semántica de vistas
`gold.v_*` (clase 05).

## Esqueleto de entrega

Cada grupo trabaja en su carpeta `TpFinal/grupos/G<NN>/`. Arranquen copiando el
template [`grupos/G00/README.md`](grupos/G00/README.md).

```
TpFinal/grupos/G<NN>/
├── README.md                       # API elegida + modelo de datos + como levantar el stack
├── docker-compose.yml              # 4 servicios: warehouse + airflow_db + airflow + dashboard
├── Dockerfile                      # imagen Airflow custom (basada en apache/airflow:3.1.5)
├── Dockerfile.postgres             # opcional: si quieren pre-cargar init.sql en la imagen
├── init.sql                        # CREATE SCHEMA bronze, silver, gold
├── requirements.txt                # deps Python para Airflow (pandas, sqlalchemy, requests, etc.)
├── .env                            # variables de entorno — SI se versiona (ver abajo)
├── .gitignore                      # ignorar credentials/, __pycache__, data/, etc.
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

> **El `.env` va al repo**, a propósito: así el stack levanta con un solo
> comando, y el `.gitignore` ya tiene la excepción. Solo credenciales de juguete
> (`admin/admin`). Una API key real no va ahí: se pasa como variable del host y
> el `.env` la lee con `${MI_API_KEY}`. **Nada los frena si la suben**, así que
> revisen antes de commitear.

## Cómo entregar

1. **Pidan el número de grupo** al docente (`G01`, `G02`, ...). Va en la rama,
   en la carpeta y en el título del PR.
2. Creen la rama **`tpfinal/G<NN>`** desde `main`, y la carpeta
   `TpFinal/grupos/G<NN>/`.
3. Abran un **PR en draft** contra `main`, con título `TP Final - G<NN> - <API>`
   y en el cuerpo: integrantes (nombre + usuario de GitHub), API elegida e idea
   para Gold.
4. Trabajen en esa rama: cada push actualiza el PR solo.
5. **Entrega: domingo 15 de noviembre de 2026, 23:59 (hora Argentina)** — en el
   PR, click en **"Ready for review"**.
6. **Presentación: jueves 19 de noviembre de 2026, remota**, 7 a 10 minutos con
   el dashboard corriendo. Qué mostrar:
   [`consigna_presentacion.html`](consigna_presentacion.html).

Dudas de git (crear la rama, conflictos, trabajar de a varios):
[`git-guia.md`](git-guia.md).
