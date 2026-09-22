# Ejercicio 05 — Reglas de entrega

> El entregable del Ejercicio 05 es **[`ejercicio.ipynb`](ejercicio.ipynb)** (un solo archivo, autocontenido) y consta de **11 ítems**: **Parte 1 — Setup** carga la base **Northwind** (Postgres o DuckDB); **Parte 2 — 9 ejercicios SQL Gold** (G1–G8 + G11: GROUP BY+COUNT, GROUP BY+SUM, AVG/MIN/MAX por dimensión, HAVING, JOIN tipo *star*, CASE buckets, ROW_NUMBER/RANK, % del total y variación temporal con LAG); **Parte 3 — G9** (diseñás y materializás **TU propia tabla Gold**: grano + `CREATE TABLE` + `INSERT ... SELECT` + KPI) y **G10** (**tu página Streamlit** que la consume). Son los patrones que la Capa Gold usa para **agregar y responder preguntas de negocio** (colapsan el grano, al revés que Silver en el ejercicio 04).
>
> Esta carpeta guarda tu entrega (`estudiantes/` + `dashboard/pages/`) y el **material de referencia del pipeline productivo** que G9/G10 imitan en chico: el DAG [`dag_crypto_gold.py`](dag_crypto_gold.py) (ELT: todo en SQL, con `CREATE TABLE ... AS SELECT`) y las páginas Streamlit del dashboard del curso ([`stack/dashboard/pages/`](../../stack/dashboard/pages/) — las que ya ves corriendo en `localhost:8501`; no se duplican acá para que no queden desactualizadas).

## ¿Qué entrego?

**Dos archivos**:

```
estudiantes/<apellido>-<nombre>.txt          <- lo genera la seccion "📦 Entrega" del notebook
dashboard/pages/7_<apellido>-<nombre>.py          <- tu pagina Streamlit de G10 (la escribis vos)
```

Ejemplo: `estudiantes/sokil-juan.txt` + `dashboard/pages/7_sokil-juan.py`.

> **¿Por qué `7_` y por qué va tu nombre?** El dashboard del curso ya ocupa `1_` a `6_` (Bronze, Silver y las cuatro de Gold): tu página va con `7_` para que no choque y aparezca al final del sidebar. Y lleva **apellido y nombre** (igual que tu `.txt`) porque esta página **se commitea al repo del curso**: si fuera solo el apellido, dos compañeros que lo compartan escribirían el mismo archivo y se pisarían en un conflicto de merge.

> **No tipees el filename del `.txt` a mano** — lo genera automáticamente la sección **📦 Entrega** (final de [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas, separados por guión). **Los compuestos van pegados**: María José García López entrega `garcialopez-mariajose.txt` y su página `7_garcialopez-mariajose.py`. Tu página de G10 usa **el mismo slug** que el `.txt`.
>
> Tu tabla Gold de G9 **no** se sube (vive en tu base local): queda registrada en el `.txt` vía el **fingerprint del esquema** (nombres + tipos de columnas — único por diseño).

## ¿Qué pongo adentro del `.txt`?

**Nada manual.** El script del notebook lo escribe por vos. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Motor: duckdb
Northwind: 8/8 tablas
Customers: 91 filas
Orders: 196 filas
Ejercicios SQL (forma verificada, extraido de las queries, no autoreporte):
  G1: OK (8x2) h=1A2B3C4D
  G2: OK (10x2) h=5E6F7A8B
  ...
  G8: FORMA_INESPERADA (1x1) h=-
  G11: OK (8x3) h=9C0D1E2F
G9: OK tabla=gold_ventas_categoria_mes_sokil shape=64x4 grano=categoria,mes schema_h=E042D94D kpi=OK:8x3:h=0C0B6DDE
G10: OK archivo=7_sokil-juan.py sha256=CB75939A8F5B tabla=gold_ventas_categoria_mes_sokil
Items OK: 10 / 11
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

> **Funciona con Postgres o DuckDB**: la Parte 1 detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local) y todo el ejercicio reusa **ese mismo motor**. No tenés que configurar nada.
>
> **Las queries NO se autocorrigen contra una solución** (las soluciones no se publican — el aprendizaje es pelearla). Pero la entrega **sí verifica**:
>
> - **G1–G8 y G11**: ejecuta tus `query_g1..query_g8` y `query_g11` y exige la **forma exacta** del resultado (`filas×cols`). Una query que corre pero devuelve otra cosa (ej. `SELECT 1`) figura como `FORMA_INESPERADA` y **no cuenta**. Además registra un hash sha256 del resultado — **extraído automáticamente, NO se autoreporta nada**.
> - **G9**: tu tabla existe, tiene ≥ 3 columnas y ≥ 5 filas, y el **grano declarado es real** (`COUNT(*)` = combinaciones distintas de tus `grano_cols`); registra el fingerprint del esquema y ejecuta tu `query_g9` (que debe leer **tu** tabla).
> - **G10**: verificación **estática** de tu página (existe con el nombre correcto, compila, contiene `st.metric` + un gráfico + un filtro y referencia tu tabla). No hace falta levantar Streamlit.
>
> El **código** sha256 final se deriva de todos esos fingerprints + el motor + Northwind. Si todavía no terminaste, igual podés generar con estado parcial.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

Tu página `dashboard/pages/7_<apellido>-<nombre>.py`, en cambio, **sí se commitea**: es un archivo único por estudiante, no genera conflictos.

**Regla**: usá `git add` con los paths explícitos, no `git add .`:

```bash
# CORRECTO
git add clase05/ejercicios/estudiantes/sokil-juan.txt clase05/ejercicios/dashboard/pages/7_sokil-juan.py
git commit -m "ejercicio05: sql gold + tabla y pagina propia"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `ejercicio05: ...`, el `.txt` nuevo y tu página.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos (inicio de la Parte 3) y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase05/ejercicios/estudiantes/sokill-jaun.txt
```

(Y lo mismo con una página mal nombrada en `dashboard/pages/`.)
