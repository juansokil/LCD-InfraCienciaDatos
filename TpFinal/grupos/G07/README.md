# TP Final - G07 
---

## Integrantes

- Gonzalo Cárdenas (@Zagon22)
- Gabriela Gattas (@Gabi6285)
- Gastón Rossi (@torino05)
- Morena Stolerman (@Morenastolerman)
- Camila Vidoni (@camilavidoni7)
- Alex Flores (@afloreschoquehuanca-byte)

## API elegida

- **Nombre**: `CityBikes API`
- **URL**: `https://docs.citybik.es/api`
- **Descripcion**: `Proporciona datos en tiempo real sobre el estado de estaciones de bicicletas públicas en distintas ciudades del mundo. Devuelve información como cantidad de bicicletas disponibles, slots vacíos, coordenadas geográficas y timestamp de actualización.`
- **Auth**: `Sin autenticación (no requiere API key para uso básico).`
- **Refresh**: `Cada 2–5 minutos (actualización frecuente según la red de bicicletas).`
- **Frecuencia de ingesta del DAG**: cada 5 minutos.

## Modelo de datos

El proyecto implementa una arquitectura analítica basada en la **Arquitectura Medallón**, diseñada para monitorear el sistema EcoBici del Gobierno de la Ciudad de Buenos Aires (GCBA).

### Bronze

La capa Bronze almacena los datos crudos obtenidos de la API CityBikes, conservando el payload original mediante una ingesta automatizada por Airflow (cada 5 minutos). Los archivos JSON obtenidos se almacenan inicialmente en una carpeta Landing y, una vez procesados exitosamente, se trasladan a Processed para garantizar trazabilidad y reproducibilidad. Se implementa una estrategia de idempotencia delete-insert basada en el timestamp de ejecución.

**Tablas generadas:**
* `bronze.networks`: Snapshot de redes disponibles en CityBikes.
* `bronze.stations`: Snapshot del estado de estaciones (ubicación, disponibilidad).
* `bronze.snapshots`: Trazabilidad de los requests HTTP realizados a la API.

**Metadatos de auditoría (agregados a todas las tablas):**
* `ts`: Timestamp lógico de la corrida del DAG (clave de partición).
* `ds`: Fecha lógica de la corrida.
* `source_url`: Endpoint de origen consultado.
* `ingested_at`: Momento real de la ingesta.

* **Evolución del esquema:** incorporación automática de nuevas columnas detectadas en la fuente mediante sentencias `ALTER TABLE`, evitando reconstrucciones completas de la capa.

### Silver

En esta capa se aplican estrictas reglas de calidad impulsadas de manera declarativa por el contrato de datos ([Ver contrato Silver](./data/contracts/silver_contracts.yaml)).

**Transformaciones aplicadas:**
* **Validación y Tipado (Casting):** Conversión automática de variables (ej. `free_bikes` a INTEGER, coordenadas a FLOAT).
* **Quarantine Table:** Los registros que violan las reglas de negocio (ej. cantidades negativas de bicicletas o coordenadas anómalas) se aíslan en `silver.quarantine` para no contaminar la capa analítica.
* **Integridad Físico-Lógica:** Generación dinámica de Claves Primarias (PK) y Foráneas (FK) en PostgreSQL.
* **Enriquecimiento Geográfico:** Cruce espacial de los datos con el archivo semilla `station_barrios.csv` para anexar barrio y comuna a cada estación.
* **Métricas Derivadas:** Cálculo del porcentaje de ocupación (`occupancy_pct`) fila a fila para cada snapshot.

* **Evolución del contrato:** las nuevas columnas definidas en el contrato se incorporan automáticamente sin necesidad de recrear tablas.
  
### Gold

La capa Gold expone un modelo dimensional (Esquema Estrella) estructurado específicamente para alimentar el dashboard en Streamlit, definido mediante `gold_contracts.yaml`. 

**Modelo Dimensional:**
* **Dimensiones:** `dim_time` (desglose temporal granular), `dim_zona` (barrio y comuna) y `dim_estacion` (atributos estáticos y ubicación).
* **Hechos (Facts):**
    * `fact_estado_actual_estacion`: Tabla de última milla (último snapshot) para monitoreo operativo y mapas en tiempo real.
    * `fact_ocupacion_por_hora`: Tabla histórica agregada por hora que evalúa promedios y calcula el % de tiempo en "estado crítico" (saturación o desabastecimiento).
* **Métricas principales expuestas por las tablas de hechos:**
    * Bicicletas promedio disponibles por hora.
    * Slots promedio disponibles por hora.
    * Ocupación promedio.
    * Porcentaje de tiempo en estado crítico.
    * Frecuencia de saturación y desabastecimiento.

**Preguntas de negocio que responde el Dashboard:**
1.  **¿Cuál es el estado operativo actual de la red?** (Bicicletas libres, slots vacíos y estaciones monitoreadas).
2.  **¿En qué momentos del día varía la disponibilidad?** (Patrón horario de ocupación promedio).
3.  **¿Qué zonas de la ciudad requieren más atención?** (Ocupación y estaciones críticas agrupadas por barrio/comuna).
4.  **¿Qué estaciones presentan fallas recurrentes?** (Ranking Top 10 de "puntos ciegos" con problemas crónicos de saturación o vaciado).

---

## Como levantar el stack

```bash
cd TpFinal/grupos/G07/
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

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md)

