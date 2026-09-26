# Ejercicio 05 — Reglas de entrega

> El Ejercicio 05 vive en **[`ejercicio.ipynb`](ejercicio.ipynb)** — un solo archivo, autocontenido (lo que se **entrega** es el `.txt` que genera, nunca el notebook): **Parte 1 — Setup** carga la base **Northwind** (Postgres o DuckDB) y le aplica la limpieza que ya hizo Silver; **Parte 2 — 6 queries** (G1–G6) que arman **la misma tabla Gold**, ventas por categoría y mes: el grano, el JOIN con la dimensión (*star*), el corte con `HAVING`, el segmento con `CASE`, la participación y el ranking con *window functions*, y la variación con `LAG`. Son los patrones que la Capa Gold usa para **agregar y responder preguntas de negocio** (colapsan el grano, al revés que Silver en el ejercicio 04).
>
> Esta carpeta guarda tu entrega (`estudiantes/`) y el **material de referencia del pipeline productivo**: el DAG [`dag_crypto_gold.py`](dag_crypto_gold.py) (ELT: todo en SQL, con `CREATE TABLE ... AS SELECT`), que es esto mismo en grande.

## ¿Qué entrego?

**Un archivo**:

```
estudiantes/<apellido>-<nombre>.txt          <- lo genera la seccion "📦 Entrega" del notebook
```

Ejemplo: `estudiantes/sokil-juan.txt`.


> **No tipees el filename a mano** — lo genera automáticamente la sección **📦 Entrega** (final de [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas, separados por guión). **Los compuestos van pegados**: María José García López entrega `garcialopez-mariajose.txt`.

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
  G1: OK (8x3) h=1A2B3C4D
  G2: OK (64x4) h=5E6F7A8B
  G3: OK (27x3) h=C0DF431C
  G4: SIN_QUERY (0x0) h=-
  G5: FORMA_INESPERADA (1x1) h=-
  G6: OK (64x4) h=9C0D1E2F
Items OK: 4 / 6
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

> **Funciona con Postgres o DuckDB**: la Parte 1 detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local) y todo el ejercicio reusa **ese mismo motor**. No tenés que configurar nada.
>
> **Las queries NO se autocorrigen contra una solución** (las soluciones no se publican — el aprendizaje es pelearla). Pero la entrega **sí verifica**:
>
> - **G1–G6**: ejecuta tus `query_g1..query_g6` y exige la **forma exacta** del resultado (`filas×cols`). Una query que corre pero devuelve otra cosa (ej. `SELECT 1`) figura como `FORMA_INESPERADA` y **no cuenta**. Además registra un hash sha256 del resultado — **extraído automáticamente, NO se autoreporta nada**.
>
> El **código** sha256 final se deriva de esos fingerprints + el motor + Northwind. **Si alguna query no te salió, entregá igual**: queda como `SIN_QUERY` y las demás cuentan lo mismo.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con los paths explícitos, no `git add .`:

```bash
# CORRECTO
git add clase05/ejercicios/estudiantes/sokil-juan.txt
git commit -m "clase05 (Gold)"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `clase05 (Gold)` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos (arriba de la Entrega) y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase05/ejercicios/estudiantes/sokill-jaun.txt
```
