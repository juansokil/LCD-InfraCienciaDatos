# TP Final – G04 – Open-Meteo

## Integrantes

- Juan Krizaj (@juankrizaj)
- Matías Rousso (@Matirou1)
- [Completar integrantes restantes y usuarios de GitHub]

## API elegida

- **Nombre:** Open-Meteo Forecast API
- **Documentación:** https://open-meteo.com/en/docs
- **Descripción:** API meteorológica que proporciona condiciones climáticas actuales estimadas y pronósticos para distintas ubicaciones.
- **Autenticación:** No requiere API key para el uso realizado en el proyecto.
- **Frecuencia de ingesta:** Cada hora.
- **Ciudades:** Buenos Aires, Córdoba, Mendoza, Bariloche y Salta.
- **Horizonte del pronóstico:** 7 días.

## Arquitectura del proyecto

El proyecto implementa una arquitectura Medallion utilizando PostgreSQL, Apache Airflow 3.1.5, Docker Compose y Streamlit.

El procesamiento sigue tres etapas:

**Open-Meteo → Bronze → Silver → Gold → Streamlit**

Apache Airflow automatiza las ejecuciones mediante Assets. Bronze se ejecuta cada hora, Silver se activa cuando finaliza correctamente Bronze y Gold se activa cuando finaliza Silver.

## Modelo de datos

### Bronze

Tabla: `bronze.clima_raw`

Almacena las respuestas originales de Open-Meteo en formato JSONB, conservando los datos recibidos para su trazabilidad.

Incluye identificadores de consulta y ejecución, ciudad, coordenadas geográficas, fecha de ingesta, origen de los datos, ruta del archivo original y hash de integridad.

### Silver

Tablas:

- `silver.clima_actual`: condiciones meteorológicas actuales por consulta.
- `silver.pronostico_diario`: pronósticos diarios de temperatura, precipitación y viento.
- `silver.clima_quarantine`: registros que incumplen las reglas de calidad.

La capa aplica transformaciones SQL, validaciones de tipos y rangos, controles de consistencia y mecanismos para evitar duplicaciones.

### Gold

Modelo dimensional:

- `gold.dim_ciudad`: información de las ciudades.
- `gold.dim_tiempo`: dimensión de fechas.
- `gold.fact_clima_diario`: tabla de hechos con los pronósticos meteorológicos diarios.

Vistas analíticas:

- `gold.v_ultimo_pronostico`
- `gold.v_comparacion_ciudades`

Estas vistas alimentan el dashboard y permiten comparar temperaturas, precipitaciones y posibles alertas meteorológicas entre ciudades.

## Cómo levantar el proyecto

### Requisitos

- Docker Desktop instalado y en funcionamiento.
- Docker Compose disponible.
- Puertos 8080, 8501 y 5433 disponibles.

Desde la raíz del repositorio:

```bash
cd TpFinal/grupos/G04
docker compose up -d --build
```

La inicialización de Airflow y las bases de datos se realiza mediante Docker Compose. El servicio de bootstrap dispara la ejecución inicial de Bronze cuando Airflow está disponible.

### Accesos

| Servicio | Dirección |
|---|---|
| Apache Airflow | http://localhost:8080 |
| Dashboard Streamlit | http://localhost:8501 |
| PostgreSQL Warehouse | localhost:5433 |

Las credenciales y variables de conexión se configuran mediante el archivo `.env`.

### Verificar servicios

```bash
docker compose ps -a
```

### Verificar DAGs

```bash
docker compose exec airflow-dag-processor airflow dags list
docker compose exec airflow-dag-processor airflow dags list-import-errors
```

Deben aparecer los DAGs `bronze_clima`, `silver_clima` y `gold_clima`, sin errores de importación.

### Verificar ejecuciones

```bash
docker compose exec airflow-dag-processor airflow dags list-runs bronze_clima
docker compose exec airflow-dag-processor airflow dags list-runs silver_clima
docker compose exec airflow-dag-processor airflow dags list-runs gold_clima
```

## Pruebas

Para ejecutar los tests desde la carpeta G04:

```bash
docker compose run --rm --no-deps --entrypoint python -e PYTHONPATH=/opt/airflow/project:/opt/airflow/project/dags airflow-dag-processor -m pytest /opt/airflow/project/tests -v
```

En la verificación realizada el 12/11/2026 se obtuvieron **9 tests aprobados**.

También se comprobó el encadenamiento automático de los tres DAGs y la persistencia de registros en Bronze, Silver y Gold.

## Apagar el proyecto

Para detener los servicios conservando los datos:

```bash
docker compose down
```

No utilizar `docker compose down -v` salvo que se quiera eliminar expresamente los volúmenes persistentes de las bases de datos.
