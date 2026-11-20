#!/bin/bash
# =============================================================================
# Arranque de Airflow 3.1.5 (standalone, un solo contenedor)
# =============================================================================
set -e

echo "== [G11] Migrando la base de metadatos de Airflow..."
airflow db migrate

# -----------------------------------------------------------------------------
# Login de la UI: admin / admin
# -----------------------------------------------------------------------------
# Airflow 3 trae el "Simple Auth Manager": los usuarios salen de
# AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS (en el .env: admin:admin = usuario
# admin con rol admin) y las contrasenas de un JSON. Si el usuario no esta en
# el JSON, Airflow inventa una contrasena al azar en cada volumen nuevo; la
# dejamos fija para que el README pueda decir cual es.
PASSWORDS_FILE="${AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE:-/opt/airflow/simple_auth_manager_passwords.json}"
echo "{\"admin\": \"${AIRFLOW_ADMIN_PASSWORD:-admin}\"}" > "$PASSWORDS_FILE"

echo "== [G11] Levantando scheduler, triggerer, dag-processor y api-server"
echo "== [G11] UI: http://localhost:8080  (admin / ${AIRFLOW_ADMIN_PASSWORD:-admin})"

airflow scheduler &
airflow triggerer &
airflow dag-processor &
exec airflow api-server
