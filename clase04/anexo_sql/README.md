# Anexo SQL — Fundamentos para Silver

> Material **complementario** y **opcional** de la clase 04. El núcleo de la clase sigue siendo [`clase04.ipynb`](../clase04.ipynb) (teoría) + [`ejercicios/ejercicio.ipynb`](../ejercicios/ejercicio.ipynb) (práctica crypto Bronze→Silver).

---

## ¿Por qué este anexo existe?

La capa **Silver** se apoya fuertemente en SQL: queries de quality checks, validación de integridad referencial, deduplicación, idempotencia con `MERGE`/`ON CONFLICT`, lógica de SCD Tipo 2, etc.

Si tus queries arrancan y terminan en `SELECT * FROM tabla WHERE id = 1`, vas a chocarte con problemas en cuanto entres al ejercicio crypto. Este anexo te lleva de **SELECT/WHERE → JOINs, agregaciones, subqueries y window functions** usando una base de datos clásica: **Northwind**.

Cada ejercicio incluye una nota **🔗 En Silver esto sería...** que conecta la técnica con un caso real de la clase. No es SQL desconectado: es la herramienta para construir Silver.

---

## ¿Qué hay acá adentro?

| Archivo | Propósito |
|---|---|
| [`00_setup.ipynb`](00_setup.ipynb) | Carga la base Northwind en Postgres (Docker) o DuckDB (local). Detecta automáticamente cuál motor está disponible. |
| [`01_ejercicios.ipynb`](01_ejercicios.ipynb) | 11 ejercicios graduados en 4 bloques. Tenés que resolverlos vos. |

**Material del docente (ya lo tenés a mano):**
- [`../creacion_base_datos.txt`](../creacion_base_datos.txt) — script SQL que crea Northwind (lo lee `00_setup.ipynb`).
- [`../Esquema Base de Datos Northwind.png`](../Esquema%20Base%20de%20Datos%20Northwind.png) — diagrama ER. **Tenelo abierto en otra pestaña mientras hacés los ejercicios.**
- [`../SQL - EJERCICIOS (1).pdf`](../SQL%20-%20EJERCICIOS%20(1).pdf) — práctica adicional de SQL puro (referencia opcional).

---

## ¿Cómo lo trabajo?

1. **Setup (una sola vez):** abrí `00_setup.ipynb` y corré todas las celdas. Te va a crear la base Northwind con sus 8 tablas.
2. **Ejercicios:** abrí `01_ejercicios.ipynb`. Resolvé en orden — cada bloque construye sobre el anterior.
3. **Verificá vos mismo:** los ejercicios incluyen *"resultado esperado"* (forma del output) para que sepas si tu query está bien. Las soluciones no se publican: el aprendizaje está en pelearla.

---

## Bloques de ejercicios

| # | Bloque | Técnicas | Conexión con Silver |
|---|---|---|---|
| **E1-E2** | SELECT + WHERE | filtros, `LIKE`, `IN` | Filtrar registros válidos en quality checks |
| **E3-E5** | GROUP BY + agregaciones | `COUNT`, `SUM`, `HAVING` | Detectar duplicados y completitud por dimensión |
| **E6-E8** | JOINs | `INNER`, `LEFT`, multi-tabla | Validar integridad referencial entre tablas |
| **E9-E11** | Subqueries + CASE + Window | scalar subquery, `CASE WHEN`, `ROW_NUMBER OVER` | Outliers, flagging de quarantine, dedup por timestamp (SCD2) |

---

## ¿Postgres o DuckDB?

**Postgres** (si ya levantaste el stack de clase 02):
- Coherente con el resto del curso.
- La base se crea en un schema dedicado `northwind` — no contamina `bronze`/`silver`/`gold`.

**DuckDB** (si querés algo livianito sin Docker):
- Crea un archivo local `northwind.duckdb` en esta carpeta.
- Misma sintaxis SQL para todo lo del anexo.
- Ideal si estás trabajando offline o sin el stack levantado.

El notebook `00_setup.ipynb` detecta cuál está disponible y elige solo. No tenés que decidir nada.
