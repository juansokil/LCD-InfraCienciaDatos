"""DAG Silver Open-Meteo (Airflow 3.1.5). La transformación ocurre en PostgreSQL."""
import os
from pathlib import Path

import yaml
from sqlalchemy import text
from airflow.sdk import dag, task
from common.assets import BRONZE_CLIMA, SILVER_CLIMA
from common.db import get_warehouse_engine


def _root() -> Path:
    return Path(os.environ.get('PROJECT_ROOT', str(Path(__file__).resolve().parents[2])))


def cargar_reglas_calidad() -> dict:
    with (_root() / 'contracts' / 'clima.yaml').open(encoding='utf-8') as archivo:
        contrato = yaml.safe_load(archivo)
    reglas = contrato['quality_rules']
    requeridas = ('temperature_min_c', 'temperature_max_c', 'humidity_min_pct',
                  'humidity_max_pct', 'precipitation_min_mm', 'precipitation_max_mm',
                  'wind_min_kmh', 'wind_max_kmh', 'require_min_not_above_max')
    if any(k not in reglas for k in requeridas):
        raise ValueError('Faltan reglas obligatorias en clima.yaml')
    return reglas


def _bloques() -> dict:
    contenido = (_root() / 'sql' / 'silver_clima.sql').read_text(encoding='utf-8')
    return {
        'clima_actual': contenido.split('-- BLOQUE: clima_actual', 1)[1].split('-- BLOQUE: pronostico_diario', 1)[0].strip(),
        'pronostico_diario': contenido.split('-- BLOQUE: pronostico_diario', 1)[1].strip(),
    }


def ejecutar_sql_silver(nombre_bloque: str) -> None:
    bloques = _bloques()
    if nombre_bloque not in bloques:
        raise ValueError(f'Bloque SQL desconocido: {nombre_bloque}')
    reglas = cargar_reglas_calidad()
    engine = get_warehouse_engine()
    # Misma transacción y conexión para set_config y el SQL.
    with engine.begin() as conn:
        for clave, valor in reglas.items():
            conn.execute(text('SELECT set_config(:nombre, :valor, true)'), {
                'nombre': f'silver.{clave}',
                'valor': str(valor).lower() if isinstance(valor, bool) else str(valor),
            })
        conn.execute(text(bloques[nombre_bloque]))


def transformar_clima_actual() -> None:
    ejecutar_sql_silver('clima_actual')


def transformar_pronostico_diario() -> None:
    ejecutar_sql_silver('pronostico_diario')


def validar_calidad_silver() -> dict:
    engine = get_warehouse_engine()
    with engine.connect() as conn:
        bronze = conn.execute(text('SELECT count(*) FROM bronze.clima_raw')).scalar_one()
        if bronze == 0:
            raise ValueError('No hay datos en Bronze; no se publica Silver')
        invalidos_actuales = conn.execute(text('''
            SELECT count(*) FROM silver.clima_actual s
            LEFT JOIN bronze.clima_raw b ON s.consulta_id = b.consulta_id
            WHERE b.consulta_id IS NULL
        ''')).scalar_one()
        invalidos_diarios = conn.execute(text('''
            SELECT count(*) FROM silver.pronostico_diario s
            LEFT JOIN bronze.clima_raw b ON s.consulta_id = b.consulta_id
            WHERE b.consulta_id IS NULL
        ''')).scalar_one()
        if invalidos_actuales or invalidos_diarios:
            raise ValueError('Filas Silver sin consulta Bronze')
        actual = conn.execute(text('SELECT count(*) FROM silver.clima_actual')).scalar_one()
        diario = conn.execute(text('SELECT count(*) FROM silver.pronostico_diario')).scalar_one()
        quarantine = conn.execute(text('SELECT count(*) FROM silver.clima_quarantine')).scalar_one()
        if actual == 0 and diario == 0 and quarantine == 0:
            raise ValueError('Silver no produjo datos ni cuarentena')
    return {'bronze': bronze, 'actual': actual, 'diario': diario, 'quarantine': quarantine}


@dag(
    dag_id='silver_clima',
    schedule=[BRONZE_CLIMA],
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['tpfinal', 'open-meteo', 'G04'],
)
def _silver_dag():
    @task
    def verificar_bronze():
        engine = get_warehouse_engine()
        with engine.connect() as conn:
            if conn.execute(text('SELECT count(*) FROM bronze.clima_raw')).scalar_one() == 0:
                raise ValueError('Bronze vacío')

    @task
    def cargar_actual():
        transformar_clima_actual()

    @task
    def cargar_diario():
        transformar_pronostico_diario()

    @task(outlets=[SILVER_CLIMA])
    def confirmar_calidad():
        return validar_calidad_silver()

    a = verificar_bronze()
    b = cargar_actual()
    c = cargar_diario()
    d = confirmar_calidad()
    a >> b >> c >> d


silver_clima = _silver_dag()
