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
3. **DAGs de Airflow**: minimo un DAG por capa (bronze, silver, gold), **encadenados por Assets** (bronze con cron y `outlets=`; silver y gold con `schedule=[ASSET]`, sin cron) y **activos por default** (no en pausa)
4. **Dashboard en Streamlit** sobre las tablas **Gold** (el dashboard consume el modelo final, no Bronze ni Silver)
5. **README** del proyecto explicando: API elegida, modelo de datos, como levantar el stack
   
   *(Y la **presentacion**, que ademas de exponerse hay que **subirla al campus** en
   un formato descargable — ver `consigna_presentacion.html`.)*
6. **Trabajo repartido en git**: que **commiteen varios integrantes**, con commits del dominio
   distribuidos en el tiempo — no un unico commit gigante el ultimo dia, ni un solo autor
   subiendo todo. El historial es parte de la entrega: muestra como trabajo el grupo, y se mira.

> ⚠️ **Importante: el stack tiene que arrancar a correr SOLO.** Cuando se haga
> `docker compose up`, el pipeline empieza a correr sin que haya que activar DAGs a mano ni crear schemas manualmente:
>
> Y rapido: en el pipeline del curso, desde que arranca Airflow hasta que hay datos en Gold
> pasan **menos de 30 segundos** — bronze a los 8s, y silver, gold y el scoring encadenados
> detras. No es una meta ambiciosa: es lo que sale solo cuando la configuracion esta bien.
>
> **Como se corrige esto**: el docente hace `docker compose up` en frio y mira. Si al minuto
> no hay filas en Bronze, no se sale a buscar por que — se anota que no arranco.
>
> - DAGs **activados por default** (en el `@dag(...)` poner `is_paused_upon_creation=False`).
> - **Ningun DAG con `schedule=None`.** Pero ojo con la forma: el cron va **solo en Bronze** —
>   elegi el intervalo segun el `Refresh` de tu API (ej: `@hourly`, `"*/15 * * * *"`, `@daily`)—
>   y **silver y gold NO llevan cron**: van con `schedule=[ASSET]`, que es lo que los
>   despierta cuando la capa de arriba termino. Esta explicado abajo, en "UN SOLO CRON,
>   EN EL BORDE".
> - **`start_date` en el PASADO.** Esta es la trampa que mas silencio hace, asi que va
>   medida y no de palabra: con `catchup=False` y `start_date` viejo, Airflow crea la
>   corrida del **ultimo intervalo ya cerrado** y la ejecuta **al instante** — lo medimos en
>   el stack del curso y el DAG arranco **1 segundo** despues de que Airflow leyo el archivo.
>   Con `start_date` en el futuro (o `datetime.now()`), en cambio, **no corre nunca**:
>   probamos uno con fecha de manana y a los 45 segundos tenia **cero corridas**.
>
>   Es la diferencia entre un TP que genera datos solo y uno que parece roto sin estarlo.
>   Poner algo como `start_date=datetime(2024, 1, 1)` y listo.
> - **ENCADENAR las tres capas** (esto es lo que mas falla). Si las tres comparten el mismo cron, disparan al mismo tiempo: bronze todavia no escribio y silver/gold leen una tabla vacia (o inexistente, y el DAG queda en rojo).
>
>   **La forma que esperamos: UN SOLO CRON, EN EL BORDE.** Bronze corre por reloj porque sale a buscar a una API que no le avisa cuando hay dato nuevo. De ahi para adentro, cada capa arranca **cuando la anterior termino de escribir**, usando Airflow Assets:
>
>   ```
>   bronze   cron cada N min          --emite-->  BRONZE_LISTO
>   silver   schedule=[BRONZE_LISTO]  --emite-->  SILVER_LISTO
>   gold     schedule=[SILVER_LISTO]
>   ```
>
>   ```python
>   # common/assets.py  -- definilos UNA vez y que los tres DAGs los importen.
>   # Si cada DAG construye su propio Asset(...), un typo rompe el encadenado EN SILENCIO.
>   from airflow.sdk import Asset
>   BRONZE_LISTO = Asset(name="bronze_mi_api")
>
>   # 01-bronze: cron (es el borde) + la task que ESCRIBE declara el asset
>   @dag(schedule="*/15 * * * *", is_paused_upon_creation=False, ...)
>   @task(outlets=[BRONZE_LISTO])
>   def load_bronze(...): ...
>
>   # 02-silver: sin cron, escucha el asset
>   @dag(schedule=[BRONZE_LISTO], is_paused_upon_creation=False, ...)
>   ```
>
>   El `outlets` va en la **task que escribe**, no al final del DAG: lo que se publica es *"el dato existe"*, no *"el DAG termino"*.
>
>   📎 **Implementacion de referencia: el pipeline del curso.** No es un ejemplo de juguete, es el que corre en `stack/`. Miren estos cuatro archivos, en este orden:
>
>   > ℹ️ El `stack/` se publica junto con la **clase 02**. Si estan leyendo esto en
>   > la primera semana, los links de abajo todavia no resuelven — vuelvan cuando
>   > tengan el stack levantado, que es cuando esto se entiende de verdad.
>
>   | Archivo | Que mirar | Llega con |
>   |---|---|---|
>   | `stack/dags/common/assets.py` | los assets definidos una sola vez, con el mapa de la cadena arriba de todo | clase 03 |
>   | `clase03/ejercicios/dag_crypto_bronze.py` | el unico con cron, y el `outlets=` en `load_markets` | clase 03 |
>   | `clase04/ejercicios/dag_crypto_silver.py` | `schedule=[BRONZE_CRYPTO]` + emite el suyo | clase 04 |
>   | `clase05/ejercicios/dag_crypto_gold.py` | `schedule=[SILVER_CRYPTO]` + emite dos assets, uno por consumidor | clase 05 |
>
>   > Los tres DAGs viven en `claseNN/ejercicios/`. Aparecen bajo `stack/dags/`
>   > recien cuando los copies vos, siguiendo el README de cada clase (`cp
>   > clase03/ejercicios/dag_crypto_bronze.py stack/dags/01-bronze/`). Es a
>   > proposito: el `.gitignore` no versiona `stack/dags/**/*.py` para que cada
>   > clase llegue a su tiempo.
>
>   **Tres trampas que ya nos comimos** (les van a ahorrar una tarde):
>   1. **Un run disparado por asset NO tiene `logical_date`**, asi que `ds` no existe en el contexto: pedirlo tira `KeyError('ds')`. Si su DAG es incremental por dia, prevean el caso — miren `_target_date()` en `dag_crypto_silver.py`.
>   2. **Un consumidor pausado no se dispara** y no hay ningun error a la vista: el asset se actualiza, el DAG simplemente no arranca. De ahi el `is_paused_upon_creation=False` en los tres.
>   3. **Un dato, un dueño.** Si dos DAGs escriben la misma tabla, ganan por orden de llegada y el resultado se vuelve no determinista. Una tabla se escribe desde un solo lugar.
>
>   **El cron escalonado NO alcanza.** Escalonar los tres crons parece equivalente, y no lo
>   es: silver arranca **por reloj**, no porque bronze haya terminado. El dia que bronze
>   tarde de mas, silver procesa datos viejos **sin fallar** y gold publica igual. Un
>   pipeline que anda mientras miente es peor que uno que se rompe.
>
>   ```python
>   # esto NO cumple la consigna:
>   schedule="0,15,30,45 * * * *"    # bronze
>   schedule="5,20,35,50 * * * *"    # silver, 5 min despues -- espera, no escucha
>   ```
>
> - **🔎 Como se evalua esto**: el docente hace `docker compose up` en la carpeta del grupo, espera un ciclo y mira si las tres capas tienen datos **sin haber tocado nada**. Si su cron de Bronze es lento (`@daily`, `@hourly`), el docente va a **disparar Bronze a mano una vez** desde la UI: con el encadenado por assets, silver y gold salen detras en segundos y queda demostrado. Con cron escalonado hay que esperar los offsets.
>
>   **Autoverifiquen con el mismo comando antes de entregar** — si esto no da, el docente lo va a ver:
>   ```bash
>   docker exec <su_airflow> airflow dags trigger <su_dag_bronze>
>   # ~1 min despues, sin tocar nada mas:
>   docker exec <su_airflow> airflow dags list-runs <su_dag_silver>
>   ```
>   El `run_id` de la ultima corrida tiene que **empezar con `asset_triggered__`** y estar en `success`. Si empieza con `scheduled__` o `manual__`, o no hay corrida nueva, el encadenado **no** esta funcionando por mas que las tablas tengan datos.
>
>   *(En Airflow 3 el `dag_id` va posicional: `list-runs -d <dag>` no existe. Y van a ver el `logical_date` vacio en esas corridas — es correcto, es la trampa 1 de arriba.)*
> - **Red de seguridad**: agreguen reintentos, asi una capa que arranca antes que su upstream se recupera sola en vez de quedar en rojo:
>   ```python
>   default_args={"retries": 2, "retry_delay": timedelta(minutes=2)}
>   ```
> - Las **tablas** conviene crearlas en el `init.sql` (no dentro del DAG): si silver corre antes que bronze y la tabla no existe, el DAG falla; si ya existe, simplemente lee 0 filas y en el proximo ciclo levanta los datos.
> - Los schemas `bronze`/`silver`/`gold` se crean solos (via `init.sql` montado al postgres).
> - **El acceso a Airflow tiene que estar documentado.** `airflow standalone` genera una
>   contraseña **aleatoria** y la escribe en los logs: si el docente levanta el stack y no
>   puede entrar a la UI, no puede verificar nada. Pongan en el README del grupo el usuario
>   y la contraseña, o configuren un usuario fijo (o sin login). No es un detalle de
>   prolijidad: sin acceso, el TP no se puede corregir.
> - **Healthchecks y orden de arranque**: Postgres tarda unos segundos en aceptar conexiones,
>   y Airflow arranca mas rapido. Sin `healthcheck` en la base y `depends_on: condition:
>   service_healthy` en los servicios que dependen de ella, el arranque es una **carrera**:
>   a veces anda y a veces el primer DAG falla con "connection refused". Que ande en su
>   maquina no alcanza — en la del docente arranca en frio, que es el caso peor.
>
>   ```yaml
>   services:
>     postgres:
>       healthcheck:
>         test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
>         interval: 5s
>         retries: 10
>     airflow:
>       depends_on:
>         postgres: { condition: service_healthy }
>   ```
> - El dashboard arranca, conecta a Postgres y muestra Gold automaticamente.
>
> Una vez levantado, va a haber datos en las tablas en cuestion de minutos/horas segun el schedule.

## Organizacion y entrega

| | |
|---|---|
| **Donde se entrega** | En **este mismo repo**, en una branch del grupo: `tpfinal/G<NN>`. Cada grupo trabaja en su carpeta `TpFinal/grupos/G<NN>/` y entrega via **Pull Request en draft** contra `main`. El paso a paso completo esta en "Como entregar el TP, de principio a fin", al final de este documento. |
| **Politica de APIs** | Pueden repetir la misma API entre grupos (no es excluyente). Si quieren proponer una API fuera de la lista, consultar con el docente. |
| **Fecha de entrega** | **Domingo 15 de noviembre de 2026, hasta las 23:59 (hora Argentina)** — entrega = PR del grupo marcado como **"Ready for review"** en GitHub. |
| **Presentacion oral** | **Jueves 19 de noviembre de 2026, remota (por videollamada)**, **7 a 10 minutos por grupo**, mas una breve ronda de preguntas. Camara prendida durante la exposicion. |

> **Sobre `G<NN>`**: `G` = Grupo, `NN` = numero de 2 digitos (`G01`, `G02`, ..., `G99`). **El numero se pide al docente ANTES de crear la branch** (Paso 0 del instructivo): aparece en la branch, en la carpeta y en el titulo del PR, asi que cambiarlo despues obliga a renombrar las tres. `G00` es el template de referencia, no es una entrega real.

## APIs publicas disponibles

A continuacion se listan APIs gratuitas que pueden utilizarse como fuente de datos. Cada grupo debe elegir **una** API y construir su pipeline completo.

Solo se incluyen APIs con datos que se actualizan al menos cada hora, lo que justifica tener Airflow corriendo y acumulando snapshots continuamente. Para cada API se incluyen **ideas orientativas** de como aplicar Bronze / Silver / Gold — son sugerencias, no requisitos. Cada grupo decide que transformaciones tienen sentido segun su caso.

---

> **Nota:** En clase usaremos **CoinGecko** (api.coingecko.com/api/v3) como ejemplo de referencia para mostrar el pipeline completo. Por lo tanto, **no se puede elegir CoinGecko ni ninguna API de crypto** para el TP.

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

## Criterios de evaluacion

Estos son los cinco criterios con los que se mira el TP. **No es una suma mecanica**: se
parte de aca, pesan los problemas (lo que no arranca, lo que no produce datos) y suman los
extras de la seccion siguiente.

| # | Criterio | Que se mira |
|---|---|---|
| 1 | **Pipeline funcional** (Bronze → Silver → Gold) | Que corra solo y produzca datos reales end-to-end, **encadenado por Assets** (bronze termina → dispara silver → dispara gold). Idempotencia: correrlo dos veces no duplica filas. |
| 2 | **Modelo y transformaciones** | Modelo dimensional (fact/dim), tipado y validacion, deduplicacion, trazabilidad a Bronze. **Aca es donde se sube el techo.** |
| 3 | **Dashboard sobre Gold** | Consume solo `gold.*`, responde preguntas de negocio, y no se rompe cuando todavia no hay datos. |
| 4 | **Containerizacion + arranque automatico** | `docker compose up` y el pipeline corre solo, sin activar DAGs a mano. Airflow 3.1.5, `init.sql`, **healthchecks + `depends_on: service_healthy`** para que el arranque no sea una carrera. Dockerfile propio, `init.sql`. **El mas discriminante.** |
| 5 | **Documentacion y trabajo del grupo** | README completo (API, modelo, como levantar, decisiones, integrantes reales), codigo legible, y un **historial de git con varios autores** y commits repartidos en el tiempo. |

> ⚠️ **Airflow 3.1.5 es obligatorio**, no una sugerencia: la imagen base tiene que ser
> `apache/airflow:3.1.5`. Todo lo que vemos en clase (assets, TaskFlow, la UI) es de la 3.x,
> y el codigo de Airflow 2 **no corre tal cual**: `schedule_interval` ya no existe y
> `webserver` paso a ser `api-server`. Ojo con el peor de los casos: subir la imagen a 3.x
> y dejar el codigo de 2 — el stack no arranca, y eso pega justo en el criterio 4.

### Bonus: lo que sube el techo

Nada de esto es obligatorio y **no hacerlo no resta**. Son las cosas que distinguen un TP
que funciona de uno bien ingenierizado. Todas se ven en alguna clase, con codigo que pueden
mirar en `stack/` (se publica con la clase 02).

> ⚠️ **El encadenado por Assets y la colaboracion en git NO son bonus**: son requisitos, y
> estan en la seccion **Entregables**. Si los buscan aca es porque en una version anterior
> de esta consigna figuraban como opcionales — ya no lo son.

| Bonus | De que se trata | Clase |
|---|---|---|
| **Contratos + calidad de datos** | Un contrato declarativo (YAML) con reglas que **efectivamente corren**, dos severidades (rechaza a cuarentena vs deja pasar marcado) y la tabla de cuarentena con lo que no paso. | 04 |
| **Metricas de calidad en el tiempo** | Una tabla append-only con una fila por (corrida x regla). Un numero suelto no dice nada: "12 rechazos" puede ser lo normal o una catastrofe, y la diferencia solo se ve con la historia al lado. | 04 |
| **Capa semantica** | Vistas `gold.v_*` que encapsulan las metricas del negocio, para que el dashboard no repita SQL. La regla para saber si algo va en una vista: *si la consulta depende de lo que el usuario eligio, no es capa semantica*. | 05 |

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

> **Patron de referencia**: la estructura sigue la misma logica del `stack/` del curso (Airflow 3.1.5 + Postgres 17 Alpine + Streamlit). Pueden mirar `stack/` para inspirarse en el `docker-compose.yml`, `Dockerfile`, `init.sql`, etc. 

> **Por que `G<NN>`?** El numero de grupo tiene que coincidir en la branch y en la carpeta (`tpfinal/G01` ↔ `TpFinal/grupos/G01/`), para que el docente pueda comparar entregas lado a lado al evaluar. Se pide al docente antes de empezar — ver el Paso 0 del instructivo de entrega.

> **Donde corre el stack del grupo?** En la maquina de cada estudiante. Cuando hagan `docker compose up` dentro de `TpFinal/grupos/G<NN>/`, levanta SU propio Postgres, Airflow y Streamlit aislados — no se mezcla con el stack del curso ni con el de otros grupos. **Ojo con los puertos**: si tienen el stack del curso levantado en paralelo, va a haber conflicto en 5432/8080/8501 — apaguen uno antes de levantar el otro, o cambien los mapeos en `docker-compose.yml`.

## Como entregar el TP, de principio a fin

El TP se desarrolla y se entrega **en este mismo repo** (no en un repo propio).
Cada grupo trabaja en su propia branch `tpfinal/G<NN>`, dentro de su carpeta
`TpFinal/grupos/G<NN>/`, y abre un **Pull Request** que oficia de aviso durante
el cuatrimestre y de entrega al final.

> **Branch (rama)** = copia paralela del codigo donde se desarrolla, antes de mergear a `main`.
> **PR (Pull Request)** = propuesta de mergear los commits de una branch a otra; lleva codigo, se puede revisar linea por linea y se mergea cuando esta lista.
>
> 💡 Dudas de Git/GitHub aplicadas al TP (como crear la branch bien, resolver conflictos, trabajar de a varios en la misma rama) → [`git-guia.md`](git-guia.md).

---

### Paso 0 — Armar el grupo y **pedir el numero**

Antes de tocar git: junten el grupo y **pidanle el numero al docente**. El los
asigna mirando cuales ya estan tomados y les confirma el suyo (`G01`, `G02`, ...).

**Esto va primero a proposito**: el numero aparece en el nombre de la branch, en
el de la carpeta y en el titulo del PR. Si lo eligen por su cuenta y dos grupos
agarran el mismo, hay que renombrar las tres cosas.

> `G` = Grupo, `NN` = numero de 2 digitos. La branch y la carpeta **tienen que
> coincidir** (`tpfinal/G01` ↔ `TpFinal/grupos/G01/`): asi el docente compara
> branches lado a lado al evaluar. `G00` es el template de referencia, no es una
> entrega real.

### Paso 1 — Elegir y explorar la API

Una de la lista de [APIs publicas disponibles](#apis-publicas-disponibles), o
propongan otra consultando con el docente (pueden repetir API entre grupos).

Miren **antes de empezar**: endpoints, estructura de la respuesta, rate limits,
si pide API key, y cada cuanto se actualiza (`Refresh`) — ese ultimo dato define
el cron de Bronze en el Paso 5.

### Paso 2 — Disenar el modelo de datos

Que tablas van en bronze, que limpieza en silver, y que `fact` / `dim` /
metricas en gold. No hace falta que sea definitivo: es para saber a donde van.

### Paso 3 — Crear la branch y la carpeta

Con el numero ya asignado, reemplazando `NN` por el suyo:

```bash
git checkout main && git pull
git checkout -b tpfinal/G01              # <- su numero

mkdir -p TpFinal/grupos/G01
cp TpFinal/grupos/G00/README.md TpFinal/grupos/G01/README.md   # el template
# editenlo: integrantes, API elegida, idea Gold

git add TpFinal/grupos/G01/
git commit -m "tpfinal/G01: setup inicial (API: OpenAQ)"
git push -u origin tpfinal/G01
```

La estructura completa de archivos que va adentro de esa carpeta esta en
[Esqueleto de entrega](#esqueleto-de-entrega), mas arriba. Ahora alcanza con el
README.

### Paso 4 — Abrir el PR **en draft**

Contra `main`, desde la branch recien pusheada.

- **Titulo exacto**: `TP Final - G<NN> - <API>` — ej: `TP Final - G01 - OpenAQ`
- **Body**:
  - **Integrantes**: nombre completo + usuario de GitHub de cada uno.
  - **API elegida**: nombre + URL.
  - **Idea Gold** (1-2 oraciones): que pregunta de negocio responde el dashboard.

Queda en **draft** hasta la entrega. Cada `git push` lo actualiza solo: no abren
uno nuevo nunca mas.

### Paso 5 — Construir el pipeline

1. **`docker-compose.yml`** con los 4 servicios: postgres (warehouse), postgres
   (airflow), airflow y dashboard. Inspirense en
   [`stack/docker-compose.yml`](../../stack/docker-compose.yml), disponible desde
   la clase 02.
2. **Los DAGs, encadenados por Assets** (minimo uno por capa):
   - **Bronze** con cron segun el `Refresh` de su API, y `outlets=[TU_ASSET]`.
   - **Silver** con `schedule=[TU_ASSET]` (**sin cron**) y su propio `outlets=[...]`.
   - **Gold** con `schedule=[ASSET_DE_SILVER]` (**sin cron**).
   - Los tres con `is_paused_upon_creation=False`, para que arranquen solos.

   El cron escalonado (`:00` / `:05` / `:10`) **no cumple la consigna**: esta
   explicado en *"UN SOLO CRON, EN EL BORDE"*, mas arriba. La implementacion de
   referencia son los DAGs del curso (clases 03 a 05).
3. **El dashboard en Streamlit, sobre las tablas Gold**. Bronze y Silver no se
   visualizan: son backend del pipeline.

Commits chicos y frecuentes, de todos los integrantes. **El historial es parte
de la entrega** y se mira.

### Paso 6 — Documentar

En `TpFinal/grupos/G<NN>/README.md`: API elegida, modelo de datos, como levantar
el stack y las decisiones tecnicas que tomaron (por que esa limpieza, por que
ese modelo dimensional, que dejaron afuera).

### Paso 7 — Entregar

**Domingo 15 de noviembre, hasta las 23:59 (hora Argentina).** En el PR, click en
**"Ready for review"**: eso convierte el draft en PR formal, y **esa accion es la
entrega**.

### Paso 8 — Presentar

**Jueves 19 de noviembre, remota (videollamada)**, 7 a 10 minutos por grupo con
el dashboard corriendo en sus maquinas, mas una ronda corta de preguntas. Camara
prendida. Que mostrar y como:
[`consigna_presentacion.html`](consigna_presentacion.html).
