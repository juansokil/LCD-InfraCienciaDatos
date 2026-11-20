#!/bin/bash
set -e

echo "=========================================="
echo "Iniciando Airflow - TP Final G03"
echo "=========================================="

airflow db migrate

echo '{"admin":"admin"}' > /opt/airflow/simple_auth_manager_passwords.json

airflow scheduler &
airflow triggerer &
airflow dag-processor &

exec airflow api-server