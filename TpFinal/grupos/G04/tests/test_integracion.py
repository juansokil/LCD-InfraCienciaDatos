import sys
from pathlib import Path

# Incorporar la carpeta dags para importar common.
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