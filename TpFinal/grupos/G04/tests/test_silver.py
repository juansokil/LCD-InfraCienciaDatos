"""Pruebas sin API externa: contrato y SQL estático. Integración requiere Postgres Docker."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_yaml_reglas():
    data = yaml.safe_load((ROOT / 'contracts/clima.yaml').read_text(encoding='utf-8'))
    r = data['quality_rules']
    assert r['temperature_min_c'] == -100
    assert r['temperature_max_c'] == 70
    assert r['require_min_not_above_max'] is True


def test_sql_bloques_y_destinos():
    sql = (ROOT / 'sql/silver_clima.sql').read_text(encoding='utf-8')
    for fragmento in ('-- BLOQUE: clima_actual', '-- BLOQUE: pronostico_diario',
                      'silver.clima_actual', 'silver.pronostico_diario',
                      'silver.clima_quarantine', 'generate_series(',
                      'ON CONFLICT DO NOTHING', "current_setting('silver.temperature_min_c')"):
        assert fragmento in sql
