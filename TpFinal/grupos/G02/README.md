# TP Final - G02

---

## Integrantes

- Ezequiel Oyola (@Equi00)
- Tomas Martin (@martintomas1)
- Gino Mariani (@Ginomariani)
- Marcos Rodriguez (@perdilacuentapormiotrohermano-cell)

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

> La tabla real también guarda `request_params` y `payload` (el JSON completo, tipo JSONB). La columna `temp_actual` del ejemplo es solo ilustrativa: corresponde a `payload->'current'->>'temperature_2m'`.

- **Ciudades:** Buenos Aires (BUE), Córdoba (COR), Mendoza (MDZ), Salta (SLA) y Bariloche (BRC).
- **Variables:** clima actual + pronóstico diario de 7 días.
- **Validaciones:** HTTP 200, JSON válido, presencia de `current` y `daily`, campos esperados y 7 posiciones en los arreglos diarios. Las respuestas inválidas se guardan con su error y Silver las ignora.
- **Historial:** Bronze no borra ni deduplica, conserva todas las ingestas.
- **Orquestación:** el DAG `open_meteo_bronze` corre cada hora, arranca despausado y, cuando existe el DAG de Silver, lo dispara al terminar.

### Silver

Dos tablas relacionales que separan el estado actual del pronóstico, ambas con `source_id` (el `id` de la respuesta en Bronze) para poder rastrear cada fila hasta el dato original.

| Tabla | Granularidad | Clave |
|---|---|---|
| `silver.clima_actual` | Una fila por respuesta Bronze y ciudad | `source_id` |
| `silver.pronostico_diario` | Una fila por respuesta Bronze, ciudad y fecha pronosticada (7 por respuesta) | `(source_id, forecast_date)` |

- **Qué lee:** solo respuestas de Bronze con HTTP 200, `payload` presente y sin error, que todavía no fueron procesadas (carga incremental).
- **Limpieza y tipos:** se aplanan los objetos `current` y `daily` (los arreglos diarios se recorren por posición, manteniendo cada fecha con sus valores). Los valores pasan a tipos numéricos y las columnas llevan sufijo de unidad (`_c`, `_mm`, `_kmh`, `_pct`).
- **Validaciones:** campos obligatorios presentes; temperatura y sensación térmica entre -60 y 60 °C; humedad y nubosidad entre 0 y 100 %; precipitación y viento mayores o iguales a 0; dirección del viento entre 0 y 360°; código meteorológico entero; en el pronóstico, fechas válidas y sin repetir, y máxima mayor o igual a la mínima. Si un registro no pasa, la tarea falla y el motivo queda en los logs de Airflow.
- **Enriquecimiento:** `weather_code` se traduce a `weather_description` en español (Despejado, Lluvia, Tormenta, etc.; "Sin clasificar" para códigos desconocidos), y `valid_at` se interpreta con el desfase horario que devuelve la API.
- **Idempotencia:** las inserciones usan `ON CONFLICT DO NOTHING`, así que reintentar una corrida no duplica filas.
- **Orquestación:** el DAG `open_meteo_silver` no tiene horario propio: lo dispara Bronze y, al terminar, dispara Gold. Tareas: `create_silver_tables` → `extract_bronze_records` → `load_silver` → `trigger_gold`.

### Gold

Modelo estrella con dos dimensiones y dos tablas de hechos. Se carga solo desde Silver (Bronze se consulta únicamente para saber cuál es el snapshot más reciente).

| Tabla | Granularidad / contenido |
|---|---|
| `gold.dim_ciudad` | Una fila por ciudad: código, nombre, provincia, país, latitud, longitud y zona horaria |
| `gold.dim_fecha` | Una fila por día (`date_id` = AAAAMMDD): año, mes, nombre del mes, día, día de la semana y si es fin de semana |
| `gold.fact_clima_actual` | Una fila por ciudad y captura: temperatura, sensación térmica, humedad, precipitación, viento, nubosidad y estado del tiempo |
| `gold.fact_pronostico_diario` | Una fila por ciudad y fecha pronosticada, siempre con el **pronóstico más reciente**: máxima, mínima, lluvia acumulada, viento máximo y estado del tiempo |

Además, dos vistas para el dashboard:
- `gold.v_clima_ultimo`: la última captura de cada ciudad.
- `gold.v_pronostico`: el pronóstico con los nombres de ciudad y fecha, y banderas de días calurosos (máxima ≥ 35 °C), fríos (mínima ≤ 0 °C), lluviosos (≥ 10 mm) y ventosos (viento máximo ≥ 40 km/h). Son umbrales didácticos, no alertas oficiales.

**Carga:** el DAG `open_meteo_gold` (`create_gold_tables` → `load_dimensions` → `load_facts`) lo dispara Silver. Es idempotente: una segunda corrida no duplica filas, y el pronóstico nuevo reemplaza al anterior para la misma ciudad y fecha (UPSERT por `(city_id, date_id)`).

**Preguntas de negocio que responde el dashboard:**
- ¿Cómo están las condiciones meteorológicas ahora en cada ciudad?
- ¿Qué diferencias se esperan entre ciudades durante los próximos 7 días?
- ¿En qué días y ciudades se pronostican eventos extremos (calor, frío, lluvia o viento)?

**Dashboard (Streamlit, solo lee del esquema `gold`):** tres pestañas (Situación actual, Pronóstico de 7 días y Días destacados), con filtros por ciudad y fechas. Incluye un cuadro de contexto sobre El Niño (fuente: NOAA) que aclara que, con pocos días de datos, el tablero no permite atribuir los eventos al fenómeno.

## Como levantar el stack

```bash
cd TpFinal/grupos/G02/
docker compose up -d --build   # el .env ya viene en el repo
# Esperar unos minutos: Bronze corre al arrancar y dispara Silver y luego Gold solo
```

No hace falta crear tablas ni activar DAGs a mano: los esquemas y las tablas los crean los propios DAGs, y todos arrancan despausados. El dashboard muestra datos cuando terminan los tres.

**Accesos**:
- Airflow UI: http://localhost:8080 (usuario `admin` / contraseña `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5433` (base `weather_dw`, usuario `weather`, contraseña en `.env`)

> Si el login de Airflow no avanza, probar en una ventana de incógnito: el navegador puede tener cookies de otro Airflow en `localhost:8080`.

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

```
TpFinal/grupos/G02/
├── docker-compose.yml
├── .env
├── airflow_passwords.json
├── README.md
├── airflow/        # Dockerfile, requirements.txt e init-airflow.sh
├── dags/           # open_meteo_bronze, open_meteo_silver, open_meteo_gold
├── dashboard/      # app.py, Dockerfile y requirements.txt
└── postgres/       # init.sql
```
