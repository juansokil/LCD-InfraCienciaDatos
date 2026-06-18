# Clase 06: Workshop End-to-End — ML sobre Gold

> **Clase de cierre del cuatrimestre**. Workshop magistral: el docente recorre el pipeline completo desde Gold hasta ML productivo. **No hay entrega comprometida** — el objetivo es consolidar lo aprendido y ver el cuadro completo.

---

## 📚 Material

- [`clase06.ipynb`](clase06.ipynb) — workshop completo en un solo notebook (recap del cuatrimestre + walkthrough ML + bonus track + cierre).

---

## 🚀 Setup mínimo

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`).
- Tablas Gold ya pobladas (las generaste en **Clase 05** corriendo el `dag_crypto_gold.py`):
  - `gold.dim_crypto`, `gold.dim_tiempo`
  - `gold.fact_crypto_markets`, `gold.fact_global_market`
  - `gold.gold_abt_crypto` ← la ABT que se usa para entrenar
- Entorno Python con `scikit-learn`, `mlflow`, `matplotlib` instalados (`pip install -r requirements.txt`).

> ⚠️ **clase06 requiere el stack Docker levantado** (Postgres + Airflow) **y los DAGs productivos ya corridos** en Airflow: `crypto_bronze` → `crypto_silver` → `crypto_gold`.
>
> Si en clase03/04/05 hiciste los **ejercicios con DuckDB** (sin Docker), eso **no alcanza acá**: clase06 no usa las tablas `*_demo` del ejercicio personal, sino el **pipeline productivo** completo (`gold.gold_abt_crypto`, sin sufijo). Es el cierre que **integra todo en productivo** — orquestador Airflow E2E + monitoring + ML sobre datos reales. DuckDB sirvió para practicar cada capa; el cierre necesita el stack real.

---

## 🗺️ Lo que vas a ver en clase

El docente recorre el notebook en vivo. Estructura:

### Bloque 1 — Recap del Cuatrimestre (3 secciones)

1. **📋 Tabla + diagrama del pipeline completo** (Bronze → Silver → Gold → ML).
2. **🎯 Decisiones técnicas clave**: por qué SHA256 en Bronze, por qué Pydantic + Cuarentena en Silver, por qué Star Schema **y** ABT en Gold, por qué MLflow hoy.
3. **⚠️ Errores típicos / lecciones aprendidas**: qué sale mal en cada capa si te salteás los principios.

### Bloque 2 — Workshop ML (3 pasos)

1. **Setup + cargar datos de Gold**.
2. **Clasificación con Random Forest + model zoo**: predecir la **dirección del precio 24h** (¿subió?) desde *fundamentals* → baseline vs modelo → feature importance → **lección sobre target leakage** → **validación temporal honesta con `TimeSeriesSplit`** (el otro leakage, el temporal).
3. **Tracking con MLflow** + **Model Registry**: entrenar un *model zoo* de 4 modelos (regresión logística, árbol, random forest, gradient boosting) → registrar cada uno como run → comparar en la UI y confirmar que **ninguno le gana al baseline** → promover el campeón al **Registry** con alias `@champion` (MLflow 2.x: aliases en lugar de stages legacy) y recargarlo para inferencia.

### Bloque 3 — Monitoring del Pipeline E2E

4. **📊 Monitoring del pipeline E2E**: tres niveles de observabilidad (infra / datos / negocio), el dashboard Streamlit como cierre del ciclo, health check del pipeline completo via SQL.

### Bloque 4 — Cierre

5. **🎁 Bonus Track**: mapa de MLOps en producción (Feature Stores, Drift, Model Registry, etc.). No se enseña — es la próxima frontera.
6. **🎓 Mensaje final**: qué construiste este cuatrimestre, próximos pasos sugeridos.

---

## 🎁 Bonus Track: ¿Y producción?

| Concepto | Para qué sirve |
|----------|----------------|
| **Feature Stores** (Feast, Tecton) | Reuso consistente de features entre training y serving |
| **Model Registry** | Versionado de modelos y promoción entre staging/production |
| **Data Drift detection** | Alertar cuando los datos de inferencia se alejan del training |
| **Training-Serving Skew** | Asegurar que las features en producción sean idénticas a las usadas en training |
| **Observability Gate** | Validación automática previa a deploy |

Estos temas son **carrera completa**. Si te interesa profundizar:
- Material avanzado preservado en `_legacy/clase12-mlops/` (notebooks de cuatrimestres anteriores).
- Cursos: "Machine Learning Engineering for Production (MLOps)" (Coursera/DeepLearning.AI), "Made With ML" (Goku Mohandas).

---

## 🎓 Cierre del cuatrimestre

Si llegaste hasta acá hiciste **un pipeline completo de Data Engineering**: desde una API real hasta ML productivo trackeado. Eso es portfolio, eso es lo que separa a alguien que "sabe Python" de un Data Engineer junior.

**Próximos pasos sugeridos**: aplicar el mismo patrón a un dataset de tu interés (no crypto). Cambiá la fuente de Bronze, ajustá Silver al dominio, modelá Gold para la pregunta de negocio que querés responder. Ese ejercicio es el verdadero capstone.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| `gold.gold_abt_crypto` está vacía | Verificá que `dag_crypto_gold` (clase05) haya corrido en Airflow |
| `ImportError: sklearn` o `mlflow` | Activá tu entorno y `pip install -r requirements.txt` (raíz del repo) |
| MLflow UI no levanta en `localhost:5000` | Corré `mlflow ui --host 0.0.0.0 --port 5000` desde la terminal, en el directorio donde MLflow guardó los runs |
| El Random Forest apenas le gana (o no) al baseline | **Es esperable y es la lección**: predecir la dirección del precio desde fundamentals es casi azar. Un modelo honesto acá ronda el baseline. Si vieras accuracy alta, sospechá *target leakage* (una feature que es el target disfrazado). |
| `train_test_split` falla con `stratify` | Pasa sólo si una clase tiene <2 muestras (mercado 100% verde o rojo ese día — rarísimo). Reintentá con datos de otro snapshot o quitá `stratify` temporalmente. |
