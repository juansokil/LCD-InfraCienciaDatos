# 🚀 Orquestación de Datos: DAGs

Esta carpeta contiene los **DAGs (Directed Acyclic Graphs)** que Airflow lee desde `/opt/airflow/dags/` (mount al folder local `./dags`).

---

## 📂 Estructura actual

### `00-playground/`

DAGs de aprendizaje y demos. Los alumnos generan los suyos en la **Clase 02** mediante celdas `%%writefile` del notebook `clase02.ipynb`:

- `demo_01_hola_mundo.py` — primer DAG con TaskFlow API
- `demo_02_secuencia.py` — pasaje de datos entre tareas (XComs implícitos)
- `demo_03_branching.py` — decisiones con `@task.branch`

> El patrón **Dynamic Task Mapping** (`.expand()`) se ve en **Clase 03** aplicado a un caso real: ingesta de N archivos del landing → ver `01-bronze/dag_ingesta_dynamic.py`.

> A medida que avancemos en el cuatrimestre van a aparecer más carpetas con DAGs reales:
> - `01-bronze/` (Clase 03 — Ingesta)
> - `02-silver/` (Clase 04 — Refinería)
> - `03-gold/` (Clase 05 — Serving / Star Schema)

---

## 💡 Conceptos clave

- **TaskFlow API**: Airflow 3 usa decoradores `@dag` y `@task` para definir flujos de manera limpia.
- **Configuración desde `.env`**: las credenciales vienen de variables de entorno, no se hardcodean.
- **Conexiones**: los DAGs reales (de clase 03 en adelante) usan `PostgresHook` con la conexión `database` configurada en Airflow UI.

**¡A orquestar se ha dicho! 🚀🫡**
