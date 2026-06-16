#!/bin/bash
set -e

echo "Inicializando Airflow G09..."
airflow db migrate

airflow scheduler &
airflow triggerer &
airflow dag-processor &
exec airflow api-server

