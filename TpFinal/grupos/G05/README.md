# TP Final - G05 - USGS Earthquakes



---

## Integrantes

- Juan Cruz Goñi (@JuanCruzGoni)
- Uriel Fenley (@urifen)
- Mía Arcondo (@michuarcondo)
- Julián Mesina (@julii00m)
- Agustín Fiorini (@agustinfiorini06-max)


## API elegida

- **Nombre**: USGS Earthquakes — Sismos
- **URL**: https://earthquake.usgs.gov/fdsnws/event/1/
- **Descripcion**: This is an implementation of the FDSN Event Web Service Specification, and allows custom searches for earthquake information using a variety of parameters.
- *Auth*: Sin auth
- *API key*: <no necesita>
- *Refresh*: Real-time

## Modelo de datos

### Bronze

`bronze.sismos_crudo` conserva las observaciones recibidas de USGS. El grano
es una versión por sismo (`id`, `updated_epoch`), con los campos del GeoJSON y
auditoría (`ingested_at`, `source`, `run_id`). El archivo GeoJSON de cada
respuesta se guarda en `data/raw/sismos/`.

El DAG `00_backfill_sismos_30_dias` trae los últimos 30 días. Corre una sola
vez, solo, apenas se levanta el stack. Divide los intervalos si una consulta
alcanza el límite de 20.000 eventos de FDSN. Luego `01_bronze_sismos` consulta
el feed semanal cada hora.

### Silver

`silver.sismos_limpio` contiene una fila por `id`, elegida por el `updated_epoch`
más reciente. Solo incluye eventos `earthquake` con magnitud, fecha y
coordenadas válidas. Las versiones rechazadas se conservan una sola vez en
`silver.sismos_cuarentena`. El campo `tsunami` conserva `0`, `1` o `NULL`.
La zona se deriva de `place` y es aproximada, no una región normalizada.

### Gold

`gold.fact_sismo` tiene una fila por evento y referencias a `gold.dim_fecha` y
`gold.dim_zona`. El DAG `03_gold_sismos` reconstruye el modelo y comprueba que
cada hecho tenga sus dimensiones. Las vistas para consumo son
`gold.v_actividad_mensual`, `gold.v_actividad_zona`, `gold.v_mapa_sismos` y
`gold.v_sismos_tsunami`.

El dashboard responde cómo varía la actividad por mes y zona, dónde ocurrieron
los eventos y cuáles tienen el flag `tsunami=1` publicado por USGS. El esquema
[GeoJSON de USGS](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
lo publica como entero; el proyecto conserva `0`, `1` o `NULL` y no lo
interpreta como una alerta ni una predicción.


## Como levantar el stack

```bash
cd TpFinal/grupos/G05/
docker compose up -d --build
```

No hace falta activar nada a mano. Al levantar el stack:

1. `00_backfill_sismos_30_dias` corre una sola vez y trae los últimos 30 días.
2. `01_bronze_sismos` corre enseguida y después cada hora.
3. Cada carga de Bronze dispara Silver, y Silver dispara Gold al completar.

En unos minutos el dashboard ya muestra los datos.

**Accesos**:
- Airflow UI: http://localhost:8080. No pide usuario ni contraseña: todos
  entran como admin (`SIMPLE_AUTH_MANAGER_ALL_ADMINS=True` en el `.env`).
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` / DB: `InfraCienciaDatos` / usuario `admin` /
  contraseña `admin`

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # BORRA los volumenes y todos los datos (solo reset intencional)
```

## Como comprobar que anda

Después de levantar el stack, en unos 5 minutos:

**1. Airflow** (http://localhost:8080): los 4 DAGs aparecen activos y con su
última corrida en verde.

| DAG | Qué tiene que pasar |
|---|---|
| `00_backfill_sismos_30_dias` | Una sola corrida, la de los 30 días. |
| `01_bronze_sismos` | Una corrida al arrancar y después una por hora. |
| `02_silver_sismos` | Una corrida después de cada carga de Bronze. |
| `03_gold_sismos` | Una corrida después de cada Silver. |

Si alguna tarea queda en rojo, se puede abrir y ver el log. La primera tarea
de Bronze reintenta sola si falla porque Airflow todavía estaba arrancando.

**2. Dashboard** (http://localhost:8501):

- **Inicio**: total de sismos, días con actividad (alrededor de 30), zonas y
  eventos marcados con tsunami.
- **Actividad sísmica**: sismos por mes y las zonas con más actividad.
- **Mapa de sismos**: dónde ocurrió cada evento.
- **Sismos marcados con tsunami**: la lista de eventos con `tsunami=1`.

Si el inicio dice que Gold todavía no tiene datos, falta que termine
`03_gold_sismos`.

**3. Postgres** (opcional, con cualquier cliente SQL):

```sql
-- Cuántos días y qué período cubre Gold
SELECT COUNT(DISTINCT fecha), MIN(fecha), MAX(fecha) FROM gold.fact_sismo;

-- Cuántos sismos quedan en cada capa
SELECT 'bronze', COUNT(*) FROM bronze.sismos_crudo
UNION ALL SELECT 'silver', COUNT(*) FROM silver.sismos_limpio
UNION ALL SELECT 'gold', COUNT(*) FROM gold.fact_sismo;
```

Bronze tiene más filas que Silver porque guarda cada versión que publicó USGS
de un mismo sismo; Silver se queda con la más reciente.

Los JSON que se guardan en `data/raw/` quedan en cada máquina y no se suben al
repo (están en el `.gitignore`).

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
