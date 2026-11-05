# TP Final - G02

---

## Integrantes

- Ezequiel Oyola (@Equi00)
- Tomas Martin (@martintomas1)

## API elegida

- **Nombre**: `open-meteo`
- **URL**: `https://open-meteo.com/`
- **Descripcion**: `API que devuelve la informacion del clima de los paises y provincias del mundo.`
- **Auth**: `Sin Auth.`
- **API key**: `No necesita.`
- **Refresh**: `Cada hora.`

## Modelo de datos

### Bronze

Tabla `bronze.open_meteo_raw`: una fila por ciudad y por ejecución, con la respuesta original de Open-Meteo sin modificar.

| id | city_code | http_status | error_message | ingested_at | temp_actual |
|---:|-----------|------------:|---------------|-------------------------------|------------:|
| 1  | BUE | 200 |  | 2026-11-05 13:15:07.62374+00  | 22.3 |
| 2  | COR | 200 |  | 2026-11-05 13:15:08.324421+00 | 21.8 |
| 3  | MDZ | 200 |  | 2026-11-05 13:15:09.084656+00 | 21.1 |
| 4  | SLA | 200 |  | 2026-11-05 13:15:09.834026+00 | 17.6 |
| 5  | BRC | 200 |  | 2026-11-05 13:15:10.561981+00 | 6.3  |
| 6  | BUE | 200 |  | 2026-11-05 14:15:09.627604+00 | 23.6 |
| 7  | COR | 200 |  | 2026-11-05 14:15:10.338846+00 | 23.4 |
| 8  | MDZ | 200 |  | 2026-11-05 14:15:11.091161+00 | 22.6 |
| 9  | SLA | 200 |  | 2026-11-05 14:15:11.817808+00 | 17.5 |
| 10 | BRC | 200 |  | 2026-11-05 14:15:12.52598+00  | 7.8  |
| 11 | BUE | 200 |  | 2026-11-05 15:15:07.309275+00 | 24.5 |
| 12 | COR | 200 |  | 2026-11-05 15:15:08.328562+00 | 24.7 |
| 13 | MDZ | 200 |  | 2026-11-05 15:15:09.351989+00 | 24.2 |
| 14 | SLA | 200 |  | 2026-11-05 15:15:10.369221+00 | 18.0 |
| 15 | BRC | 200 |  | 2026-11-05 15:15:11.366895+00 | 9.5  |
| 16 | BUE | 200 |  | 2026-11-05 16:15:06.937959+00 | 25.4 |
| 17 | COR | 200 |  | 2026-11-05 16:15:07.693142+00 | 25.7 |
| 18 | MDZ | 200 |  | 2026-11-05 16:15:08.416127+00 | 25.9 |
| 19 | SLA | 200 |  | 2026-11-05 16:15:09.12062+00  | 18.4 |
| 20 | BRC | 200 |  | 2026-11-05 16:15:09.820003+00 | 10.6 |
| 21 | BUE | 200 |  | 2026-11-05 17:15:07.880008+00 | 25.9 |

- **Ciudades:** Buenos Aires (BUE), Córdoba (COR), Mendoza (MDZ), Salta (SLA) y Bariloche (BRC).
- **Variables:** clima actual + pronóstico diario de 7 días.
- **Validaciones:** HTTP 200, JSON válido, presencia de `current` y `daily`, campos esperados y 7 posiciones en los arreglos diarios. Las respuestas inválidas se guardan con su error y Silver las ignora.
- **Historial:** Bronze no borra ni deduplica, conserva todas las ingestas.
- **Orquestación:** el DAG `open_meteo_bronze` corre cada hora, arranca despausado y, cuando existe el DAG de Silver, lo dispara al terminar.

### Silver

`<que transformaciones aplican: limpieza, validacion de tipos, deduplicacion, enriquecimiento>`

### Gold

`<modelo dimensional: fact_X + dim_Y, y que pregunta de negocio responde el dashboard>`

## Como levantar el stack

```bash
cd TpFinal/grupos/G02/      # ej: cd TpFinal/grupos/G01/
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
