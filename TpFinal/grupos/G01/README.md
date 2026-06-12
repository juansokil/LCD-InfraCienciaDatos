# TP Final - G01 — Open-Meteo Weather Pipeline

## Integrantes

| Federico Raiteri | @RaiteriFederico  |
| Lautaro Molendi | @Lautaro-Molendi |
| Lorenzo Ortmann | @lorenzoortmann|
| Lucas Graziadei | @usuario-github |
| Rocío Sajama | @rocioSajama |

## API elegida

| **Nombre** | Open-Meteo |
| **URL** | https://open-meteo.com/ |
| **Descripción** | API pública de pronóstico y datos meteorológicos históricos para coordenadas geográficas arbitrarias |
| **Auth** | Sin autenticación, sin límite de requests |
| **Refresh** | Cada 1 hora |

## Regiones monitoreadas

| `buenos_aires` | Buenos Aires | -34.6037 | -58.3816 |
| `cordoba` | Córdoba | -31.4135 | -64.1811 |
| `mendoza` | Mendoza | -32.8895 | -68.8458 |
| `salta` | Salta | -24.7859 | -65.4117 |
| `tierra_del_fuego` | Tierra del Fuego | -54.8019 | -68.3030 |

## Modelo de datos

### Bronze

Ingesta cruda de la API mediante peticiones horarias parametrizadas por coordenadas. Cada request devuelve dos nodos: `current` (medición real instantánea) y `daily` (pronóstico a 7 días con arrays paralelos). Ambos nodos se guardan juntos en un único payload JSONB sin transformación.

**Tabla: `bronze.open_meteo_raw`**

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | Identificador único de la ingesta |
| `id_provincia` | VARCHAR | Código de la región (`buenos_aires`, `cordoba`, etc.) |
| `payload` | JSONB | JSON crudo con nodos `current` y `daily` |
| `ingested_at` | TIMESTAMP | Timestamp de captura (auditoría) |
| `source` | VARCHAR | Origen del dato, siempre `'open-meteo'` |


### Silver

Desanidación y limpieza del JSON de Bronze. Se separan las mediciones reales del pronóstico en dos tablas relacionales con claves primarias compuestas que garantizan idempotencia, así aseguramos que la misma medición nunca se duplica.

**Transformaciones:**

- **Desanidación**: Los arrays paralelos del nodo `daily` se convierten en filas individuales via `zip()`
- **Tipado**: Todos los campos numéricos se mapean a tipos `NUMERIC` con precisión definida
- **Manejo de nulos**: Registros sin timestamp válido se descartan con warning en el log
- **`snapshot_ts`**: Registramos el momento exacto en que se emitió cada pronóstico (esto viene del `ingested_at` del registro Bronze), lo que permite calcular el horizonte temporal de cada predicción en Gold

> Las unidades (°C, mm, km/h) y la sensación térmica (`apparent_temperature`) ya vienen correctas desde la API, nos ahorramos la conversión adicional.

**Tabla: `silver.clima_actual`**

| Campo | Tipo | Descripción |
|---|---|---|
| `id_provincia` | VARCHAR | PK compuesta |
| `fecha_hora` | TIMESTAMP | PK compuesta — timestamp de la medición |
| `temperatura_c` | NUMERIC | Temperatura en °C |
| `sensacion_termica_c` | NUMERIC | Sensación térmica en °C |
| `humedad_relativa` | INT | Humedad relativa en % |
| `lluvia_mm` | NUMERIC | Precipitación en mm |
| `viento_kmh` | NUMERIC | Velocidad del viento en km/h |
| `weather_code` | INT | Código WMO de condición climática |
| `actualizado_at` | TIMESTAMP | Timestamp de procesamiento (auditoría) |

**Tabla: `silver.clima_pronostico`**

| Campo | Tipo | Descripción |
|---|---|---|
| `id_provincia` | VARCHAR | PK compuesta |
| `fecha_pronostico` | DATE | PK compuesta — fecha del pronóstico |
| `snapshot_ts` | TIMESTAMP | Momento en que se emitió el pronóstico |
| `temp_max_c` | NUMERIC | Temperatura máxima pronosticada |
| `temp_min_c` | NUMERIC | Temperatura mínima pronosticada |
| `sensacion_max_c` | NUMERIC | Sensación térmica máxima pronosticada |
| `sensacion_min_c` | NUMERIC | Sensación térmica mínima pronosticada |
| `lluvia_acumulada_mm` | NUMERIC | Precipitación acumulada pronosticada |
| `precipitacion_prob_pct` | INT | Probabilidad de precipitación en % |
| `viento_max_kmh` | NUMERIC | Viento máximo pronosticado en km/h |
| `weather_code` | INT | Código WMO del pronóstico |
| `calculado_at` | TIMESTAMP | Timestamp de procesamiento (auditoría) |

---

### Gold

Modelo orientado a responder dos preguntas de negocio: *¿Cuál es el comportamiento climático histórico por región?* y *¿Qué tan precisas son las predicciones de Open-Meteo?*. Sumamos uno diario para poder monitorear el correcto funcionamiento de forma horaria: lo pensamos para facilitar la evaluación.

**Dimensiones:**

| Tabla | Descripción |
|---|---|
| `gold.dim_provincia` | Datos geográficos estáticos de cada región (nombre, latitud, longitud) |
| `gold.dim_tiempo` | Calendario con granularidad diaria (año, mes, día, día de semana, fin de semana) |
| `gold.dim_weather_code` | Lookup table de los 24 códigos WMO con descripción en español, categoría e indicador de alerta |

**Tablas de hechos:**

| Tabla | Descripción |
|---|---|
| `gold.fact_clima_diario` | Temperatura promedio, máxima y mínima real, lluvia acumulada y categoría de confort térmico por provincia y día |
| `gold.fact_desvio_pronostico` | Cruce entre pronóstico emitido y medición real: error absoluto en °C, acierto en predicción de lluvia |

---

### Dashboard (Streamlit)


| Página | Descripción |
|---|---|
| **Condiciones Actuales** | KPIs de temperatura y condición climática por provincia con iconos WMO. Incluye evolución horaria del día en curso |
| **Comparativa Regional** | Gráficos de temperatura promedio, rango térmico y lluvia acumulada entre provincias a lo largo del tiempo |
| **Precisión del Pronóstico** | Error absoluto medio por provincia, scatter de pronosticado vs real, acierto en predicción de lluvia y evolución temporal del error |


## Cómo levantar el stack

```bash
git clone https://github.com/juansokil/LCD-InfraCienciaDatos.git
cd LCD-InfraCienciaDatos
git checkout tp-final/G01
cd TpFinal/grupos/G01
docker compose up --build
```

**Accesos:**

| Servicio | URL | Credenciales |
|---|---|---|
| Airflow UI | http://localhost:8080 | Sin login (SimpleAuthManager) |
| Dashboard | http://localhost:8501 | Sin login |
| Postgres | localhost:5432 | Usuario y contraseña definidos en `.env` |

**Una vez levantado**, los DAGs arrancan solos, pusimos `is_paused_upon_creation=False`.
**Apagar:**

```bash
docker compose down     
```
