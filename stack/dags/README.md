# 🚀 Orquestación de Datos: DAGs

Esta carpeta contiene los **DAGs (Directed Acyclic Graphs)** que Airflow lee desde `/opt/airflow/dags/` (mount al folder local `./dags`).

---

## 📂 Estructura actual

### `00-playground/`

DAGs de aprendizaje y demos. Los estudiantes generan los suyos en la **Clase 02** mediante celdas `%%writefile` del notebook `clase02.ipynb`:

- `demo_01_hola_mundo.py` — primer DAG con TaskFlow API
- `demo_02_secuencia.py` — pasaje de datos entre tareas (XComs implícitos)
- `demo_03_branching.py` — decisiones con `@task.branch`

> El patrón **Dynamic Task Mapping** (`.expand()`) se ve en **Clase 03** aplicado a un caso real: ingesta de N archivos del landing → ver `01-bronze/bronze_03_dynamic.py`.

> A medida que avanzamos en el cuatrimestre aparecen más carpetas con DAGs reales:
> - `01-bronze/` (Clase 03 — Ingesta)
> - `02-silver/` (Clase 04 — Refinería)
> - `03-gold/` (Clase 05 — Serving / Star Schema · Clase 06 — la ABT)
> - `04-ml/` (Clase 06 — un modelo adentro de un DAG)

---

## 💡 Conceptos clave

- **TaskFlow API**: Airflow 3 usa decoradores `@dag` y `@task` para definir flujos de manera limpia.
- **Configuración desde `.env`**: las credenciales vienen de variables de entorno, no se hardcodean.
- **Conexiones**: los DAGs **no usan Hooks ni Airflow Connections**. Arman la URI a mano desde variables de entorno (`SOURCE_DB_USER`, `SOURCE_DB_PASS`, `SOURCE_DB_HOST`, `SOURCE_DB_NAME`), que el `docker-compose.yml` inyecta desde `.env`. Es deliberado: una Connection hay que crearla a mano en la UI la primera vez, y el stack tiene que levantar sin configuración manual. Si abrís **Admin → Connections** no vas a encontrar ninguna, y está bien.

**¡A orquestar se ha dicho! 🚀🫡**
