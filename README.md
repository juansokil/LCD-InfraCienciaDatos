# 🏗️ LCD — Infraestructura para Ciencia de Datos (UNSAM)

[![GitHub](https://img.shields.io/badge/GitHub-LCD--InfraCienciaDatos-181717?logo=github)](https://github.com/juansokil/LCD-InfraCienciaDatos)

Repositorio de **Infraestructura para Ciencia de Datos** — Licenciatura en Ciencia de Datos, Universidad Nacional de San Martín.

---


## 🛠️ Stack Tecnológico

* **Lenguajes**: Python 3.10+ (Pandas, SQLAlchemy).
* **Bases de Datos**: PostgreSQL (Producción) y DuckDB (Analítica/Local).
* **Orquestación**: Apache Airflow 3.x.
* **Contenerización**: Docker & Docker Compose.
* **IA/ML Support**: Scikit-Learn (conceptos de features) y Feature Store Architecture.

---

## 🚀 Empezá por la Clase 01

Cada clase tiene su propio README con guía paso a paso. Para tu primera entrega:

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

---

## 🎯 Proyecto Final

El curso culmina con un proyecto integrador donde los alumnos aplican todas las técnicas aprendidas:

- **Pipeline End-to-End**: Construcción completa desde ingesta (Bronze) hasta analytics (Gold)
- **Feature Engineering**: Preparación de datos para modelos de Machine Learning
- **MLOps**: Implementación de monitoreo, versionado y deployment
- **Documentación profesional**: Portfolio listo para mostrar a empleadores

Los estudiantes construyen su propia infraestructura de datos escalable aplicando las mejores prácticas de la industria.

---
