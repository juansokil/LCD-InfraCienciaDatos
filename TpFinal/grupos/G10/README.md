# TP Final - G00 (Template del README)

> **Este es el template del README** que va al lado del codigo de su grupo.
>
> **Naming**: cada grupo va en `TpFinal/grupos/G<NN>/`, donde `G` = Grupo y `NN` = numero de 2 digitos (`G01`, `G02`, ..., `G99`). `G00` es el template, no es una entrega real.
>
> Cada grupo crea `TpFinal/grupos/G<NN>/` y copia este README como base; despues lo completa con sus datos. El resto de los archivos (docker-compose, DAGs, dashboard, etc.) los arman desde cero siguiendo la estructura documentada en [`../../README.md`](../../README.md) (seccion "Esqueleto de entrega").
>
> Para arrancar: `cp TpFinal/grupos/G00/README.md TpFinal/grupos/G<NN>/README.md` y editar.

---

## Integrantes

- Alejo Trenti (@usuario-github)
- Abigail Lezcano Garcia (@usuario-github)
- Nicolas Ezequiel Lombisano (@usuario-github)
- Samir Almuiña (@usuario-github)
- Thiago Sosa (@usuario-github)
- Rodrigo Romero (@usuario-github)

## API elegida

- **Nombre**: Open-Meteo
- **URL**: https://open-meteo.com
- **Descripcion**: API pública que proporciona datos meteorológicos actuales y pronósticos climáticos sin necesidad de autenticación.
- **Auth**: Sin autenticación
- **Refresh**: Cada hora

## Modelo de datos

### Bronze

`<que tablas crudas guardan + columnas + metadatos de auditoria (ingested_at, source, etc.)>`

### Silver

`<que transformaciones aplican: limpieza, validacion de tipos, deduplicacion, enriquecimiento>`

### Gold

`<modelo dimensional: fact_X + dim_Y + abt_Z + que pregunta de negocio responde el dashboard>`

## Como levantar el stack

```bash
cd TpFinal/grupos/G<NN>/      # ej: cd TpFinal/grupos/G01/
cp .env.example .env
docker compose up -d --build
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
