"""
Airflow Assets del pipeline CityBikes.

Un solo reloj, en el borde.
"""

from airflow.sdk import Asset

# Producido por citybikes_bronze (tarea cargar_bronze).
BRONZE_CITYBIKES = Asset(name="bronze_citybikes")

# Producido por citybikes_silver (pendiente).
SILVER_CITYBIKES = Asset(name="silver_citybikes")

# Producido por citybikes_gold (pendiente): star schema que mira el dashboard.
GOLD_CITYBIKES = Asset(name="gold_citybikes")
