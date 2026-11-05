# TP Final - G04 - Open-Meteo.

## Integrantes

- Nombre Apellido (@usuario-github)

- Matias Rousso (@Matirou1)
- ...

## API elegida

- **Nombre**: `<Open-Meteo Forecast API>`
- **URL**: `<https://open-meteo.com/en/docs>`
- **Descripcion**: `<API meteorologica que devuelve condiciones climaticas actuales estimadas y pronosticos para distintas ubicaciones geograficas. Temperatura, humedad, precipitaciones, etc>`
- **Auth**: `<sin auth>`
- **API key**: `<no necesita>`
- **Refresh**: `<Ingesta programada cada hora.>`

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

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
