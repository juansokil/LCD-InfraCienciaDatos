# TP Final - G08

---

## Integrantes

- Mauricio Genta (@5y5F4il)
- Erik Daniel Garcia (@ErikDanielGar)
- Ivan Lopez (@IvanLpp)
- Christian Rojas (@Christian-Rojas-Rodriguez)

## API elegida

- **Nombre**: `Citybikes — Bicicletas públicas`
- **URL**: `api.citybik.es/v2`
- **Descripcion**: estado en tiempo real de los sistemas de bicicletas públicas del mundo. Por cada red (`/networks/{id}`) devuelve sus estaciones con bicis disponibles, anclajes libres, coordenadas y un bloque `extra` propio de cada operador (capacidad, si alquila/recibe, última actualización).
- **Auth**: `sin auth`
- **API key**: `no necesita`
- **Refresh**: `2-5 minutos`

## Preguntas de negocio

El pipeline toma un snapshot de las estaciones cada 5 minutos en tres redes argentinas: EcoBici (CABA), Mi Bici Tu Bici (Rosario) y Bike Itaú Nordelta. Con eso, gold responde:

1. **¿Qué estaciones se saturan y cuándo?** Una estación está saturada cuando se usaron todas sus bicis (`free_bikes = 0`). Se mira por estación, hora del día y día de la semana.
2. **¿Cómo varía la saturación por zona?** Barrio y comuna en CABA; ciudad en el resto (ver [Zonas](#zonas)).
3. **¿Cuánto dura la saturación?** Cada vez que una estación se queda sin bicis empieza un episodio, que termina cuando vuelve a tener alguna. Se mide cuánto duran los episodios por estación, zona y franja horaria: si una estación vacía se repone en 5 minutos o en 2 horas.
4. **¿Qué zonas se vacían y qué zonas se llenan, y en qué horario?** Compara las dos caras de la saturación: sin bicis (no se puede retirar) y sin anclajes libres (`empty_slots = 0`, no se puede devolver). El horario se mira con la ocupación promedio por zona y hora (qué parte de los anclajes operativos tiene bici), que muestra la tendencia aunque la zona no llegue a vaciarse o llenarse del todo. Debería mostrar el ida y vuelta diario entre barrios residenciales y zonas de oficinas.
5. **¿Cuánto uso tiene cada estación y en qué horario?** Se suma cuánto cambia la cantidad de bicis entre un snapshot y el siguiente, como estimación de retiros y devoluciones. Si en 5 minutos sale una bici y entra otra, la cuenta no lo ve, así que el número es un **mínimo**. Sirve para distinguir una estación vacía porque se usa mucho de una vacía porque nadie la repone.
6. **¿Qué parte de la capacidad está realmente disponible?** Anclajes fuera de servicio, estaciones que no alquilan y estaciones que no reportan hace rato, por red y zona.

Criterios comunes:

- Las filas marcadas en `_quality_flags` (estación que no alquila o dato del operador viejo) no cuentan como saturación en las preguntas 1 a 5: una estación caída no es una estación sin bicis. Son justamente el tema de la pregunta 6.
- La ocupación se calcula sobre la capacidad operativa (`free_bikes + empty_slots`), no sobre `slots`, porque en buena parte de las filas hay anclajes fuera de servicio.
- Los horarios van en hora de Argentina (`snapshot_local`).
- Los porcentajes se calculan sobre los snapshots que efectivamente llegaron, no sobre 288 por día: si una red falla en una corrida, ese snapshot no existe.

## Modelo de datos

### Bronze

DAG `citybikes_bronze` (`dags/01-bronze/citybikes_bronze.py`). Corre cada 5 minutos (`*/5 * * * *`), arranca solo al levantar el stack y, al terminar, emite el asset `bronze_citybikes`, que dispara silver.

Bronze guarda lo que mandó la API, sin interpretar: todas las columnas son `text`. Las redes a consultar salen del contrato (`delivery.networks`).

**Flujo de cada corrida**

1. **Descarga:** un GET por red a `https://api.citybik.es/v2/networks/{network_id}`, en paralelo (una tarea por red, con 3 reintentos).
2. **Zona raw:** la respuesta se guarda tal cual, comprimida, en `data/raw/citybikes/<red>/ds=<fecha>/<HHMMSS>.json.gz`. Es la copia exacta de lo que llegó y permite recargar bronze sin volver a llamar a la API.
3. **Validación de forma** contra el contrato: que exista `network.stations`, que haya al menos una estación y que cada estación traiga los campos obligatorios. Si no cumple, el archivo se mueve a `data/quarantine/citybikes/...` junto con un `.error.json` con el motivo, y esa red no se carga en esta corrida.
4. **Aplanado y carga:** cada estación pasa a una fila. Los campos de `extra` que usa el modelo van a columnas propias, y `extra` completo queda en `extra_json`. Si ninguna red pasó la validación, la corrida falla y silver no se dispara.
5. **Carga idempotente:** en una sola transacción se borran las filas del mismo `run_id` y se vuelven a insertar. Reintentar una corrida no duplica.

**Tablas**

| Tabla | Grano | Contenido |
|---|---|---|
| `bronze.citybikes_stations` | estación × corrida | Datos de cada estación + `extra_json` |
| `bronze.citybikes_networks` | red × corrida | Nombre, ciudad, país, coordenadas, empresa y GBFS de cada red |

**Columnas de `bronze.citybikes_stations`** (todas `text`)

| Origen en la API | Columnas |
|---|---|
| `network.id` | `network_id` |
| `stations[]` | `station_id`, `name`, `latitude`, `longitude`, `source_timestamp`, `free_bikes`, `empty_slots` |
| `stations[].extra` | `station_uid`, `address`, `post_code`, `slots`, `normal_bikes`, `ebikes`, `renting`, `returning`, `virtual`, `source_last_updated`, y el objeto completo en `extra_json` (JSON) |

**Columnas de `bronze.citybikes_networks`** (todas `text`): `network_id`, `name`, `city`, `country`, `latitude`, `longitude`, `company_json`, `gbfs_href`, `station_count`.

**Auditoría** (en las dos tablas)

| Columna | Tipo | Qué es |
|---|---|---|
| `snapshot_ts` | `timestamptz` | Momento lógico de la corrida. Es el mismo en todos los reintentos, y es el que usan silver y gold como "cuándo" |
| `ingested_at` | `timestamptz` | Cuándo se escribió la fila. Cambia si la corrida se repite |
| `run_id` | `text` | Corrida de Airflow que la cargó |
| `raw_path` | `text` | Archivo de la zona raw del que salió la fila |
| `contract_version` | `text` | Versión del contrato con que se validó |
| `source` | `text` | `citybikes_api` |

### Silver

DAG `citybikes_silver` (`dags/02-silver/citybikes_silver.py`). No tiene cron: arranca solo cuando `citybikes_bronze` termina de cargar (asset `bronze_citybikes`) y, al terminar, emite `silver_citybikes`.

Bronze guarda todo como texto, tal cual vino de la API. Silver lo deja limpio, tipado, sin duplicados y validado contra el contrato (`data/contracts/citybikes_stations.yaml`), con el mismo grano: una fila por estación y snapshot.

**Tablas**

| Tabla | Grano | Contenido |
|---|---|---|
| `silver.citybikes_stations` | estación × snapshot. PK `(snapshot_ts, network_id, station_id)` | Las columnas del contrato, tipadas, más las derivadas |
| `silver.citybikes_station_zone` | estación. PK `(network_id, station_id)` | Zona de cada estación según sus coordenadas |
| `silver.citybikes_networks` | red × snapshot. PK `(snapshot_ts, network_id)` | Nombre, ciudad, país y coordenadas de cada red |
| `silver.quarantine_citybikes_stations` | fila rechazada | Las mismas columnas en texto + `quarantine_reason` |
| `silver.quality_runs` | regla × corrida (solo se agrega, nunca se borra) | Filas evaluadas y violaciones de cada regla |

**Columnas de `silver.citybikes_stations`**

| Tipo | Columnas |
|---|---|
| `text` | `network_id`, `station_id`, `name`, `station_uid`, `address`, `post_code` |
| `double precision` | `latitude`, `longitude` |
| `integer` | `free_bikes`, `empty_slots`, `slots`, `normal_bikes`, `ebikes` |
| `boolean` | `renting`, `returning`, `virtual` |
| `timestamptz` (UTC) | `source_timestamp`, `source_last_updated`, `snapshot_ts` |
| derivadas | `station_number`, `station_name`, `docks_fuera_servicio`, `ocupacion`, `snapshot_local` (ver paso 5) |
| auditoría | `ingested_at` (carga en bronze), `_processed_at`, `_source_table`, `_contract_version`, `_quality_flags` |

**Transformaciones**

1. **Limpieza (SQL):** recorte de espacios y texto vacío a `NULL`, sin tocar mayúsculas. Se reparan las fechas de la API: `source_timestamp` llega como `...+00:00Z` (offset y `Z` a la vez) y `source_last_updated` llega sin zona (está en UTC).
2. **Deduplicación (SQL):** una fila por `(network_id, station_id, snapshot_ts)`, la de carga más reciente (`DISTINCT ON ... ORDER BY ingested_at DESC`).
3. **Tipado y validación fila a fila:** un modelo Pydantic generado desde el `schema` del contrato convierte cada valor a su tipo y controla rangos (latitud entre -90 y 90, cantidades no negativas). La fila que no cumple va a cuarentena con el motivo.
4. **Reglas de calidad sobre el lote** (`quality_rules` del contrato), con dos severidades:
   - `error`: la fila va a cuarentena.
   - `warning`: la fila pasa, marcada en `_quality_flags`. Hoy hay dos: `estacion_alquilando` (la estación no está alquilando) y `operador_fresco` (el dato del operador tiene más de 60 minutos).
5. **Columnas derivadas** (no vienen de la API; silver las calcula para que gold no repita la cuenta):
   - `station_number` (`integer`): el número que EcoBici y Nordelta ponen al principio del nombre (`001 - ADUANA` → `1`).
   - `station_name` (`text`): el nombre sin ese número. Los nombres que llegan todo en mayúsculas (la mitad de EcoBici) pasan a mayúscula inicial, con artículos y preposiciones en minúscula y las siglas conocidas en mayúscula (`FACULTAD DE DERECHO` → `Facultad de Derecho`, `UBA EXACTAS` → `UBA Exactas`). Los que ya vienen mezclados se respetan, porque ahí la API trae siglas y abreviaturas bien escritas (`CC Echesortu`, `Fac. de Ingeniería`). `name` queda tal cual vino.
   - `docks_fuera_servicio` (`integer`): `slots - (free_bikes + empty_slots)`, nunca negativo.
   - `ocupacion` (`double precision`, 0 a 1): `free_bikes / (free_bikes + empty_slots)`, sobre la capacidad operativa. `NULL` si la estación no tiene ningún anclaje operativo.
   - `snapshot_local` (`timestamp`, sin zona): `snapshot_ts` en hora de Argentina (`America/Argentina/Buenos_Aires`).
6. **Carga idempotente:** en una sola transacción se borran y se vuelven a insertar los snapshots de la corrida. Reprocesar un snapshot no duplica filas ni toca los demás.

<a id="zonas"></a>**Zonas** (tarea `asignar_zonas` → `silver.citybikes_station_zone`)

Cada estación se ubica en una zona cruzando sus coordenadas con polígonos GeoJSON (`shapely`, sin PostGIS). Las capas están en `data/geo/` y se configuran en `CAPAS_ZONA`, en `dags/common/zonas.py`.

| Red | Capa | Zona | Zona padre |
|---|---|---|---|
| EcoBici (CABA) | `caba_barrios.geojson`, de [Buenos Aires Data](https://data.buenosaires.gob.ar/dataset/barrios) | barrio | comuna |
| Mi Bici Tu Bici (Rosario) | todavía sin capa | ciudad | — |
| Bike Itaú Nordelta | sin capa (es una sola zona) | ciudad | — |

- Una fila por estación, no por snapshot: las estaciones no se mueven. Gold la une con `silver.citybikes_stations` por `(network_id, station_id)`.
- Columnas: `network_id`, `station_id`, `latitude`, `longitude`, `ciudad`, `zona`, `zona_padre`, `zona_nivel` (`barrio` o `ciudad`), `capa` (archivo usado, o `fallback`), `snapshot_ts` (snapshot del que sale la posición) y `_processed_at`. Los nombres de zona se guardan tal como vienen en la capa.
- Una estación en la costa o sobre una avenida límite puede caer apenas afuera de los polígonos: hasta unos 200 m se le asigna el más cercano. Más lejos, o si su red no tiene capa, la zona es la ciudad (`zona_nivel = 'ciudad'`).
- En cada corrida se recalculan las estaciones del run, pero solo se escribe la que es nueva o cambió, y nunca con una posición más vieja que la guardada (si se procesa un snapshot atrasado, no pisa una reubicación). Para sumar los distritos de Rosario alcanza con dejar su GeoJSON en `data/geo/` y agregar la entrada en `CAPAS_ZONA`: la corrida siguiente reasigna sola.
- Corre en paralelo con `cargar_redes` y antes de `limpiar_y_cargar`, para que gold ya encuentre la zona de una estación nueva cuando llega el asset.

Ningún dato se descarta: lo que no pasa queda en cuarentena, y las estaciones inactivas quedan marcadas para que gold decida si las usa.

**Qué procesa cada corrida:** los snapshots que están en bronze y todavía no en silver ni en cuarentena (últimas 48 horas), y los que se cargaron antes de que existieran las columnas derivadas (se reprocesan una vez). Si cambia el cálculo de una columna derivada, los snapshots ya cargados no se corrigen solos: hay que forzar su reproceso poniendo `snapshot_local` en `NULL` (dentro de la ventana de 48 horas) y dejar correr el DAG. Si una corrida falla, la siguiente levanta lo que quedó pendiente.

**Para revisar la calidad**

```sql
-- rechazos por motivo
SELECT quarantine_reason, count(*)
FROM silver.quarantine_citybikes_stations
GROUP BY 1 ORDER BY 2 DESC;

-- reglas de la ultima corrida
SELECT regla, severidad, filas_evaluadas, violaciones
FROM silver.quality_runs
WHERE run_ts = (SELECT max(run_ts) FROM silver.quality_runs);
```

### Gold

DAG `citybikes_gold` (`dags/03-gold/citybikes_gold.py`). No tiene cron: arranca cuando silver emite `silver_citybikes` y, al terminar, emite `gold_citybikes`. Todo el cálculo es SQL dentro de Postgres; el dashboard lee **solo** el schema `gold`.

**Modelo dimensional**

```
                dim_fecha (fecha)
                     │
dim_estacion ──┬── fact_estacion_hora        estación × día × hora   → P1, P2, P4, P5, P6
(network_id,   ├── fact_episodio_sin_bicis   episodio cerrado        → P3
 station_id)   └── fact_capacidad_actual     estación (última foto)  → P6
```

| Tabla | Grano / PK | Contenido |
|---|---|---|
| `gold.dim_estacion` | estación. PK `(network_id, station_id)` | Nombre limpio, red (`red_nombre`), ciudad, `zona` / `zona_padre` / `zona_nivel` (de `silver.citybikes_station_zone`), coordenadas, `slots`, primera y última observación |
| `gold.dim_fecha` | día local con datos. PK `fecha` | Día de la semana (ISO, 1 = lunes), nombre y `tipo_dia` (`Hábil` / `Fin de semana`) |
| `gold.fact_estacion_hora` | estación × día × hora local. PK `(network_id, station_id, fecha, hora)` | **Conteos** de snapshots: totales, válidos, sin bicis, sin anclajes, que no alquilan, que no reciben, con operador viejo; promedios de bicis, ocupación y anclajes fuera de servicio; pares comparados, retiros, devoluciones y bicis movidas por el operador |
| `gold.fact_episodio_sin_bicis` | episodio. PK `(network_id, station_id, inicio_ts)` | Inicio (UTC y local), fin, hora de inicio, snapshots vacíos y duración en minutos |
| `gold.fact_capacidad_actual` | estación. PK `(network_id, station_id)` | Último snapshot de cada estación: bicis, anclajes libres, `slots`, anclajes fuera de servicio, `alquila`, `recibe`, `operador_viejo`, `sin_dato_operador` |
| `gold._modelo` | — | Versión del modelo (ver abajo) |

**Reglas de cálculo**

- **Snapshot válido** (base de P1 a P5): `renting = true`, `returning` distinto de `false` y `_quality_flags` vacío. Una estación caída no es una estación saturada; esas filas se cuentan aparte para P6.
- Los hechos guardan **conteos**, no porcentajes: el dashboard suma numerador y denominador al nivel que muestra (zona, red, día) y recién ahí divide. Así los porcentajes son sobre los snapshots que efectivamente llegaron.
- **Episodio sin bicis** (P3): empieza en el primer snapshot con `free_bikes = 0` precedido por uno con bicis y termina en el primer snapshot con bicis. Los dos bordes tienen que estar a ≤ 10 minutos (dos ciclos); si hay un hueco en el medio, el episodio no se cuenta. Los episodios abiertos se cargan cuando la estación se repone (se identifican por su fin); se miden episodios de hasta 7 días (`MAX_EPISODIO_DIAS`).
- **Uso** (P5): diferencia de `free_bikes` entre snapshots válidos consecutivos a ≤ 10 minutos. Las bajas son retiros y las subas, devoluciones. Es un mínimo: lo que entra y sale dentro del mismo intervalo no se ve. Un cambio de 5 o más bicis de golpe se toma como reposición del operador (`rebalanceo_bicis`) y no como uso (heurística, constante `UMBRAL_REBALANCEO`). El dashboard normaliza por **tiempo observado**: cada par de snapshots cubre 5 minutos de una estación, así que la tasa es cambios ÷ (pares × 5 min). Por estación se muestra el uso por hora observada; para la red, la tasa de cada hora del día × estaciones, sumada sobre las horas con datos (sin extrapolar la tarde a la madrugada). Un día con una sola hora de datos no cuenta como un día entero.
- **Capacidad actual** (P6): la antigüedad del último snapshot se calcula al consultar (contra `now()`), no en gold. Las estaciones que la API dejó de informar hace más de un día respecto del último snapshot de su red se listan aparte como probables bajas.

**Carga incremental e idempotente**

- Cada corrida recalcula los días locales desde hace 2 días (silver procesa snapshots atrasados hasta 48 h), o desde el último día cargado si gold estuvo parado más tiempo, con `DELETE` + `INSERT` en una transacción por tabla. Se lee un día extra de silver para que la comparación con el snapshot anterior funcione en el borde.
- Si gold está vacío, recalcula todo el histórico de silver.
- `dim_estacion` se actualiza por upsert (nunca la pisa un snapshot más viejo); `dim_fecha` y `fact_capacidad_actual` se reconstruyen enteras (son chicas).
- Si cambia el modelo, se sube `VERSION_MODELO` en el DAG: la corrida siguiente borra las tablas gold y las reconstruye.

**Qué responde cada página del dashboard**

| Página | Pregunta | Fuente |
|---|---|---|
| 1 · Sin bicis por estación | P1: mapa de calor día × hora de la red y de cada estación, ranking con mínimo de snapshots | `fact_estacion_hora` |
| 2 · Sin bicis por zona | P2: comparación entre ciudades y desglose por barrio / comuna en CABA | `fact_estacion_hora` |
| 3 · Duración de episodios | P3: mediana y percentil 90 por zona, estación y hora de inicio | `fact_episodio_sin_bicis` |
| 4 · Vaciamiento y llenado | P4: sin bicis vs sin anclajes por zona, y ocupación por zona y hora | `fact_estacion_hora` |
| 5 · Uso por estación | P5: perfil horario, ranking y cruce uso × saturación (vacía por uso o por falta de reposición) | `fact_estacion_hora` |
| 6 · Capacidad disponible | P6: estado actual por red y zona, y evolución diaria | `fact_capacidad_actual`, `fact_estacion_hora` |
| 7 · Mapa | P1, P4 y P5 en el mapa: cada estación coloreada por tiempo sin bicis, sin anclajes, ocupación o uso, con filtro de días y franja horaria | `fact_estacion_hora`, `dim_estacion` |

```sql
-- estaciones mas saturadas de EcoBici entre 8 y 10 hs de dias habiles
SELECT d.station_name,
       round(100.0 * sum(f.snapshots_sin_bicis) / nullif(sum(f.snapshots_validos), 0), 1) AS pct
FROM gold.fact_estacion_hora f
JOIN gold.dim_estacion d USING (network_id, station_id)
JOIN gold.dim_fecha df USING (fecha)
WHERE f.network_id = 'ecobici-buenos-aires' AND f.hora BETWEEN 8 AND 9 AND df.tipo_dia = 'Hábil'
GROUP BY d.station_name
ORDER BY pct DESC NULLS LAST
LIMIT 10;
```

## Puntos a revisar

- **La ocupación por zona pondera igual a todas las estaciones, sin importar su tamaño** (P4, página 4). Gold guarda `ocupacion_promedio` (promedio de `free_bikes / (free_bikes + empty_slots)` por estación y hora), y el dashboard lo promedia por zona ponderando por snapshots, no por capacidad. Una estación de 10 anclajes al 0% y una de 40 al 100% dan 50%, aunque en la zona hay 40 bicis sobre 50 anclajes (80%). El gráfico responde "cómo está en promedio una estación de la zona", no "qué parte de los anclajes de la zona tiene bici". Para lo segundo, `fact_estacion_hora` tendría que guardar bicis y capacidad operativa sumadas (`sum(free_bikes)` y `sum(free_bikes + empty_slots)`) y el dashboard dividir una suma por la otra. Requiere subir `VERSION_MODELO` y reconstruir gold.
- **El ranking de uso por estación mezcla horarios distintos según la estación** (P5, página 5). La tasa de cada estación es Σ (retiros + devoluciones) ÷ horas observadas, sumando todos los días y horas con datos. Si una estación se observó sobre todo de madrugada y otra sobre todo en hora pico, la segunda sale con más uso aunque no lo tenga: el ranking compara mezclas horarias distintas. Con pocos días y huecos de cobertura puede pesar. Alternativa: calcular la tasa por hora del día de cada estación y combinarlas con el mismo peso horario para todas, como ya hace la estimación de la red en esa página.

## Como levantar el stack

La API de CityBikes no necesita key: el stack levanta sin completar nada.

```bash
cd TpFinal/grupos/G08/
docker compose up -d --build   # el .env ya viene en el repo
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8081 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5434` (user/pass en `.env`; se publica en 5434 para no chocar con un Postgres local)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

Sigue el **"Esqueleto de entrega"** de [`TpFinal/README.md`](../../README.md), con algunas carpetas propias que los DAGs usan con rutas fijas.

```
TpFinal/grupos/G08/
├── README.md
├── docker-compose.yml              # warehouse + airflow_db + airflow + dashboard
├── Dockerfile                      # imagen Airflow custom (apache/airflow:3.1.5)
├── Dockerfile.postgres             # Postgres 17 con init.sql adentro
├── init.sql                        # CREATE SCHEMA bronze, silver, gold
├── init-airflow.sh                 # arranque de Airflow standalone (usuario admin/admin)
├── requirements.txt
├── .env                            # se versiona: credenciales de juguete
├── .gitignore
├── dags/
│   ├── 01-bronze/
│   │   └── citybikes_bronze.py     # API -> zona raw -> bronze
│   ├── 02-silver/
│   │   └── citybikes_silver.py     # limpieza, tipado, contrato, cuarentena, zonas
│   ├── 03-gold/
│   │   └── citybikes_gold.py       # modelo dimensional (dim_* + fact_*)
│   └── common/                     # codigo compartido (fuera del parseo de Airflow por .airflowignore)
│       ├── assets.py               # assets que encadenan bronze -> silver -> gold
│       ├── contracts.py            # lectura del contrato, modelo Pydantic y quality_rules
│       ├── derivadas.py            # columnas derivadas de silver
│       └── zonas.py                # asignacion de zona por coordenadas
├── data/                           # montado en /opt/airflow/data
│   ├── contracts/
│   │   └── citybikes_stations.yaml # data contract: schema, reglas y redes a consultar
│   ├── geo/
│   │   └── caba_barrios.geojson    # poligonos para asignar zona en silver
│   ├── raw/                        # payloads de la API (.json.gz), no se versionan
│   └── quarantine/                 # payloads rechazados por bronze, no se versionan
├── credentials/                    # vacia; no se versiona
└── dashboard/                      # Streamlit sobre gold (http://localhost:8501)
    ├── Dockerfile
    ├── app.py                      # portada: preguntas, paginas y resumen
    ├── db.py                       # conexion, consultas cacheadas y espera de gold
    ├── comun.py                    # selectores y helpers compartidos por las paginas
    └── pages/                      # una pagina por pregunta de negocio (1 a 6)
```
