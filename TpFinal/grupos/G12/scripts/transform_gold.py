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


def procesar_gold_usgs():
  with engine.connect() as conn:
    df_silver = pd.read_sql('SELECT * FROM silver.earthquakes;', con=conn)

  df_dim_region = (
      df_silver[['region']].drop_duplicates().reset_index(drop=True)
  )
  df_dim_region['region_id'] = df_dim_region.index + 1
  df_dim_region = df_dim_region[['region_id', 'region']]

  df_base_gold = df_silver.merge(df_dim_region, on='region')

  df_fact_sismos_diarios = (
      df_base_gold.groupby(['event_date', 'region_id'])
      .agg(
          cantidad_sismos=('earthquake_id', 'count'),
          magnitud_promedio=('magnitude', 'mean'),
          magnitud_maxima=('magnitude', 'max'),
          energia_total_joules=('energia_joules', 'sum'),
          alertas_tsunami=('tsunami_alert', 'sum'),
      )
      .reset_index()
  )

  df_fact_sismos_diarios['magnitud_promedio'] = df_fact_sismos_diarios[
      'magnitud_promedio'
  ].round(2)
  df_fact_sismos_diarios['magnitud_maxima'] = df_fact_sismos_diarios[
      'magnitud_maxima'
  ].round(2)

  df_ranking_zonas = (
      df_base_gold.groupby('region')
      .agg(
          total_sismos=('earthquake_id', 'count'),
          magnitud_promedio=('magnitude', 'mean'),
          magnitud_maxima=('magnitude', 'max'),
          profundidad_promedio_km=('depth_km', 'mean'),
          total_alertas_tsunami=('tsunami_alert', 'sum'),
      )
      .reset_index()
      .sort_values(by='total_sismos', ascending=False)
  )

  df_ranking_zonas['magnitud_promedio'] = df_ranking_zonas[
      'magnitud_promedio'
  ].round(2)
  df_ranking_zonas['magnitud_maxima'] = df_ranking_zonas[
      'magnitud_maxima'
  ].round(2)
  df_ranking_zonas['profundidad_promedio_km'] = df_ranking_zonas[
      'profundidad_promedio_km'
  ].round(2)

  df_dim_region.to_sql(
      name='dim_region',
      con=str(engine.url),
      schema='gold',
      if_exists='replace',
      index=False,
  )
  df_fact_sismos_diarios.to_sql(
      name='fact_sismos_diarios',
      con=str(engine.url),
      schema='gold',
      if_exists='replace',
      index=False,
  )
  df_ranking_zonas.to_sql(
      name='agg_ranking_zonas',
      con=str(engine.url),
      schema='gold',
      if_exists='replace',
      index=False,
  )

  print(
      f'🥇 Gold procesado correctamente: dim_region ({len(df_dim_region)}'
      f' filas) | fact_sismos_diarios ({len(df_fact_sismos_diarios)} filas)'
  )


if __name__ == '__main__':
  procesar_gold_usgs()