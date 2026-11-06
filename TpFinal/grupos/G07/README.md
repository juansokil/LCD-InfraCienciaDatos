# TP Final - G07

## Integrantes

- Uriel Grochowski (ugro2904)
- Candela Alejandra Rossi ()
- Antonella Trinidad Frutos ()
- Maria Sol Ibar Jalil ()
- Lucas Patricio Isla ()

## API elegida

- **Nombre**: USGS Earthquakes
- **URL**: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- **Descripcion**: API pública que proporciona información sobre eventos sísmicos a nivel mundial, incluyendo magnitud, fecha, ubicación geográfica, coordenadas y profundidad.
- **Auth**: Sin autenticación.
- **API key**: No necesita.
- **Refresh**: Cada minuto.

## Modelo de datos

### Bronze

Se realizó la extracción de datos sobre los sismos desde la API de USGS Earthquakes. La información obtenida se guarda en una base de datos PostgreSQL, dentro de la tabla `bronze.sismos_raw`.

**La tabla contiene los siguientes datos:

- `id`: número que identifica cada registro.
- `event_id`: identificador del sismo en USGS.
- `payload`: registro original completo en formato JSONB.
- `ingested_at`: fecha y hora en que se guardaron los datos.
- `source_updated_ms`: fecha de última actualización del evento en USGS.

Para obtener los datos utilizamos el archivo `scripts/ingest_usgs.py`, que se ejecuta automaticamente a través del DAG `bronze_usgs_g07` en Airflow.

Este proceso permite guardar la información orginal sin modificarla y evita duplicar registros cuando se vuelve a ejecutar, siempre que el sismo y su fecha de actualizacion sean los mismos.

### Silver
### Gold

## Como levantar el stack

Desde la carpeta del grupo:
```bash
cd TpFinal/grupos/G07/
docker compose up -d --build
```

**Accesos:**

- **Airflow UI:** http://localhost:8081 (`admin` / `admin`)
- **Postgres:** `localhost:5433` (usuario y contraseña definidos en `.env`).

**Apagar:**

```bash
docker compose down
```

Para eliminar también los volúmenes:
```bash
docker compose down -v
```

## Estructura del proyecto

- `docker-compose.yml`: configuración de los servicios de PostgreSQL y Airflow.
- `.env`: variables de entorno.
- `airflow_passwords.json`: credenciales de acceso a Airflow.
- `dags/prueba_g07.py`: DAG de prueba.