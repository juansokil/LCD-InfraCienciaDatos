#!/bin/bash
set -e

echo "=========================================="
echo "Iniciando Airflow - TP Final G03"
echo "=========================================="

airflow db migrate

airflow scheduler &
airflow triggerer &
airflow dag-processor &

exec airflow api-server