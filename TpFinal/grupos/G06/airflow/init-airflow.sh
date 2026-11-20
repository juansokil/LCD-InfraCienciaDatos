#!/bin/bash

# Arranque de Airflow del TP G06
set -e

# 1) Crear / actualizar las tablas internas de Airflow (en airflow_db)
airflow db migrate

# 2) Los 4 procesos de Airflow, todos en el mismo contenedor
airflow scheduler &
airflow triggerer &
airflow dag-processor &

# 3) La UI y la API
exec airflow api-server
