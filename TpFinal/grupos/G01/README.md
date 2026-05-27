# TP Final - G01 


## Integrantes

- Federico Raiteri (@usuario-github)
- Lautaro Molendi  (@Lautaro-Molendi)
- Lorenzo Ortmann  (@usuario-github)
- Lucas Graziadei  (@usuario-github)
- Rocío Sajama  (@usuario-github)

## API elegida

- **Nombre**: `Open-Meteo`
- **URL**: `https://open-meteo.com/`
- **Descripcion**: `API pública de pronóstico y datos meteorológicos históricos.`
- **Auth**: `Sin auth`
- **Refresh**: `Cada 1 hora`

## Modelo de datos

### Bronze

Ingesta del JSON crudo directo desde la API de Open-Meteo mediante peticiones horarias parametrizadas para un set de coordenadas geográficas fijas en Argentina (elegimos Buenos Aires, Córdoba, Mendoza, Salta y Bariloche).

- **Tabla**: `bronze.open_meteo_raw`
  - `id` (SERIAL PRIMARY KEY): Identificador único de la ingesta.
  - `id_provincia` (VARCHAR): Código identificador de la región analizada.
  - `payload` (JSONB): Bloque estructurado crudo con los nodos `current` (medición horaria real) y `daily` (vectores paralelos con el pronóstico extendido a 7 días).
  - `ingested_at` (TIMESTAMP): Fecha y hora exacta de la captura (Auditoría).
  - `source` (VARCHAR): Origen del dato, por defecto `'open-meteo'` (Auditoría).

### Silver
En esta capa refinamos el JSON de Bronze. Llevamos los datos a un formato relacional limpio, tipado y estructurado, aplicando reglas de consistencia de manera atómica para evitar duplicados mediante claves primarias compuestas.

- **Transformaciones aplicadas**:
  - **Desanidación**: Apertura de los arrays paralelos del nodo `daily` para transformarlos en registros individuales (filas).
  - **Normalización de Unidades**: Forzar escala estandarizada en Celsius (°C), milímetros de precipitación (mm) y velocidad del viento en kilómetros por hora (km/h).
  - **Manejo de Nulos**: Descarte o desvío a cuarentena de registros sin marca temporal válida o coordenadas huérfanas.
  - **Enriquecimiento**: Cálculo analítico en Python de la **Sensación Térmica** (Apparent Temperature / Heat Index) para registros que carezcan de ella, cruzando temperatura y humedad relativa.

- **Tablas**:
  - `silver.clima_actual`: Registros históricos de mediciones reales instantáneas.
    - Clave primaria: `(id_provincia, fecha_hora)`.
  - `silver.clima_pronostico`: Registros históricos de las predicciones diarias emitidas.
    - Clave primaria: `(id_provincia, fecha_pronostico)`.

### Gold
Diseño de un **Modelo Estrella (Star Schema)** enfocado en responder analíticamente dos preguntas de negocio esenciales: *¿Cuál es el comportamiento climático regional histórico?* y *¿Qué tan precisas son las predicciones meteorológicas locales?*

- **Tablas del Modelo**:
  - `gold.dim_provincia` (Dimensión): Datos geográficos estáticos de control (Latitud, longitud, nombre oficial).
  - `gold.dim_tiempo` (Dimensión): Tabla de tiempo con granularidad de fecha para facilitar filtros temporales en el dashboard (Año, mes, día, día de la semana).
  - `gold.fact_clima_diario` (Hechos): Métricas agregadas reales consolidadas al final del día (Temperatura máxima real, mínima real, promedio ponderado y lluvia acumulada total).
  - `gold.fact_desvio_pronostico` (Hechos Avanzados): Tabla analítica que cruza la predicción guardada hace *X* días con la realidad medida finalmente en esa fecha, calculando el error absoluto medio en grados y la tasa de acierto/error en predicción de lluvias.

- **Dashboard (Streamlit)**:
  El tablero de control consumirá exclusivamente las tablas de la capa `gold`, permitiendo:
  1. **Comparativa Multiregional**: Análisis cruzado de tendencias de temperatura y lluvias entre provincias de Argentina.
  2. **Análisis de Confiabilidad**: Un velocímetro/indicador de la precisión del pronóstico de Open-Meteo por región.
  3. **Alertas de Anomalías**: Reporte histórico de superación de umbrales críticos (Olas de calor, heladas extremas o tormentas severas).

## Como levantar el stack

```bash
cd TpFinal/grupos/G01/
cp .env.example .env
docker compose up -d --build
# Esperar ~30s a que Airflow termine de inicializar

**Accesos**:
- Airflow UI: http://localhost:8080 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` (DB: weather_dwh, user/pass en .env)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```