set -euo pipefail

python - <<'PY'
import json
import os
import time
import urllib.request
import urllib.error

BASE_URL = os.getenv(
    "AIRFLOW_API_URL",
    "http://airflow-api-server:8080"
).rstrip("/")

DAG_ID = "bronze_clima"
RUN_ID = "bootstrap__initial"

USERNAME = os.environ["AIRFLOW_USERNAME"]
PASSWORD = os.environ["AIRFLOW_PASSWORD"]


def request(method, path, token=None, payload=None):
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 409):
            return exc.code, None
        raise


print("Bootstrap: esperando autenticacion de Airflow...", flush=True)

token = None

for intento in range(60):
    try:
        _, respuesta = request(
            "POST",
            "/auth/token",
            payload={
                "username": USERNAME,
                "password": PASSWORD,
            },
        )
        token = respuesta["access_token"]
        break
    except (urllib.error.URLError, TimeoutError):
        time.sleep(3)
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            time.sleep(3)
        else:
            raise

if not token:
    raise RuntimeError("No se pudo autenticar en Airflow")


print("Bootstrap: esperando DAG bronze_clima...", flush=True)

dag_path = f"/api/v2/dags/{DAG_ID}"

for intento in range(60):
    try:
        status, dag = request("GET", dag_path, token)

        if status == 200 and not dag["is_paused"]:
            if dag.get("is_stale") or dag.get("has_import_errors"):
                time.sleep(3)
                continue
            break

    except (urllib.error.URLError, TimeoutError):
        pass

    time.sleep(3)
else:
    raise RuntimeError("Bronze no esta registrado o activo")


runs_path = f"{dag_path}/dagRuns"

status, _ = request(
    "GET",
    f"{runs_path}/{RUN_ID}",
    token,
)

if status == 200:
    print("Bootstrap: ejecucion inicial ya existente.")
elif status == 404:
    status, _ = request(
        "POST",
        runs_path,
        token,
        payload={
            "dag_run_id": RUN_ID,
            "logical_date": None,
            "conf": {"origen": "bootstrap"},
        },
    )

    if status == 409:
        print("Bootstrap: ejecucion creada previamente.")
    else:
        print("Bootstrap: Bronze disparado correctamente.")
else:
    raise RuntimeError(f"Respuesta inesperada: {status}")

print("Bootstrap finalizado.")
PY