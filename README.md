# 🏗️ LCD — Infraestructura para Ciencia de Datos (UNSAM)

[![GitHub](https://img.shields.io/badge/GitHub-LCD--InfraCienciaDatos-181717?logo=github)](https://github.com/juansokil/LCD-InfraCienciaDatos)

Bienvenido al repositorio de **Infraestructura para Ciencia de Datos** de la Licenciatura en Ciencia de Datos — Universidad Nacional de San Martín. El curso transforma el caos de datos crudos en activos estratégicos listos para Analytics y Machine Learning.

---


## 🛠️ Stack Tecnológico

* **Lenguajes**: Python 3.10+ (Pandas, SQLAlchemy).
* **Bases de Datos**: PostgreSQL (Producción) y DuckDB (Analítica/Local).
* **Orquestación**: Apache Airflow 3.x.
* **Contenerización**: Docker & Docker Compose.
* **IA/ML Support**: Scikit-Learn (conceptos de features) y Feature Store Architecture.

---

## 🚀 Cómo empezar

### 1. Registrarse como colaborador

1. Ir a la URL de onboarding: [https://asistencia-api-unsam-production.up.railway.app/unirse](https://asistencia-api-unsam-production.up.railway.app/unirse).
2. Completar con tu **Nombre**, **Email** y **Usuario de GitHub** (sin @).
3. Ingresar el **codigo de clase**.
4. Revisar tu email y **aceptar la invitacion** de GitHub.

### 2. Clonar el repositorio

```bash
git clone https://github.com/juansokil/LCD-InfraCienciaDatos.git
cd LCD-InfraCienciaDatos
```

### 3. Crear tu rama de trabajo

Nunca trabajamos directo sobre `main`. Crea tu propia rama:

```bash
git checkout -b registro-apellido-nombre
```

---

## 📅 Cómo Consumir el Repo Semana a Semana

Cada clase sigue el mismo workflow. Ejecutá esto al comienzo de cada semana:

```bash
# 1. Sincronizá la nueva clase
git checkout main
git pull origin main

# 2. Creá tu branch personal para esa clase
git checkout -b claseXX-tuapellido

# 3. Abrí el README de la clase para entender los objetivos
#    → claseXX/README.md

# 4. Ejecutá el notebook de arriba a abajo (Kernel → Restart & Run All)
#    → claseXX/claseXX.ipynb

# 5. Completá los ejercicios en la carpeta ejercicios/

# 6. Commiteá y subí tu trabajo
git add .
git commit -m "clase XX: ejercicios resueltos"
git push origin claseXX-tuapellido

# 7. Abrí un Pull Request en GitHub hacia main para revisión
```

### 💡 Tips

| Situación | Acción |
|-----------|--------|
| Quiero ver la teoría sin ejecutar código | Leer el `README.md` de la clase |
| El notebook da error | `Kernel → Restart & Run All` desde el principio |
| Quiero trabajar sin Docker | Usá DuckDB (soportado en todos los notebooks) |
| Tengo conflictos en git | Nunca trabajés en `main`, siempre en tu branch |
| ¿Qué sigue la próxima clase? | Al final de cada `README.md` hay una sección "➡️ Próxima Clase" |

---

## 🎯 Proyecto Final

El curso culmina con un proyecto integrador donde los alumnos aplican todas las técnicas aprendidas:

- **Pipeline End-to-End**: Construcción completa desde ingesta (Bronze) hasta analytics (Gold)
- **Feature Engineering**: Preparación de datos para modelos de Machine Learning
- **MLOps**: Implementación de monitoreo, versionado y deployment
- **Documentación profesional**: Portfolio listo para mostrar a empleadores

Los estudiantes construyen su propia infraestructura de datos escalable aplicando las mejores prácticas de la industria.

---
