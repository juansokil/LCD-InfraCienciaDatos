#!/bin/bash
set -e

echo "Inicializando Airflow G23..."
airflow db migrate

echo "Airflow disponible en http://localhost:8080"
airflow scheduler &
airflow triggerer &
airflow dag-processor &
exec airflow api-server
