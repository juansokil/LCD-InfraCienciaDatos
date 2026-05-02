# 🏗️ LCD — Infraestructura para Ciencia de Datos (UNSAM)

[![GitHub](https://img.shields.io/badge/GitHub-LCD--InfraCienciaDatos-181717?logo=github)](https://github.com/juansokil/LCD-InfraCienciaDatos)

Repositorio de **Infraestructura para Ciencia de Datos** — Licenciatura en Ciencia de Datos, Universidad Nacional de San Martín.

---

## 📚 Contenido Clase por Clase

### 🚀 **Fundamentos y Setup**

#### Clase 01: Ingeniería de Datos — Data Pipelines - Arquitectura Medallion
- Fundamentos de Data Engineering y jerarquía del dato
- Modelado dimensional: Star Schema, dimensions, fact tables
- Slowly Changing Dimensions (SCD): Tipos 0, 1, 2, 3, 4, 6
- Arquitectura Medallion: Bronze, Silver, Gold
- Primer push con Git al repo de la materia

#### Clase 02: Instalación del Stack y Tutorial de Airflow
- Stack Docker: Postgres + Airflow + Streamlit
- Apache Airflow 3: TaskFlow API, decoradores `@dag` y `@task`
- Branching, Dynamic Task Mapping, XComs
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
- Contratos de Datos y Data Quality (Pydantic)
- Limpieza avanzada: tipado estricto, deduplicación idempotente
- Patrón de Cuarentena para registros inválidos
- SCD Tipo 2 con SQL

### 🥇 **Capa Gold: Analytics**

#### Clase 05: La Bóveda (Capa Gold)
- Star Schema en producción (Hechos y Dimensiones)
- Analytical Base Tables (ABT) para Machine Learning
- Capa Semántica y métricas gobernadas
- Integridad referencial completa
- Dashboard Streamlit pre-construido (consume tablas Gold)

### 🏁 **Cierre**

#### Clase 06: Workshop End-to-End — ML sobre Gold
- Recap del cuatrimestre: pipeline completo + decisiones técnicas + errores típicos
- Clustering con KMeans: features → elbow → PCA → interpretación
- Clasificación con Random Forest + análisis de feature importance
- Tracking con MLflow: experimentos + comparación de runs
- 🎁 Bonus track: introducción a MLOps (Feature Stores, Drift, Model Registry)

---

## 🛠️ Stack Tecnológico

* **Lenguajes**: Python 3.10+ (Pandas, SQLAlchemy).
* **Bases de Datos**: PostgreSQL (Producción) y DuckDB (Analítica/Local).
* **Orquestación**: Apache Airflow 3.x.
* **Contenerización**: Docker & Docker Compose.
* **IA/ML Support**: Scikit-Learn (conceptos de features) y Feature Store Architecture.

---

## 🚀 Cómo empezar

Para tu **primera entrega** seguí la guía paso a paso de la Clase 01:

👉 [`clase01/README.md`](clase01/README.md) — registro al onboarding, clone, rama personal, primer commit, push y Pull Request.

> **Importante**: la rama personal (`apellido-nombre`) la creás **una sola vez** y la usás para **todas** las entregas del curso. No crees una rama nueva cada semana.

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
git checkout apellido-nombre
git merge main --no-edit
```

- `git checkout apellido-nombre` te devuelve a tu rama (donde hacés tus entregas).
- `git merge main --no-edit` incorpora a tu rama todo lo nuevo que bajó `main`. El `--no-edit` evita que Git abra un editor pidiéndote mensaje del merge — acepta el default y listo.

> Si te olvidás del `--no-edit` y se abre Vim, salís con `:wq` (dos puntos + w + q + Enter).

### 3. Trabajá la clase

Abrí `claseXX/README.md` para entender el objetivo y leer las instrucciones del ejercicio. En general:
- Leer el desarrollo teórico en `claseXX/claseXX.ipynb`
- Resolver los ejercicios indicados
- Generar tu archivo de entrega según pida cada clase (`.md`, `.txt`, notebook, etc.)

### 4. Commiteá y subí tu trabajo

```bash
git add <ruta-de-tu-archivo-de-entrega>
git commit -m "claseXX: <descripcion corta>"
git push origin apellido-nombre
```

- `git add ...` → selecciona **qué** archivo subir. Usá la ruta exacta (no `git add .`) para evitar subir cosas que no querés.
- `git commit -m "..."` → guarda el cambio localmente con un mensaje descriptivo.
- `git push origin apellido-nombre` → sube tu commit a GitHub, a tu rama.

> **Recordatorio**: el Pull Request a `main` ya existe desde la Clase 01. Cada `push` lo actualiza automáticamente — no hace falta crear uno nuevo.
