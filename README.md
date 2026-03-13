# 🏗️ LCD — Infraestructura para Ciencia de Datos (UNSAM)

[![GitHub](https://img.shields.io/badge/GitHub-LCD--InfraCienciaDatos-181717?logo=github)](https://github.com/juansokil/LCD-InfraCienciaDatos)

Bienvenido al repositorio de **Infraestructura para Ciencia de Datos** de la Licenciatura en Ciencia de Datos — Universidad Nacional de San Martín. El curso transforma el caos de datos crudos en activos estratégicos listos para Analytics y Machine Learning.

---

## 📚 Contenido Clase por Clase



#### Clase 07: Arquitectura y Modelado de Datos
- **Fundamentos de Data Warehousing**: Conceptos de Kimball vs Inmon
- **Medallion Architecture**: Introducción a las capas Bronze, Silver y Gold
- **Modelado Dimensional**: Star Schema, dimensiones y tablas de hechos
- **Slowly Changing Dimensions (SCD)**: Tipos 0, 1, 2, 3, 4, 6
- **Ejercicios prácticos**: Diseño de esquemas dimensionales con drawio

#### Clase 08: Docker e Infraestructura de Datos
- **Contenerización con Docker**: Conceptos de imágenes y contenedores
- **Docker Compose**: Orquestación de servicios múltiples
- **PostgreSQL en contenedores**: Setup de base de datos productiva
- **Apache Airflow**: Introducción a la orquestación de pipelines
- **Ejercicios prácticos**: Levantar stack completo de infraestructura

### 🥉 **Capa Bronze: Ingesta y Fundamentos**

#### Clase 09: Ingesta a Bronze Layer
- **ELT vs ETL**: Paradigmas modernos de procesamiento
- **Ingesta de archivos**: CSV, JSON, Parquet
- **Control de duplicados**: Hashing con SHA256
- **Ingesta desde APIs REST**: Consumo de datos externos
- **Optimización**: Comparativa Parquet vs CSV
- **Ejercicios prácticos**: Pipeline de ingesta con detección de duplicados

### 🥈 **Capa Silver: Limpieza y Normalización**

#### Clase 10: Transformaciones a Silver Layer
- **Data Quality Engineering**: Contratos de datos y validaciones
- **Great Expectations**: Framework de calidad de datos
- **Limpieza de datos**: Manejo de nulos, duplicados, outliers
- **Normalización (3NF)**: Diseño de esquema normalizado
- **SCD Tipo 2 en práctica**: Implementación con SQL y Python
- **Ejercicios prácticos**: Pipeline Bronze → Silver con validaciones

### 🥇 **Capa Gold: Analytics y Machine Learning**

#### Clase 11: Modelado Dimensional y ABTs
- **Star Schema en producción**: Creación de fact tables y dimensions
- **Slowly Changing Dimensions avanzado**: SCD Tipo 2 completo
- **Analytical Base Table (ABT)**: Tablas wide para ML
- **RFM Analysis**: Segmentación de clientes (Recency, Frequency, Monetary)
- **Feature Engineering básico**: Preparación de features para modelos
- **Ejercicios prácticos**: Construcción de ABT para modelo de churn

#### Clase 12: MLOps y Arquitecturas para IA
- **Feature Stores**: Feast, componentes (Offline/Online Store, Registry)
- **Training-Serving Skew**: Detección y prevención
- **API Ingestion con SCD**: Ingesta de features externas con historia
- **Data Drift**: Tipos de drift y métodos de detección (KS Test, PSI)
- **Batch vs Online Serving**: Arquitecturas de inferencia
- **Model Registry**: Versionado de modelos con MLflow
- **Best Practices MLOps**: Testing, CI/CD, monitoring, alertas
- **Ejercicios prácticos**: Mini Feature Store y detección de drift

### 🏁 **Integración Final**

#### Clase 13: Workshop End-to-End
- **Pipeline completo**: Integración Bronze → Silver → Gold
- **Orquestación con Airflow**: DAGs de producción
- **Documentación**: Metadatos y data catalogs
- **Visualización**: Dashboards de KPIs
- **Portafolio profesional**: Preparación para el mundo laboral

---

## 🛠️ Stack Tecnológico

* **Lenguajes**: Python 3.10+ (Pandas, SQLAlchemy).
* **Bases de Datos**: PostgreSQL (Producción) y DuckDB (Analítica/Local).
* **Orquestación**: Apache Airflow 3.x.
* **Contenerización**: Docker & Docker Compose.
* **IA/ML Support**: Scikit-Learn (conceptos de features) y Feature Store Architecture.

---

## 🚀 Cómo empezar

### 1. Clonar el repositorio

Obtén una copia local del material ejecutando:

```bash
git clone https://github.com/juansokil/LCD-InfraCienciaDatos.git
cd LCD-InfraCienciaDatos
```

### 2. Crear tu rama de trabajo

Para realizar los laboratorios y guardar tus progresos, crea tu propia rama:

```bash
git checkout -b nombre-del-alumno
```

### 3. Levantar el entorno

Navega a la carpeta de infraestructura y levanta los servicios (Postgres + Airflow):

```bash
cd docker-stack-de-full
docker-compose up -d
```

Accede a Airflow en `localhost:8080` (User/Pass: `airflow`).

### 4. Laboratorios

Cada carpeta `claseXX` contiene notebooks autoejecutables con soporte híbrido para DuckDB si prefieres trabajar sin Docker.

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
*Diseñado con ❤️ para la comunidad de Ciencia de Datos de UNSAM.*
