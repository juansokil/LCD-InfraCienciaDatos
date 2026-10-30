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

`<que transformaciones aplican: limpieza, validacion de tipos, deduplicacion, enriquecimiento>`

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
