# Clase 03: Ingesta Profesional (Capa Bronze)

> 📚 **Cómo está estructurado este ejercicio** (patrón compartido por ejercicios 03/04/05):
>
> 1. **Notebook teórico** ([`clase03.ipynb`](clase03.ipynb)) — conceptos + DAGs demo sobre datos sintéticos (CSV/JSON locales)
> 2. **Ejercicio práctico** ([`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb)) — los mismos conceptos sobre CoinGecko
> 3. **DAG productivo** ([`ejercicios/dag_crypto_bronze.py`](ejercicios/dag_crypto_bronze.py)) — para copy-paste a Airflow

> **Material de la clase**:
> - [`clase03.ipynb`](clase03.ipynb) — desarrollo teórico: ingesta multi-formato (CSV/JSON/JSONL/Parquet), idempotencia con SHA256 de archivos, Hive Partitioning y guardado del payload crudo.
> - [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) — ejercicio **con entrega**: ingesta desde API real (CoinGecko). Genera tu `.txt` en `ejercicios/estudiantes/` (ver [`ejercicios/README.md`](ejercicios/README.md)).
> - [`ejercicios/dag_crypto_bronze.py`](ejercicios/dag_crypto_bronze.py) — DAG productivo de ingesta crypto a Bronze (con comentarios educativos).

---

## 🎯 Objetivos

- Implementar la **Capa Bronze** usando Airflow.
- Dominar la **Idempotencia** mediante **hashing SHA256 de archivos** (unidad = archivo: si el mismo archivo vuelve a llegar, se reemplaza su carga en vez de duplicarla).
- Aplicar **Hive Partitioning** para organizar el Data Lake.
- Guardar el **payload crudo** completo, para poder reprocesar sin volver a llamar a la fuente.
- Definir un **Data Contract** declarativo (YAML) y validar la **forma** de los archivos contra él (extensión, encoding, delimiter, columnas presentes). La validación de **valores** es responsabilidad de Silver (clase 04).

## 🥉 Capa Bronze: Fuente de Verdad

Inmutable. **No limpiamos datos acá** — solo aseguramos llegada con metadatos de auditoría:
- `ds`: fecha lógica de ejecución
- `source_file`: nombre del archivo original
- `file_hash`: identificador único de contenido para evitar duplicados

> **Importante**: nunca borres la Capa Bronze. Si las reglas de limpieza cambian en el futuro, Bronze es lo único que permite reconstruir todo el historial.

---

## 🚀 Setup

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`).

**Sincronizá tu rama con el material nuevo.** Cada clase trae material nuevo en `main`. Antes de empezar a trabajar, traete los cambios:

```bash
# 1. Bajar lo nuevo de main
git checkout main
git pull origin main

# 2. Volver a tu rama personal y mergear
git checkout estudiante/apellido-nombre   # reemplazá por tu rama
git merge main --no-edit
```

> Vas a repetir esto al empezar **cada** clase. El detalle de cada comando está en el [README raíz](../README.md), sección "Cómo Consumir el Repo Semana a Semana".

---

## 📋 Cómo trabajar la clase

### Paso 1 — Leer el notebook teórico

Abrí `clase03.ipynb`. El notebook explica los conceptos y al ejecutarse genera **4 DAGs sintéticos numerados** automáticamente vía celdas `%%writefile`. La numeración refleja la **escalera pedagógica** (cada uno suma un patrón profesional encima del anterior):

| # | DAG generado | Path destino | Qué aporta |
|---|--------------|--------------|------------|
| — | (teoría — no archivo) | — | Carga manual con pandas (`to_sql`) a `bronze.test_manual_notebook`, **sin idempotencia**. Solo para entender la mecánica básica. |
| 01 | `bronze_01_simple.py` | `stack/dags/01-bronze/` | + **Idempotencia** por SHA256 de archivo + Hive partitioning (`processed/ds=YYYY-MM-DD/`) |
| 02 | `bronze_02_multiple.py` | `stack/dags/01-bronze/` | + **Multi-formato** (CSV/JSON/JSONL) + **quarantine** para archivos rotos (con for-loop manual) |
| 03 | `bronze_03_dynamic.py` | `stack/dags/01-bronze/` | Refactor de `bronze_02_multiple` con **Dynamic Task Mapping** (`.expand()`) — una task por archivo, paralelizable y con aislamiento de errores |
| 04 | `bronze_04_con_contrato.py` | `stack/dags/01-bronze/` | + **Data Contract YAML** — valida la forma del archivo contra `stack/data/contracts/ventas.yaml` antes de cargar |

Después de ejecutar las celdas, los DAGs aparecen automáticamente en Airflow UI (`localhost:8080`). En la UI, filtrá por **tag `bronze`** para verlos juntos.

> **Convención de carpetas**: cada DAG vive en la carpeta de su **capa Medallion destino** (`01-bronze/` para todo lo que escribe a `bronze.*`, `02-silver/` para Silver, etc.). El `00-playground/` queda reservado para demos del API de Airflow que NO escriben a la DB (los demos `demo_01/02/03` de la clase 02).
>
> **Convención de tags**: sintéticos didácticos llevan `tags=["bronze"]`. El DAG productivo (crypto) lleva `tags=["prod", "bronze", "crypto"]` para distinguirlo en la UI con el filtro `prod`.

### Paso 2 — Hacer el ejercicio práctico (con entrega)

Abrí `ejercicios/ejercicio.ipynb` para practicar con datos reales desde la **API CoinGecko**. Al final, la sección **📦 Entrega** te genera automáticamente tu archivo `ejercicios/estudiantes/<apellido>-<nombre>.txt` y te indica cómo subirlo (solo commit + push: tu PR se actualiza solo). Reglas completas en [`ejercicios/README.md`](ejercicios/README.md).

**Commit y push.** Reemplazá `<apellido>-<nombre>` por el filename que te imprimió la sección 📦 Entrega. Desde la raíz del repo:

```bash
git add clase03/ejercicios/estudiantes/<apellido>-<nombre>.txt
git commit -m "ejercicio03: ejercicio bronze"
git push origin estudiante/apellido-nombre
```

> ⚠️ **No** uses `git add .` ni commitees el `.ipynb` modificado — es un template compartido entre todos los estudiantes.

> **Una rama para siempre, un PR para siempre**: tu rama `estudiante/apellido-nombre` y tu PR son los mismos desde la Clase 01; el push actualiza ese mismo PR (no abrís uno nuevo). Detalle en el [README raíz](../README.md).

### Paso 3 — Correr el DAG productivo en Airflow

`ejercicios/dag_crypto_bronze.py` es el DAG productivo de ingesta crypto **con comentarios explicando cada decisión**. Para verlo correr en Airflow:

```bash
cp clase03/ejercicios/dag_crypto_bronze.py stack/dags/01-bronze/
```

Airflow detecta el archivo automáticamente (volumen montado) y lo muestra en la UI. A diferencia de los DAGs didácticos, este trae `is_paused_upon_creation=False`: **arranca despausado solo**, no hace falta tocar el toggle. Mirá los datos llegar a `bronze.crypto_markets` y `bronze.global_market`.

> [!WARNING]
> Apenas copiás el archivo, el DAG empieza a pegarle a la API de CoinGecko **cada 15 minutos** (`schedule="0,15,30,45 * * * *"`) y sigue haciéndolo mientras el stack esté levantado. Si no querés eso corriendo de fondo, **pausalo con el toggle** en la UI después de la primera corrida.

> Filtrá por tag **`prod`** en la UI para ver solo los DAGs productivos (separa el "DAG real" de la escalera didáctica `bronze_01_*` → `bronze_04_*`).

---

## ✅ Verificación end-to-end

Después de correr los DAGs sintéticos + el productivo crypto, estas 3 verificaciones tienen que dar bien (con pandas, desde un notebook):

```python
import pandas as pd
import sqlalchemy
engine = sqlalchemy.create_engine('postgresql://admin:admin@localhost:5432/InfraCienciaDatos')

# 1. ¿Bronze tiene datos del DAG productivo crypto?
crypto = pd.read_sql_table('crypto_markets', engine, schema='bronze')
print(len(crypto), crypto['ingested_at'].max())
# Esperado: > 0 (ej: 50 filas por snapshot, varios snapshots)

# 2. ¿Cuántos archivos sintéticos se procesaron?
ventas = pd.read_sql_table('ventas_simple', engine, schema='bronze')
print(ventas.groupby(['source_file', 'file_hash']).size())
# Esperado: una fila por archivo procesado (ventas_legacy.csv, etc.)

# 3. ¿La idempotencia funciona? (mismo contenido NO duplica filas)
print(ventas['file_hash'].nunique(), len(ventas), ventas['source_file'].nunique())
# Esperado: si subiste 2 archivos con el mismo contenido (experimento `ventas_duplicado_a/b.csv`),
# hashes distintos == archivos distintos < total de archivos físicos. La tabla NO se duplica.
```

Si las 3 dan valores razonables, tu pipeline Bronze está **funcional + idempotente + auditable**.

---

## 🔮 Forward reference a Silver (clase 04)

Hasta acá tenemos `bronze.*` con datos crudos (forma validada por contrato `ventas.yaml` + idempotencia por SHA256 + audit metadata). En la **clase 04** vamos a:

| Concepto | Qué construimos |
|---|---|
| **Pydantic dinámico desde YAML** | `build_pydantic_from_contract(load_contract("ventas.yaml"))` genera el modelo en runtime — sin clase hardcodeada |
| **Pattern Quarantine** | Filas que fallan el contrato NO se descartan — van a `silver.quarantine_*` con `quarantine_reason` (motivo Pydantic estructurado) |
| **Audit metadata por capa** | `silver_at`, `quarantined_at`, `_processed_at`, `_source_table`, `_contract_version` para lineage completo |
| **SCD Tipo 2** | Historizar cambios usando los campos del bloque `scd:` del YAML (`business_key`, `tracked_columns`, `effective_date`) |
| **Upsert** (insertar o actualizar) | Idempotencia a nivel fila — el DAG puede fallar a la mitad y reanudarse sin duplicar |

> 🔁 **El círculo se cierra**: el contrato YAML que validó la **forma** del archivo en Bronze ahora valida la **semántica** de cada fila en Silver. **Un contrato, dos capas, dos responsabilidades**.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| El DAG no aparece en Airflow UI | Verificar que el archivo esté en `stack/dags/01-bronze/`. Esperar 10-30s para que Airflow lo detecte (refresh interval). |
| `ModuleNotFoundError: requests` (en el DAG crypto) | El módulo viene en el Dockerfile del stack. Si falla, rebuild: `docker compose down && docker compose up -d --build`. |
| Error de conexión a Postgres dentro del DAG | Las credenciales se leen de variables de entorno (`SOURCE_DB_*`). Verificar que `stack/.env` esté presente. |
| El DAG corre pero no veo datos | Conectarte a Postgres (`localhost:5432`, user `admin`, db `InfraCienciaDatos`) y consultar `bronze.crypto_markets`. |
| `ventas_columnar.parquet` cae en quarantine con `ImportError` | Falta `pyarrow` dentro de la imagen de Airflow. Rebuild: `docker compose up -d --build`. (Si el `.parquet` tampoco se genera desde el notebook, instalá `pyarrow` en tu entorno local.) |
| `NameError: generar_archivos_demo_ventas` | Ejecutaste una celda de siembra sin haber corrido antes la celda que define el sembrador (sección **🌱 El sembrador**, arriba de todo). Corré esa celda primero. |
