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

El DAG manual `00_backfill_sismos_30_dias` trae los últimos 30 días. Divide
los intervalos si una consulta alcanza el límite de 20.000 eventos de FDSN.
Luego `01_bronze_sismos` consulta el feed semanal cada hora.

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
# Esperar a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8080 (sin autenticación)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` / DB: `InfraCienciaDatos` / `admin`

**Primera ejecución**:

1. En Airflow, ejecutar manualmente `00_backfill_sismos_30_dias` una sola vez.
2. Ese DAG carga Bronze y dispara Silver; Silver dispara Gold al completar.
3. Las ingestas posteriores corren cada hora con `01_bronze_sismos`.

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # BORRA los volumenes y todos los datos (solo reset intencional)
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
