
import sys
from pathlib import Path

import pytest

# Permitir importar el paquete common.
DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
sys.path.insert(0, str(DAGS_DIR))


def test_assets_definidos():
    from common.assets import (
        BRONZE_CLIMA,
        SILVER_CLIMA,
        GOLD_CLIMA,
    )

    assert BRONZE_CLIMA.uri == "bronze_clima_ready"
    assert SILVER_CLIMA.uri == "silver_clima_ready"
    assert GOLD_CLIMA.uri == "gold_clima_ready"


def test_variables_warehouse_obligatorias(monkeypatch):
    from common.db import get_warehouse_engine

    variables = [
        "WAREHOUSE_HOST",
        "WAREHOUSE_PORT",
        "WAREHOUSE_DB",
        "WAREHOUSE_USER",
        "WAREHOUSE_PASSWORD",
    ]

    for variable in variables:
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(RuntimeError, match="Faltan variables"):
        get_warehouse_engine()


def test_configuracion_conexion_warehouse(monkeypatch):
    from common.db import get_warehouse_engine

    configuracion = {
        "WAREHOUSE_HOST": "data_warehouse",
        "WAREHOUSE_PORT": "5432",
        "WAREHOUSE_DB": "clima_db",
        "WAREHOUSE_USER": "usuario_prueba",
        "WAREHOUSE_PASSWORD": "clave_prueba",
    }

    for variable, valor in configuracion.items():
        monkeypatch.setenv(variable, valor)

    engine = get_warehouse_engine()

    try:
        assert engine.url.host == "data_warehouse"
        assert engine.url.port == 5432
        assert engine.url.database == "clima_db"
        assert engine.url.username == "usuario_prueba"
        assert engine.url.password == "clave_prueba"
    finally:
        engine.dispose()
