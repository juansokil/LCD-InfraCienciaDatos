# TP Final - G12 (Template del README)

> **Template del README del grupo.** Copienlo a `TpFinal/grupos/G<NN>/README.md` y
> completen cada seccion. `G00` no es una entrega real.

---

## Integrantes

- Lautaro Ramos (@lautira2006)
- Valentina Varisco (@valenvarisco)
- Francisco Baudracco (@franbaudra)
- Ramiro Kammerer (@)
## API elegida

- **Nombre**: `USGS Earthquakes`
- **URL**: `https://earthquake.usgs.gov/fdsnws/event/1/query`
- **Descripcion**: `Devuelve información de sismos en tiempo real y datos históricos en formato GeoJSON, incluyendo magnitud, profundidad, coordenadas y alertas de tsunami.`
- **Auth**: `sin auth`
- **API key**: `no necesita`
- **Refresh**: `Tiempo real cada vez que ocurre un sismo`

## Modelo de datos

### Bronze

`<que tablas crudas guardan + columnas + metadatos de auditoria (ingested_at, source, etc.)>`

### Silver

`<que transformaciones aplican: limpieza, validacion de tipos, deduplicacion, enriquecimiento>`

### Gold

`<modelo dimensional: fact_X + dim_Y, y que pregunta de negocio responde el dashboard>`

## Dashboard

Streamlit en `Stack/dashboard/`, en http://localhost:8501. Lee **solo la capa Gold**:

| Página | Pregunta que responde | Tablas |
|---|---|---|
| Portada (`app.py`) | ¿Cuánto tembló en el período, y cuáles fueron los días/lugares más fuertes? | `fact_sismos_diarios` ⋈ `dim_region` |
| Evolución diaria | ¿Cómo cambia la actividad día a día? (sismos, magnitud, energía; filtro por período y región) | `fact_sismos_diarios` ⋈ `dim_region` |
| Ranking de zonas | ¿Dónde tiembla más y dónde más fuerte? ¿Qué zonas tuvieron alerta de tsunami? | `agg_ranking_zonas` |

- La energía se muestra en **toneladas de TNT equivalentes** (1 t TNT = 4.184e9 J) para que se entienda la escala.
- Si Gold todavía no tiene datos (el pipeline no corrió), cada página lo avisa en vez de romperse.
- `db.py` centraliza la conexión (credenciales del `.env`) y cachea las consultas 60 s; el botón **Actualizar datos** de la barra lateral limpia el cache.

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
- Airflow UI: http://localhost:8080 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` (user/pass en `.env`)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
