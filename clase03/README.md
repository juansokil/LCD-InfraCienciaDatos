# Clase 03: Ingesta Profesional (Capa Bronze)

> 📚 **Cómo está estructurada esta clase** (patrón compartido por clase03/04/05):
>
> 1. **Notebook teórico** ([`clase03.ipynb`](clase03.ipynb)) — conceptos + DAGs demo sobre datos sintéticos (CSV/JSON locales)
> 2. **Ejercicio práctico** ([`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb)) — los mismos conceptos sobre CoinGecko
> 3. **DAG productivo** ([`ejercicios/dag_crypto_bronze.py`](ejercicios/dag_crypto_bronze.py)) — para copy-paste a Airflow

> **Material de la clase**:
> - [`clase03.ipynb`](clase03.ipynb) — desarrollo teórico: ingesta multi-formato, idempotencia con SHA256, Hive Partitioning, Row-hashing.
> - [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) — ejercicio **opcional**: ingesta desde API real (CoinGecko).
> - [`ejercicios/dag_crypto_bronze.py`](ejercicios/dag_crypto_bronze.py) — DAG productivo de ingesta crypto a Bronze (con comentarios educativos).

---

## 🎯 Objetivos

- Implementar la **Capa Bronze** usando Airflow.
- Dominar la **Idempotencia** mediante hashing SHA256 de archivos.
- Aplicar **Hive Partitioning** para organizar el Data Lake.
- Practicar **Row-level Hashing** para detectar cambios sin comparaciones pesadas.

## 🥉 Capa Bronze: Fuente de Verdad

Inmutable. **No limpiamos datos acá** — solo aseguramos llegada con metadatos de auditoría:
- `ds`: fecha lógica de ejecución
- `source_file`: nombre del archivo original
- `file_hash`: identificador único de contenido para evitar duplicados

> **Importante**: nunca borres la Capa Bronze. Si las reglas de limpieza cambian en el futuro, Bronze es lo único que permite reconstruir todo el historial.

---

## 🚀 Setup

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`).
- Tu rama personal sincronizada (ver root README → "Cómo Consumir el Repo Semana a Semana").

---

## 📋 Cómo trabajar la clase

### Paso 1 — Leer el notebook teórico

Abrí `clase03.ipynb`. El notebook explica los conceptos y al ejecutarse genera **3 DAGs** automáticamente vía celdas `%%writefile`:

| DAG generado | Path destino | Qué hace |
|--------------|--------------|----------|
| `dag_ingesta_simple.py` | `stack/dags/01-bronze/` | CSV local → Postgres (append) |
| `dag_ingesta_simple_profesional.py` | `stack/dags/01-bronze/` | CSV con idempotencia por file hash |
| `dag_ingesta_multiple.py` | `stack/dags/00-playground/` | Multi-formato (CSV/JSON) con landing/processed/quarantine |

Después de ejecutar las celdas, los DAGs aparecen automáticamente en Airflow UI (`localhost:8080`).

### Paso 2 — (Opcional) Hacer el ejercicio práctico

Abrí `ejercicios/ejercicio.ipynb` para practicar con datos reales desde la **API CoinGecko**. Es práctica personal sin entrega comprometida.

### Paso 3 — Correr el DAG productivo en Airflow

`ejercicios/dag_crypto_bronze.py` es el DAG productivo de ingesta crypto **con comentarios explicando cada decisión**. Para verlo correr en Airflow:

```bash
cp clase03/ejercicios/dag_crypto_bronze.py stack/dags/01-bronze/
```

Airflow detecta el archivo automáticamente (volumen montado) y lo muestra en la UI. Activalo con el toggle y mirá los datos llegar a `bronze.crypto_markets` y `bronze.global_market`.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| El DAG no aparece en Airflow UI | Verificar que el archivo esté en `stack/dags/01-bronze/`. Esperar 10-30s para que Airflow lo detecte (refresh interval). |
| `ModuleNotFoundError: requests` (en el DAG crypto) | El módulo viene en el Dockerfile del stack. Si falla, rebuild: `docker compose down && docker compose up -d --build`. |
| Error de conexión a Postgres dentro del DAG | Las credenciales se leen de variables de entorno (`SOURCE_DB_*`). Verificar que `stack/.env` esté presente. |
| El DAG corre pero no veo datos | Conectarte a Postgres (`localhost:5432`, user `admin`, db `InfraCienciaDatos`) y consultar `bronze.crypto_markets`. |
