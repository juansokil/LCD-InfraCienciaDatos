import json
import os
import subprocess
from datetime import datetime, timedelta
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

DATABASE_URL = f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(DATABASE_URL)

# Ruta base para el Data Lake local (con la corrección para Docker)
if Path('/opt/airflow/data').exists():
    CARPETA_RAW = Path('/opt/airflow/data/raw/usgs_earthquakes')
else:
    CARPETA_RAW = (
        env_path.parent
        if env_path.exists()
        else REPO_ROOT / 'TpFinal' / 'grupos' / 'G12' / 'Stack'
    ) / 'data' / 'raw' / 'usgs_earthquakes'


def filtrar_nuevos(df):
    df['earthquake_id'] = df['id'].astype(str)
    df['version_updated'] = (
        pd.to_datetime(
            df['properties'].apply(lambda p: p.get('updated') or p.get('time')),
            unit='ms',
            utc=True,
        )
        .dt.tz_localize(None)
        .dt.floor('s')
    )
    df = df.drop_duplicates(subset=['earthquake_id', 'version_updated'])

    with engine.connect() as conn:
        existentes = pd.read_sql(
            'SELECT earthquake_id, version_updated FROM bronze.raw_earthquakes;',
            con=conn,
        )

    if existentes.empty:
        return df

    existentes['earthquake_id'] = existentes['earthquake_id'].astype(str)
    existentes['version_updated'] = (
        pd.to_datetime(existentes['version_updated'], utc=True)
        .dt.tz_localize(None)
        .dt.floor('s')
    )

    df = df.merge(
        existentes,
        on=['earthquake_id', 'version_updated'],
        how='left',
        indicator=True,
    )
    return df[df['_merge'] == 'left_only'].drop(columns='_merge')


# ==========================================
# FUNCIÓN 1: INGESTA DIARIA (La que usa Airflow)
# ==========================================
def ingestar_usgs_bronze(modo='append'):
  """Extrae los sismos del último día desde la API USGS."""
  url_api = (
      'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson'
  )

  response = requests.get(url_api)
  response.raise_for_status()
  ahora = datetime.now()

  # Guardar en Landing Zone (Data Lake local) particionado por día
  carpeta_particion = CARPETA_RAW / f'ds={ahora:%Y-%m-%d}'
  carpeta_particion.mkdir(parents=True, exist_ok=True)
  archivo_json = carpeta_particion / f'{ahora:%H%M%S_%f}.json'
  archivo_json.write_bytes(response.content)

  # Procesar lista 'features' GeoJSON
  payload = response.json()
  features = payload.get('features', [])

  if not features:
    print('⚠️ No se obtuvieron eventos sísmicos en la consulta.')
    return

  df = pd.DataFrame(features)
  df = filtrar_nuevos(df)

  if df.empty:
    print('ℹ️ Nada nuevo: todos los eventos ya estaban ingestados.')
    return

  # Serializar estructuras internas (properties, geometry) a string JSON
  for col in df.columns:
    if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
      df[col] = df[col].apply(
          lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x
      )

  df['ingested_at'] = ahora

  # Guardar en Postgres
  df.to_sql(
      name='raw_earthquakes',
      con=str(engine.url),
      schema='bronze',
      if_exists=modo,
      index=False,
  )

  print(f'✅ Ingesta diaria Bronze exitosa ({ahora:%H:%M:%S} - Modo: {modo})')
  print(f' 📄 Archivo Raw: {archivo_json.name}')
  print(f' 🗄️ Tabla Postgres: bronze.raw_earthquakes (+{len(df)} filas)')


# ==========================================
# FUNCIÓN 2: INGESTA HISTÓRICA (Para correr a mano)
# ==========================================
def ingestar_historico_30dias():
  """Descarga los últimos 30 días de sismos y los guarda en Bronze."""
  fecha_fin = datetime.now()
  fecha_inicio = fecha_fin - timedelta(days=30)

  # Endpoint de consulta FDSN (permite fechas)
  url_api = (
      "https://earthquake.usgs.gov/fdsnws/event/1/query"
      f"?format=geojson"
      f"&starttime={fecha_inicio.strftime('%Y-%m-%d')}"
      f"&endtime={fecha_fin.strftime('%Y-%m-%d')}"
      f"&minmagnitude=2.5"
  )

  print(f"⏳ Consultando sismos desde {fecha_inicio.date()} hasta {fecha_fin.date()}...")
  response = requests.get(url_api)
  response.raise_for_status()
  ahora = datetime.now()

  # Guardar en una carpeta distinta para no mezclar con el flujo diario
  carpeta_particion = CARPETA_RAW / 'historico_30d'
  carpeta_particion.mkdir(parents=True, exist_ok=True)
  archivo_json = carpeta_particion / f'usgs_30d_{ahora:%Y%m%d_%H%M%S}.json'
  archivo_json.write_bytes(response.content)
  print(f"📄 JSON histórico guardado en: {archivo_json.name}")

  # Procesar
  payload = response.json()
  features = payload.get('features', [])

  if not features:
    print('⚠️ No se encontraron sismos en el período solicitado.')
    return

  df = pd.DataFrame(features)
  df = filtrar_nuevos(df)

  if df.empty:
    print('ℹ️ Nada nuevo: todos los eventos ya estaban ingestados.')
    return

  for col in df.columns:
    if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
      df[col] = df[col].apply(
          lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x
      )

  df['ingested_at'] = ahora

  # Guardar en Postgres (append)
  df.to_sql(
      name='raw_earthquakes',
      con=str(engine.url),
      schema='bronze',
      if_exists='append',
      index=False,
  )

  print(f'✅ Ingesta histórica exitosa: +{len(df)} filas en bronze.raw_earthquakes')


# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == '__main__':
  # Airflow ejecutará la función de arriba por defecto.
  # Si querés correr la histórica a mano, descomentá la línea de abajo.

  ingestar_usgs_bronze(modo='append')

  # ingestar_historico_30dias()