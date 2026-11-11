import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import requests
from sqlalchemy import create_engine


# 1. Hallar la raíz del proyecto para ubicar la carpeta Stack y el .env
def get_repo_root() -> Path:
  try:
    return Path(
        subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'], stderr=subprocess.DEVNULL
        )
        .decode()
        .strip()
    )
  except Exception:
    return Path(__file__).resolve().parents[2]


REPO_ROOT = get_repo_root()

# Cargar variables de entorno desde el .env del Stack
env_path = REPO_ROOT / 'TpFinal' / 'grupos' / 'G12' / 'Stack' / '.env'
if not env_path.exists():
  env_path = REPO_ROOT / 'stack' / '.env'
if not env_path.exists():
  env_path = Path('.env')

load_dotenv(dotenv_path=env_path)

# Credenciales de conexión
DB_USER = os.getenv('SOURCE_DB_USER', 'admin')
DB_PASS = os.getenv('SOURCE_DB_PASS', 'admin')
DB_NAME = os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')
DB_HOST = os.getenv('SOURCE_DB_HOST', 'localhost')
DB_PORT = int(os.getenv('SOURCE_DB_PORT', 5432))

DATABASE_URL = (
    f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)
engine = create_engine(DATABASE_URL)


# Ruta base para el Data Lake local
if Path('/opt/airflow/data').exists():
    # Si estamos dentro de Docker, usamos la ruta mapeada en el docker-compose.yml
    CARPETA_RAW = Path('/opt/airflow/data/raw/usgs_earthquakes')
else:
    # Si estamos en el Jupyter local, usamos la lógica original
    CARPETA_RAW = (
        env_path.parent
        if env_path.exists()
        else REPO_ROOT / 'TpFinal' / 'grupos' / 'G12' / 'Stack'
    ) / 'data' / 'raw' / 'usgs_earthquakes'

def ingestar_usgs_bronze(modo='append'):
  """Extrae los sismos del último día desde la API USGS,

  guarda los bytes JSON crudos en la Landing Zone y persiste los datos en la
  tabla bronze.raw_earthquakes.
  """
  url_api = (
      'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson'
  )

  # 1. Petición HTTP a la API
  response = requests.get(url_api)
  response.raise_for_status()
  ahora = datetime.now()

  # 2. Resguardo en Landing Zone (Data Lake local)
  carpeta_particion = CARPETA_RAW / f'ds={ahora:%Y-%m-%d}'
  carpeta_particion.mkdir(parents=True, exist_ok=True)
  archivo_json = carpeta_particion / f'{ahora:%H%M%S_%f}.json'
  archivo_json.write_bytes(response.content)

  # 3. Procesar lista 'features' GeoJSON
  payload = response.json()
  features = payload.get('features', [])

  if not features:
    print('⚠️ No se obtuvieron eventos sísmicos en la consulta.')
    return

  df = pd.DataFrame(features)

  # Serializar estructuras internas (properties, geometry) a string JSON
  for col in df.columns:
    if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
      df[col] = df[col].apply(
          lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x
      )

  # Auditoría
  df['ingested_at'] = ahora

  # 4. Guardar en Postgres usando str(engine.url) para compatibilidad
  df.to_sql(
      name='raw_earthquakes',
      con=str(engine.url),
      schema='bronze',
      if_exists=modo,
      index=False,
  )

  print(f'✅ Ingesta Bronze exitosa ({ahora:%H:%M:%S} - Modo: {modo})')
  print(f' 📄 Archivo Raw: {archivo_json.name}')
  print(f' 🗄️ Tabla Postgres: bronze.raw_earthquakes (+{len(df)} filas)')


if __name__ == '__main__':
  # Modo append para ejecución continua en producción/Airflow
  ingestar_usgs_bronze(modo='append')