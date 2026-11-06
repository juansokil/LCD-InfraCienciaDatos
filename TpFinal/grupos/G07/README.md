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