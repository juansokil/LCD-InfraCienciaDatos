#!/bin/bash

# Arranque de Airflow del TP G06
set -e

# 1) Crear / actualizar las tablas internas de Airflow (en airflow_db)
airflow db migrate

# 2) Los 4 procesos de Airflow, todos en el mismo contenedor
airflow scheduler &
airflow triggerer &
airflow dag-processor &

# 3) Primera corrida automatica: apenas el dag-processor registra el DAG de
#    Bronze, lo disparamos una vez. Despues sigue solo con su cron, y Silver y
#    Gold se encadenan por assets. Asi, con `docker compose up`, el pipeline
#    arranca sin tocar nada (lo pide la consigna).
(
  for _ in $(seq 1 60); do
    if airflow dags list -o plain 2>/dev/null | grep -q "g06_bronze"; then
      airflow dags trigger g06_bronze && echo "[init] primera corrida de g06_bronze disparada"
      break
    fi
    sleep 5
  done
) &

# 4) La UI y la API
exec airflow api-server
