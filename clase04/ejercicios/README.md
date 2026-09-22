# Ejercicio 04 — Reglas de entrega

> El entregable del Ejercicio 04 es **[`ejercicio.ipynb`](ejercicio.ipynb)** (un solo archivo, autocontenido): **Parte 1 — Setup** carga la base **Northwind** (Postgres o DuckDB) y **Parte 2** son **10 ejercicios de SQL básico** (SELECT/WHERE, COUNT, MIN/MAX, AVG, normalización+nulos con COALESCE, DISTINCT/LIKE, atributo derivado con CASE, INNER JOIN, anti-join de integridad referencial y deduplicación con ROW_NUMBER) — los fundamentos que la Capa Silver usa todo el tiempo, a nivel de registro.
>
> Esta carpeta guarda tu entrega (`estudiantes/`) y el DAG productivo (`dag_crypto_silver.py`, referencia / deploy). **[`dag_crypto_silver.py`](dag_crypto_silver.py) es el patrón productivo de referencia de todo lo que practicás acá — leelo.**

## ¿Qué entrego?

Un **único archivo** dentro de [`estudiantes/`](estudiantes/) con el formato:

```
estudiantes/<apellido>-<nombre>.txt
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la sección **📦 Entrega** (final de [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas, separado por guión).

## ¿Qué pongo adentro del archivo?

**Nada manual.** El script del notebook lo escribe por vos a partir de la base **Northwind** que cargaste en la Parte 1. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Motor: postgres
Northwind: 8/8 tablas
Customers: 91 filas
Orders: 196 filas
Ejercicios (extraido de las queries, no autoreporte):
  E1: OK (24x3) h=1A2B3C4D
  E2: OK (1x1) h=5E6F7A8B
  ...
  E7: SIN_QUERY (0x0) h=-
  E8: FORMA INCORRECTA (obtuviste 5x3, esperado 20x3) (5x3) h=-
  ...
Ejercicios con resultado: 8 / 10
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

> **Funciona con Postgres o DuckDB**: la Parte 1 detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local) y la entrega reusa **ese mismo motor**. No tenés que configurar nada.
>
> **Las soluciones no se publican** (el aprendizaje es pelearla), pero el verificador **sí exige la forma exacta**: la celda final **ejecuta tus `query_e1..query_e10`** y registra, por ejercicio, la forma del resultado (`filas×cols`) + un hash sha256 — **extraído automáticamente, NO se autoreporta nada**. Cuenta como **OK** sólo el que **corre sin error Y devuelve la forma exacta esperada** (filas × columnas + nombres de columna, tabla `SHAPES_ESPERADAS` del verificador). Un `SELECT 1` no pasa: da `FORMA INCORRECTA (obtuviste 1x1, esperado ...)` o `COLUMNAS INCORRECTAS`. El **código** sha256 se deriva de esos fingerprints + el motor + Northwind. El **contenido** de tus queries no se compara contra ninguna solución. Si todavía no corriste los ejercicios o la Parte 1, igual podés generar con estado parcial. **Y si alguna query no te salió, entregá igual**: esa queda como `SIN_QUERY` y las demás cuentan lo mismo.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase04/ejercicios/estudiantes/sokil-juan.txt
git commit -m "ejercicio04: ejercicio sql"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `ejercicio04: ...` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase04/ejercicios/estudiantes/sokill-jaun.txt
```
