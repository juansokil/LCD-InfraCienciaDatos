#!/bin/bash
set -e

echo "=========================================="
echo "Lanzando Airflow UN-SAM"
echo "=========================================="

# 1. Migrar base de datos
echo "Inicializando Metadatos..."
airflow db migrate

echo "=========================================="
echo "Sin autenticacion - Acceso directo"
echo "URL: http://localhost:8080"
echo "=========================================="

# 2. Iniciar servicios (Airflow 3.x)
airflow scheduler &
airflow triggerer &
airflow dag-processor &
exec airflow api-server
