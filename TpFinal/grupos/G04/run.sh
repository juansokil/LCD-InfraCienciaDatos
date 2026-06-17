#!/usr/bin/env bash
# run.sh - Levanta el stack CityBikes (G04) con UN solo comando.
# Uso (Mac / Linux):   ./run.sh     (si hace falta: chmod +x run.sh)
set -e
cd "$(dirname "$0")"

echo "==> Chequeando Docker..."
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker no esta corriendo. Abri Docker Desktop, espera a que arranque y reintenta."
  exit 1
fi

# El paso que todos se olvidan: crear el .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> .env creado desde .env.example"
else
  echo "==> .env ya existe"
fi

echo "==> Levantando el stack (docker compose up --build)..."
echo "    Dashboard -> http://localhost:8501   |   Airflow -> http://localhost:8080"
docker compose up --build
