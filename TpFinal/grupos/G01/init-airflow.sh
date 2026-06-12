#!/bin/bash
set -e

echo "Inicializando base de metadatos de Airflow..."
airflow db migrate

echo "Arrancando servicios..."
airflow scheduler &
airflow triggerer &
airflow dag-processor &
exec airflow api-server
