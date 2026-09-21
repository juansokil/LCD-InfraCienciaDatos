# TP Final - G00 (Template del README)

> **Template del README del grupo.** Copienlo a `TpFinal/grupos/G<NN>/README.md` y
> completen cada seccion. `G00` no es una entrega real.

---

## Integrantes

- Nombre Apellido (@usuario-github)
- Nombre Apellido (@usuario-github)
- ...

## API elegida

- **Nombre**: `<nombre de la API>`
- **URL**: `<link a la doc oficial>`
- **Descripcion**: `<breve explicación de que devuelve la API>`
- **Auth**: `<sin auth / API key gratis / OAuth>`
- **Refresh**: `<cada cuanto se actualizan los datos>`

## Modelo de datos

### Bronze

`<que tablas crudas guardan + columnas + metadatos de auditoria (ingested_at, source, etc.)>`

### Silver

`<que transformaciones aplican: limpieza, validacion de tipos, deduplicacion, enriquecimiento>`

### Gold

`<modelo dimensional: fact_X + dim_Y, y que pregunta de negocio responde el dashboard>`

## Como levantar el stack

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

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es la misma estructura para todos los grupos.
