import json
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine


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
env_path = REPO_ROOT / 'TpFinal' / 'grupos' / 'G12' / 'Stack' / '.env'
if not env_path.exists():
  env_path = Path('.env')

load_dotenv(dotenv_path=env_path)

DB_USER = os.getenv('SOURCE_DB_USER', 'admin')
DB_PASS = os.getenv('SOURCE_DB_PASS', 'admin')
DB_NAME = os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')
DB_HOST = os.getenv('SOURCE_DB_HOST', 'localhost')
DB_PORT = int(os.getenv('SOURCE_DB_PORT', 5432))

DATABASE_URL = (
    f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)
engine = create_engine(DATABASE_URL)


def procesar_silver_usgs():
  with engine.connect() as conn:
    df_bronze = pd.read_sql('SELECT * FROM bronze.raw_earthquakes;', con=conn)

  registros = []
  for idx, row in df_bronze.iterrows():
    props = (
        json.loads(row['properties'])
        if isinstance(row['properties'], str)
        else row['properties']
    )
    geom = (
        json.loads(row['geometry'])
        if isinstance(row['geometry'], str)
        else row['geometry']
    )

    coords = geom.get('coordinates', [None, None, None])
    lon, lat, depth = coords[0], coords[1], coords[2]

    mag = props.get('mag')
    energia_joules = 10 ** (4.8 + 1.5 * mag) if (mag and mag > 0) else None

    if mag is None:
      escala = 'Desconocida'
    elif mag < 3.0:
      escala = 'Menor'
    elif mag < 4.5:
      escala = 'Leve'
    elif mag < 6.0:
      escala = 'Moderado'
    else:
      escala = 'Fuerte / Mayor'

    place_str = props.get('place') or ''
    region = place_str.split(',')[-1].strip() if ',' in place_str else place_str

    time_ms = props.get('time')
    event_dt = pd.to_datetime(time_ms, unit='ms') if time_ms else None

    registros.append({
        'earthquake_id': row['id'],
        'magnitude': mag,
        'escala_magnitud': escala,
        'energia_joules': energia_joules,
        'place': place_str,
        'region': region,
        'tsunami_alert': int(props.get('tsunami', 0)),
        'event_timestamp': event_dt,
        'event_date': event_dt.date() if event_dt else None,
        'longitude': lon,
        'latitude': lat,
        'depth_km': depth,
        'ingested_at': row['ingested_at'],
        'processed_at': pd.Timestamp.now(),
    })

  df_silver = pd.DataFrame(registros).drop_duplicates(subset=['earthquake_id'])

  df_silver.to_sql(
      name='earthquakes',
      con=str(engine.url),
      schema='silver',
      if_exists='replace',
      index=False,
  )

  print(
      f'🥈 Silver procesado exitosamente: {len(df_silver)} filas en'
      ' silver.earthquakes'
  )


if __name__ == '__main__':
  procesar_silver_usgs()