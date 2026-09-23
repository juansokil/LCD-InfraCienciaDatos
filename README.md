# 🏗️ LCD — Infraestructura para Ciencia de Datos (UNSAM)

[![GitHub](https://img.shields.io/badge/GitHub-LCD--InfraCienciaDatos-181717?logo=github)](https://github.com/juansokil/LCD-InfraCienciaDatos)

Repositorio de **Infraestructura para Ciencia de Datos** — Licenciatura en Ciencia de Datos, Universidad Nacional de San Martín.

---

## 📚 Contenido Clase por Clase

### 🚀 **Fundamentos y Setup**

#### Clase 01: Ingeniería de Datos — Data Pipelines - Arquitectura Medallion
- Fundamentos de Data Engineering
- Modelado dimensional: Star Schema, dimensions, fact tables
- Slowly Changing Dimensions (SCD): panorama de tipos (la implementación llega en la Clase 04)
- Arquitectura Medallion: Bronze, Silver, Gold
- Primer push con Git al repo de la materia

#### Clase 02: Instalación del Stack y Tutorial de Airflow
- Stack Docker: Postgres + Airflow + Streamlit + MLflow
- Apache Airflow **3.1.5**: TaskFlow API, decoradores `@dag` y `@task`
- Branching y XComs (el Dynamic Task Mapping llega en la Clase 03)
- Buenas prácticas: idempotencia, atomicidad, determinismo
- Instalación + verificación local del stack

### 🥉 **Capa Bronze: Ingesta**

#### Clase 03: Ingesta Profesional (Capa Bronze)
- Implementación de la Capa Bronze con Airflow
- Idempotencia mediante hashing SHA256 de archivos
- Hive Partitioning para organización del Data Lake
- Row-level hashing para detección de cambios
- DAGs de ingesta CSV/JSON/multi-formato

### 🥈 **Capa Silver: Limpieza**

#### Clase 04: La Refinería (Capa Silver)
- Transformación Bronze → Silver
- Contratos de datos declarativos (YAML) + validación fila a fila con Pydantic
- Reglas de calidad que **corren de verdad**, con dos severidades: `error` manda el registro a cuarentena, `warning` lo deja pasar marcado
- Métricas de calidad por corrida (`silver.quality_runs`): un número suelto no dice nada, la señal es el cambio
- Limpieza avanzada: tipado estricto, deduplicación idempotente
- Patrón de Cuarentena para registros inválidos
- SCD Tipo 2 con SQL

### 🥇 **Capa Gold: Analytics**

#### Clase 05: La Bóveda (Capa Gold)
- Star Schema en producción (Hechos y Dimensiones)
- **Claves sustitutas**: por qué el hecho no guarda la clave del negocio
- Integridad referencial: qué es un **huérfano**, cómo aparece y cómo se lo detecta antes de que llegue al tablero
- Capa Semántica y métricas gobernadas: las vistas `gold.v_*` que consume el dashboard
- Dashboard Streamlit pre-construido (consume tablas Gold)

### 🏁 **Cierre**

#### Clase 06: MLOps — del pipeline al modelo en producción
- Recap del cuatrimestre: pipeline completo + decisiones técnicas + errores típicos
- El **switch a modo producción**: se retira el andamiaje pedagógico, la cadena queda encadenada por **Assets** (un solo cron, en Bronze) y se ve cómo se monitorea
- La **ABT**: la forma de tabla con la que se entrena un modelo — llega acá, que es donde se usa
- **Elegir la pregunta antes que el modelo**: predecir la *dirección* del precio no funciona ni puede funcionar; predecir **qué criptos van a ser las más movidas** sí, porque la volatilidad se agrupa en el tiempo
- Tres modelos con la misma pregunta y distinta historia (**1, 3 y 7 días**): mirar más atrás ayuda, y se ve
- Validación honesta: walk-forward por fechas, **dos baselines** (la clase mayoritaria, que es la vara fácil, y la persistencia *«mañana se repite lo de hoy»*, que es la que de verdad hay que ganar), lección de target leakage
- Tracking con MLflow: un modelo registrado por ventana, cada uno con su alias `@champion`
- El tablero **corrige al modelo** contra lo que pasó: accuracy por ventana, evolución y desagregado por cripto
- 🎁 Bonus track: introducción a MLOps (Feature Stores, Drift, Model Registry)
- 📦 **La entrega**: *El veredicto* — siete candidatos esperando en el tracking y una decisión, cuál iría a producción o si ninguno está listo

---

## 🎓 Patrón Pedagógico (Clases 03 a 06)

Las clases que arman el pipeline (**Bronze → Silver → Gold**) y la de cierre (**ML sobre Gold**) siguen un patrón uniforme de **3 capas pedagógicas**:

| Capa | Archivo | Datos | Para qué |
|---|---|---|---|
| **1. Teórica** | `claseNN.ipynb` | sintéticos hardcoded | Conceptos + DAGs demo (vía celdas `%%writefile` que generan archivos en `stack/dags/`) |
| **2. Práctica** | `ejercicios/ejercicio.ipynb` | CoinGecko en clase 03; SQL sobre Northwind en 04–05; runs de MLflow en 06 | Aplicar los conceptos: ingesta real (03), el SQL que Silver y Gold usan (04–05) y leer el tracking para decidir (06) |
| **3. Productiva** | `ejercicios/dag_crypto_*.py` | CoinGecko API real | DAG listo para copy-paste a Airflow (`cp` al stack) |

**Detalle por clase:**

| Clase | Notebook teórico genera | Ejercicio práctico (entrega) | DAG productivo |
|---|---|---|---|
| **03 — Bronze** | 4 DAGs progresivos sobre CSV/JSON locales (simple con idempotencia SHA256 → multi-formato + cuarentena → **Dynamic Task Mapping** → contrato YAML) | Top 50 cryptos (CoinGecko) → el JSON crudo al lake (`stack/data/raw/`) → `bronze.crypto_markets_demo` | `dag_crypto_bronze.py` |
| **04 — Silver** | 2 DAGs sobre `bronze.ventas_demo` sintético (limpieza básica → Pydantic + Quarantine) | 10 ejercicios SQL sobre Northwind (fundamentos de Silver + anti-join, dedup y cuarentena) | `dag_crypto_silver.py` |
| **05 — Gold** | 1 DAG sobre `silver.ventas_demo` sintético (Star Schema) + el chequeo de integridad referencial en vivo y el consumo del star, en el notebook | 6 queries SQL sobre Northwind (G1–G6) que arman, paso a paso, **una misma tabla Gold**: el grano, el JOIN con la dimensión, `HAVING`, `CASE`, participación y ranking con *window functions*, y `LAG` | `dag_crypto_gold.py` |
| **06 — ML sobre Gold** | 1 DAG sobre el star sintético (la **ABT**) + el workshop de ML sobre el hecho productivo, en el notebook | *El veredicto*: siete candidatos en MLflow, una decisión y su porqué | `dag_crypto_ml.py` |

**Por qué este diseño:**

- La **notebook teórica** usa datos sintéticos hardcoded → cero dependencias entre clases. Cualquiera puede correr el cell `%%writefile` y disparar el DAG demo sin necesidad de haber corrido la clase anterior.
- El **ejercicio** aplica lo aprendido: en clase 03 sobre datos reales "vivos" (CoinGecko); en clase 04–05 sobre **SQL en Northwind** (los fundamentos SQL que Silver y Gold usan a nivel de registro y de agregación); en clase 06 sobre el **tracking de MLflow**, que es donde se decide qué modelo se promueve.
- El **DAG productivo** es el "código listo" (crypto, las cuatro clases): un `cp` al stack y queda corriendo en Airflow. Juntos forman la cadena completa — `crypto_bronze` → `crypto_silver` → `crypto_gold` → `crypto_ml`.

> **Clase 06 cierra el patrón con otra materia prima.** Las tres capas están: el
> notebook teórico genera su DAG demo (`gold_02_abt.py`, la ABT sobre datos
> sintéticos), hay ejercicio con entrega (*El veredicto*) y hay DAG productivo
> (`ejercicios/dag_crypto_ml.py`), que cierra la cadena consumiendo la ABT de Gold.
> Lo que cambia es **sobre qué se practica**: no SQL, sino leer el tracking y
> decidir con lo que dice. Y la entrega es corta a propósito — el trabajo grande de
> esa semana es el **TP Final**.

### 🎓 **El TP Final**

Se entrega en grupo al final del cuatrimestre, pero **conviene leerlo desde la clase 01**: lo primero que hay que hacer es elegir la API, y esa decisión condiciona todo lo demás.

- **[Consigna completa](TpFinal/README.md)** — qué se entrega, ideas de API y el esqueleto sugerido
- **[Consigna de la presentación](TpFinal/consigna_presentacion.pdf)** — qué mostrar y cómo, el día de la defensa
- **[Guía de git para el grupo](TpFinal/git-guia.md)** — trabajar en la misma rama sin pisarse

---

## 🛠️ Stack Tecnológico

| Componente | Versión | Dónde corre |
|---|---|---|
| **Python** | 3.11 (Pandas, SQLAlchemy) | tu máquina + Docker |
| **Orquestación** | **Apache Airflow 3.1.5** (`apache/airflow:3.1.5-python3.11`) | Docker |
| **Bases de datos** | PostgreSQL 17 (producción) · DuckDB (analítica local) | Docker / local |
| **Visualización** | Streamlit (dashboard sobre tablas Gold) | Docker |
| **IA/ML** | Scikit-Learn + MLflow 3.4.0 (tracking + Model Registry, clase 06) | Docker |
| **Contenerización** | Docker & Docker Compose | tu máquina |

> ⚠️ **La versión de Airflow no es un detalle: usamos 3.1.5.** Airflow 3 rompió
> compatibilidad con el 2 (`schedule_interval` dejó de existir, `webserver` pasó a
> ser `api-server`), así que el código y los tutoriales de Airflow 2 que encuentren
> dando vueltas **no corren tal cual**. Todo lo que vemos en clase — TaskFlow API,
> Assets, la UI — es de la 3.x, y el **TP Final la exige**.

---

## 🚀 Cómo empezar

Para tu **primera entrega** seguí la guía paso a paso de la Clase 01:

👉 [`clase01/README.md`](clase01/README.md) — registro al onboarding, clone, rama personal, primer commit, push y Pull Request.

> **Cómo se llama tu rama**: `estudiante/<apellido>-<nombre>`, en minúsculas, sin tildes y con **un solo guión** (el que separa apellido de nombre). Si tenés más de un nombre o más de un apellido, **van pegados**: María José García López → `estudiante/garcialopez-mariajose`. Un workflow de GitHub cierra automáticamente los PRs cuya rama no cumple la convención, con un comentario que explica cómo arreglarlo.

> **Importante**: tu **rama** personal (`estudiante/apellido-nombre`) la creás **una sola vez** y la reusás para **todas** las entregas (no la borres, no crees una nueva cada semana). El **Pull Request** lo abrís **una sola vez** (en la Clase 01) y lo dejás **abierto**: cada entrega siguiente es solo un `push` a la misma rama y el PR se actualiza solo. Una rama para siempre, un PR para siempre. **El PR no se mergea nunca** (tampoco al final del cuatrimestre): es la ventana por donde el docente revisa tus entregas, no un cambio a incorporar a `main`.

---

## 📅 Cómo Consumir el Repo Semana a Semana

A partir de la Clase 02, cada semana repetís estos pasos sobre tu rama personal.

### 1. Posicionate en `main` y bajá el material nuevo

```bash
git checkout main
git pull origin main
```

- `git checkout main` te mueve a la rama oficial del curso.
- `git pull` baja desde GitHub lo que el docente subió esta semana (clase nueva, fixes, etc.).

### 2. Volvé a tu rama personal y traete los cambios

```bash
git checkout estudiante/apellido-nombre
git merge main --no-edit
```

- `git checkout estudiante/apellido-nombre` te devuelve a tu rama (donde hacés tus entregas).
- `git merge main --no-edit` incorpora a tu rama todo lo nuevo que bajó `main`. El `--no-edit` evita que Git abra un editor pidiéndote mensaje del merge — acepta el default y listo.

> Si te olvidás del `--no-edit` y se abre Vim, salís con `:wq` (dos puntos + w + q + Enter).

### 3. Trabajá la clase

Abrí `claseXX/README.md` para entender el objetivo y leer las instrucciones del ejercicio. En general:
- Leer el desarrollo teórico en `claseXX/claseXX.ipynb`
- Resolver los ejercicios indicados
- Generar tu archivo de entrega según pida cada clase (**siempre un `.txt`**). **El `.ipynb` nunca se entrega**: es template compartido y generaría conflictos.

### 4. Commiteá y subí tu trabajo

```bash
git add <ruta-de-tu-archivo-de-entrega>
git commit -m "claseNN (Tema)"
git push origin estudiante/apellido-nombre
```

- `git add ...` → selecciona **qué** archivo subir. Usá la ruta exacta (no `git add .`) para evitar subir cosas que no querés.
- `git commit -m "..."` → guarda el cambio localmente. **El mensaje lo dice el ejercicio de cada clase**: `clase01 (Registro)`, `clase02 (Stack)`, `clase03 (Bronze)`, `clase04 (Silver)`, `clase05 (Gold)`, `clase06 (MachineLearning)`.
- `git push origin estudiante/apellido-nombre` → sube tu commit a GitHub, a tu rama.

### 5. Tu Pull Request se actualiza solo (no abrís uno nuevo)

Si ya abriste tu PR en la Clase 01, **acá no tenés que hacer nada más**: el `git push` del paso 4 actualiza automáticamente tu PR abierto. El docente revisa tu nueva entrega ahí.

> **¿No abro un PR nuevo cada semana?** No. Tu PR (`estudiante/apellido-nombre` → `main`) lo abriste **una sola vez** en la Clase 01 y queda **abierto** todo el cuatrimestre. Cada push se suma a ese mismo PR. El docente identifica cada entrega por el commit `claseNN (Tema)` y el `.txt` nuevo que aparece.
>
> Igual, **cada semana arrancás por el paso 1** (sincronizar con `main`) para traer el material nuevo del curso a tu rama.

### 6. Cómo leer el estado de tu PR

Tu PR es el tablero de tu cuatrimestre. Vale la pena saber qué significa cada cosa que vas a ver ahí, porque **algunas señales piden acción y otras no**.

| Lo que ves | Qué significa | Qué hacés |
| :--- | :--- | :--- |
| 🟢 **Open**, sin marcas | Todo en orden: tus entregas llegaron | Nada. Seguí con la clase siguiente |
| 💬 **Comment** del docente | Un comentario suelto: una observación, una pregunta, una sugerencia | Leelo. Si te pregunta algo, respondé en el mismo hilo |
| 🔴 **Changes requested** | El docente **rechazó una entrega**: algo hay que corregir | Leé el review, corregí, `commit` + `push` **a la misma rama**. Eso actualiza el PR y la marca se levanta |
| ❌ **Check en rojo** al abrir el PR | El robot de convenciones: tu **rama está mal nombrada** | Renombrá la rama y abrí un PR nuevo (el comentario del robot te da los comandos exactos) |
| 🟣 **Merged** | **Nunca va a pasar** | — |

Dos cosas que conviene tener claras desde el principio:

**"Changes requested" no cierra tu PR.** Sigue abierto y sigue siendo el mismo de siempre: no abras uno nuevo, no crees otra rama. Corregís, pusheás, y ese mismo push limpia la marca. Es feedback, no una puerta cerrada.

**Que tu PR nunca se mergee no es una nota.** No es que "no aprobaste": es cómo está diseñado el curso. Tu rama es tu espacio de trabajo y el PR es la ventana por donde el docente lo mira. Un PR abierto, con pushes semanales y sin marcas rojas, es exactamente lo que tiene que verse.

> **El único caso en que un PR del curso se cierra antes de tiempo** es el de la rama mal nombrada, y pasa en la Clase 01 o no pasa nunca. Si el nombre está bien, tu PR queda abierto hasta el cierre del cuatrimestre.
