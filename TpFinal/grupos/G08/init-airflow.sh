#!/bin/bash
set -e

echo "=========================================="
echo "Lanzando Airflow - TP Final G08"
echo "=========================================="

echo "Inicializando metadatos de Airflow..."
airflow db migrate

echo "=========================================="
echo "Airflow listo en http://localhost:8080"
echo "=========================================="

airflow scheduler &
airflow triggerer &
airflow dag-processor &
exec airflow api-server
