# TP Final - G00 (Template del README)

> **Template del README del grupo.** Copienlo a `TpFinal/grupos/G<NN>/README.md` y
> completen cada seccion. `G00` no es una entrega real.

---

## Integrantes

- Mauricio Genta (@5y5F4il)
- Erik Daniel Garcia (@ErikDanielGar)
- Ivan Lopez (@IvanLpp)
- Christian Rojas (@Christian-Rojas-Rodriguez)

## API elegida

- **Nombre**: `Citybikes — Bicicletas públicas`
- **URL**: `api.citybik.es/v2`
- **Descripcion**: `<breve explicación de que devuelve la API>`
- **Auth**: `sin auth`
- **API key**: `no necesita`
- **Refresh**: `2-5 minutos`

## Modelo de datos

### Bronze

`<que tablas crudas guardan + columnas + metadatos de auditoria (ingested_at, source, etc.)>`

### Silver

DAG `citybikes_silver` (`dags/02-silver/citybikes_silver.py`). No tiene cron: arranca solo cuando `citybikes_bronze` termina de cargar (asset `bronze_citybikes`) y, al terminar, emite `silver_citybikes`.

Bronze guarda todo como texto, tal cual vino de la API. Silver lo deja limpio, tipado, sin duplicados y validado contra el contrato (`data/contracts/citybikes_stations.yaml`), con el mismo grano: una fila por estación y snapshot.

**Tablas**

| Tabla | Grano | Contenido |
|---|---|---|
| `silver.citybikes_stations` | estación × snapshot. PK `(snapshot_ts, network_id, station_id)` | Las columnas del contrato, tipadas |
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
| auditoría | `ingested_at` (carga en bronze), `_processed_at`, `_source_table`, `_contract_version`, `_quality_flags` |

**Transformaciones**

1. **Limpieza (SQL):** recorte de espacios y texto vacío a `NULL`, sin tocar mayúsculas. Se reparan las fechas de la API: `source_timestamp` llega como `...+00:00Z` (offset y `Z` a la vez) y `source_last_updated` llega sin zona (está en UTC).
2. **Deduplicación (SQL):** una fila por `(network_id, station_id, snapshot_ts)`, la de carga más reciente (`DISTINCT ON ... ORDER BY ingested_at DESC`).
3. **Tipado y validación fila a fila:** un modelo Pydantic generado desde el `schema` del contrato convierte cada valor a su tipo y controla rangos (latitud entre -90 y 90, cantidades no negativas). La fila que no cumple va a cuarentena con el motivo.
4. **Reglas de calidad sobre el lote** (`quality_rules` del contrato), con dos severidades:
   - `error`: la fila va a cuarentena.
   - `warning`: la fila pasa, marcada en `_quality_flags`. Hoy hay dos: `estacion_alquilando` (la estación no está alquilando) y `operador_fresco` (el dato del operador tiene más de 60 minutos).
5. **Carga idempotente:** en una sola transacción se borran y se vuelven a insertar los snapshots de la corrida. Reprocesar un snapshot no duplica filas ni toca los demás.

Ningún dato se descarta: lo que no pasa queda en cuarentena, y las estaciones inactivas quedan marcadas para que gold decida si las usa.

**Qué procesa cada corrida:** los snapshots que están en bronze y todavía no en silver ni en cuarentena (últimas 48 horas). Si una corrida falla, la siguiente levanta lo que quedó pendiente.

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

`<modelo dimensional: fact_X + dim_Y, y que pregunta de negocio responde el dashboard>`

## Como levantar el stack

> ⚠️ **Esta API necesita una key.** Antes de levantar, completa `MI_API_KEY` en el
> `.env` con tu propia key — se saca gratis en `<link para pedirla>`. La que viene
> en el repo es un placeholder: no sirve.
>
> *(Si su API no necesita key, borren esta nota.)*

```bash
cd TpFinal/grupos/G<NN>/      # ej: cd TpFinal/grupos/G01/
docker compose up -d --build   # el .env ya viene en el repo
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8081 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` (user/pass en `.env`)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
