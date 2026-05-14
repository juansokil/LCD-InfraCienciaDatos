# Clase 02: Instalación del Stack de Trabajo

> **Material de la clase**:
> - [`clase02.ipynb`](clase02.ipynb) — desarrollo en clase: instalación del stack + tutorial de Airflow (TaskFlow API, branching, XComs).
> - Este `README.md` — entrega práctica: dejar el laboratorio listo y verificarlo.
> - [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) — script de verificación del stack.

---

## 🛠️ Stack: opción A o opción B

Para esta materia necesitás un stack con **Airflow + Postgres + Streamlit** levantado. Tenés dos caminos — la decisión es tuya:

| Opción | Para quién | Esfuerzo |
|---|---|---|
| **A. Stack del curso** (recomendada) | Querés arrancar rápido y enfocarte en el contenido | `docker compose up -d` y listo |
| **B. Stack propio** | Querés armar tu propio `docker-compose.yml` y aprender el setup | Más control, más trabajo |

> Si elegís la **opción B**, tu stack tiene que cumplir: Postgres expuesto en `localhost:5432`, db `InfraCienciaDatos`, credenciales `admin/admin`, schemas `bronze`/`silver`/`gold` creados, Airflow en `localhost:8080`. El script de verificación (Paso 4) valida estas piezas — si pasa, vas bien independientemente del stack que hayas armado.

El resto de esta clase asume la **opción A** (más simple). Si vas con la B, saltá los pasos de instalación y andá directo al Paso 4.

---

## 🎯 Objetivo de esta entrega

Dejar instalado y funcionando un stack de trabajo (del curso o propio) y subir el resultado de la verificación.

## 🧱 ¿Qué vamos a instalar?

| Componente | Para qué sirve | Puerto |
|------------|---------------|--------|
| **Entorno Python** | Correr notebooks y scripts del curso. | — |
| **Docker Desktop** | Levantar todos los servicios sin instalar nada nativo en tu PC. | — |
| **Postgres (Data Warehouse)** | Base de datos del curso (Bronze / Silver / Gold). | `5432` |
| **Airflow** | Orquestador de pipelines. | `8080` |
| **Streamlit Dashboard** | Visualización BI. | `8501` |

---

## ✅ Prerequisito

Tener la **Clase 01 lista**: tu rama personal `apellido-nombre` ya creada y con tu primer push hecho. Si todavía no la hiciste, andá a [`../clase01/README.md`](../clase01/README.md) primero.

---

**Paso 1 — Sincronizá tu rama con el material nuevo**

Cada clase trae material nuevo en `main`. Antes de empezar a trabajar, traete los cambios:

```bash
# 1. Bajar lo nuevo de main
git checkout main
git pull origin main

# 2. Volver a tu rama personal y mergear
git checkout apellido-nombre
git merge main
```

> **Tip**: vas a repetir esto al empezar **cada** clase.

---

**Paso 2 — Creá tu entorno Python**

Tres opciones (elegí una). Las dependencias del **entorno local** del alumno están en [`requirements.txt`](../requirements.txt) (raíz del repo).

> El `stack/requirements.txt` es para el Docker de Airflow — no es el que usás vos localmente.

### Opción A: conda
```bash
conda create -n airflow python=3.11 -y
conda activate airflow
pip install -r requirements.txt
```

### Opción B: venv
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Opción C: uv (más rápido, moderno)
```bash
uv venv
uv pip install -r requirements.txt
```

---

**Paso 3 — Levantá el stack Docker**

> Si elegiste la **opción B** (stack propio), saltá este paso y andá directo al Paso 4.

Asegurate de tener **Docker Desktop abierto** y con al menos **4 GB de RAM** asignados (Settings → Resources → Memory).

Desde la raíz del repo:
```bash
cd stack
docker compose up -d
```

La primera vez tarda unos minutos (baja imágenes). Levanta cuatro contenedores:

| Contenedor | Servicio |
|------------|----------|
| `airflow_standalone` | Airflow (UI en `localhost:8080`) |
| `airflow_db` | Postgres interno de Airflow (no expuesto) |
| `data_warehouse` | Postgres del curso (`localhost:5432`) |
| `dashboard` | Streamlit (`localhost:8501`) |

Verificá que estén corriendo:
```bash
docker ps
```

Tenés que ver los 4 contenedores en estado `Up`.

> **Credenciales del Data Warehouse** (las usa el ejercicio):
> - host: `localhost` · puerto: `5432`
> - user: `admin` · pass: `admin` · db: `InfraCienciaDatos`

---

**Paso 4 — Validá la instalación con el ejercicio**

Abrí [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) desde Jupyter o VSCode. Completá tu nombre y apellido, ejecutá la verificación (Paso 2 del notebook) y después generá tu archivo de entrega (Paso 3 del notebook).

El script crea **un archivo único para vos** en `clase02/ejercicios/alumnos/<apellido>-<nombre>.txt` con tu código de verificación.

> **Importante**: leé [`clase02/ejercicios/README.md`](ejercicios/README.md) — el deliverable es **solo el `.txt`**, no el notebook. Esto evita conflictos cuando muchos alumnos suben al mismo tiempo.

---

**Paso 5 — Commit y push**

Reemplazá `<apellido>-<nombre>` por el filename que te imprimió el Paso 3 del notebook (ej: `sokil-juan.txt`). Desde la raíz del repo:

```bash
git add clase02/ejercicios/alumnos/<apellido>-<nombre>.txt
git commit -m "clase02: verificacion de stack"
git push origin apellido-nombre
```

> ⚠️ **No** uses `git add .` ni commitees el `.ipynb` modificado — es un template compartido entre todos los alumnos.

> El PR a `main` ya existe desde la Clase 01. Cada `push` lo actualiza automáticamente — no hace falta crear uno nuevo.

---

## 🛠️ Troubleshooting

| Problema | Solución |
|----------|----------|
| `docker compose up` falla a secas | Verificá que Docker Desktop esté abierto y corriendo |
| `port 5432 already in use` | Tenés otro Postgres local. Pará ese servicio antes de levantar el stack |
| Airflow se queda en "Starting" o falla healthcheck | Subí la RAM en Docker Desktop (Settings → Resources → 4 GB+) |
| `ImportError: pandas` (o cualquier librería) | El entorno virtual no está activado, o faltó `pip install -r requirements.txt` |
| En Windows: bind mounts lentos o no sincronizan | Activá el motor WSL2 en Docker Desktop |
| Nivel 3 (Airflow) falla aunque levantó OK | Esperá 1-2 minutos, Airflow tarda en estar listo después del `up` |

---

## ➡️ Próxima clase

En la **Clase 03** empezamos a escribir DAGs reales sobre este stack.
