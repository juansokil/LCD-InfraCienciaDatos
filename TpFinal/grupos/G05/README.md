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
<<<<<<< HEAD
- Airflow UI: http://localhost:8080 (Usuario: `admin` / Contraseña: `admin`)
=======
- Airflow UI: http://localhost:8080 (usuario: `admin` / contraseña: `admin`)
>>>>>>> 756c5406dd425aaab7e54a8cd244d826af1b75e3
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` / DB: `InfraCienciaDatos` / `admin`

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.
