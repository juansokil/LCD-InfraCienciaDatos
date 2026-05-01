# 🏗️ LCD — Infraestructura para Ciencia de Datos (UNSAM)

[![GitHub](https://img.shields.io/badge/GitHub-LCD--InfraCienciaDatos-181717?logo=github)](https://github.com/juansokil/LCD-InfraCienciaDatos)

Bienvenido al repositorio de **Infraestructura para Ciencia de Datos** de la Licenciatura en Ciencia de Datos — Universidad Nacional de San Martín. El curso transforma el caos de datos crudos en activos estratégicos listos para Analytics y Machine Learning.

---

## 📚 Contenido Clase por Clase

### 🚀 **Fundamentos y Setup**

#### Clase 01: Ingeniería de Datos — Data Pipelines - Arquitectura Medallion
- Fundamentos de Data Engineering y jerarquía del dato
- Modelado dimensional: Star Schema, dimensions, fact tables
- Slowly Changing Dimensions (SCD): Tipos 0, 1, 2, 3, 4, 6
- Arquitectura Medallion: Bronze, Silver, Gold
- **Entrega**: primer push con Git al repo de la materia

#### Clase 02: Instalación del Stack y Tutorial de Airflow
- Stack Docker: Postgres + Airflow + Streamlit
- Apache Airflow 3: TaskFlow API, decoradores `@dag` y `@task`
- Branching, Dynamic Task Mapping, XComs
- Buenas prácticas: idempotencia, atomicidad, determinismo
- **Entrega**: stack instalado y verificado en local

### 🥉 **Capa Bronze: Ingesta**

#### Clase 03: Ingesta Profesional (Capa Bronze)
- Implementación de la Capa Bronze con Airflow
- Idempotencia mediante hashing SHA256 de archivos
- Hive Partitioning para organización del Data Lake
- Row-level hashing para detección de cambios
- **Entrega**: pipeline de ingesta con auditoría

### 🥈 **Capa Silver: Limpieza**

#### Clase 04: La Refinería (Capa Silver)
- Transformación Bronze → Silver
- Contratos de Datos y Data Quality (Pydantic)
- Limpieza avanzada: tipado estricto, deduplicación idempotente
- Patrón de Cuarentena para registros inválidos
- SCD Tipo 2 con SQL
- **Entrega**: pipeline Silver con validaciones

### 🥇 **Capa Gold: Analytics**

#### Clase 05: La Bóveda (Capa Gold)
- Star Schema en producción (Hechos y Dimensiones)
- Analytical Base Tables (ABT) para Machine Learning
- Capa Semántica y métricas gobernadas
- Integridad referencial completa
- **Entrega**: ABT y modelado dimensional

### 🏁 **Integración Final**

#### Clase 06: Workshop End-to-End
- Pipeline completo Bronze → Silver → Gold
- Orquestación profesional con Airflow
- Documentación y data catalogs
- Visualización con dashboards
- **Entrega**: proyecto integrador

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

A partir de la Clase 02, cada semana seguís este workflow sobre tu rama personal:

```bash
# 1. Traer el material nuevo desde main
git checkout main
git pull origin main

# 2. Volver a tu rama personal y mergear lo nuevo de main
git checkout apellido-nombre
git merge main

# 3. Trabajar la clase
#    → leer claseXX/README.md para entender los objetivos
#    → ejecutar claseXX/claseXX.ipynb (Kernel → Restart & Run All)
#    → completar los ejercicios

# 4. Commitear y pushear (el PR ya existe, se actualiza solo)
git add .
git commit -m "claseXX: ejercicios resueltos"
git push origin apellido-nombre
```
