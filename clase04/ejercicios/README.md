# Ejercicio Clase 04 — Reglas de entrega

> El ejercicio de la clase 04 es **[`ejercicio.ipynb`](ejercicio.ipynb)** (un solo archivo, autocontenido): **Parte 1 — Setup** carga la base **Northwind** (Postgres o DuckDB) y **Parte 2** son **8 ejercicios de SQL básico** (SELECT/WHERE, COUNT, MIN/MAX, AVG, normalización+nulos con COALESCE, DISTINCT/LIKE, atributo derivado con CASE, un INNER JOIN simple) — los fundamentos que la Capa Silver usa todo el tiempo, a nivel de registro.
>
> Esta carpeta guarda tu entrega (`alumnos/`) y el DAG productivo (`dag_crypto_silver.py`, referencia / deploy).

## ¿Qué entrego?

Un **único archivo** dentro de [`alumnos/`](alumnos/) con el formato:

```
alumnos/<apellido>-<nombre>.txt
```

Ejemplo: `alumnos/sokil-juan.txt`.

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
  E1: OK (12x3) h=1A2B3C4D
  E2: OK (1x1) h=5E6F7A8B
  ...
  E7: SIN_QUERY (0x0) h=-
  E8: OK (20x3) h=9C0D1E2F
Ejercicios con resultado: 7 / 8
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

> **Funciona con Postgres o DuckDB**: la Parte 1 detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local) y la entrega reusa **ese mismo motor**. No tenés que configurar nada.
>
> **Las queries NO se autocorrigen** (las soluciones no se publican — el aprendizaje es pelearla). La entrega es **evidencia de trabajo**: la celda final **ejecuta tus `query_e1..query_e8`** y registra, por ejercicio, la forma del resultado (`filas×cols`) + un hash sha256 — **extraído automáticamente, NO se autoreporta nada**. Cuenta como hecho sólo el que **corre sin error y devuelve ≥1 fila** (stub vacío / 0 filas / error → no cuenta). El **código** sha256 se deriva de esos fingerprints + el motor + Northwind. Sigue **sin autocorregirse**: es evidencia de tu trabajo, no una comparación contra una solución. Si todavía no corriste los ejercicios o la Parte 1, igual podés generar con estado parcial.

## ⚠️ Importante: NO commitees el `.ipynb`

`ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los alumnos.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase04/ejercicios/alumnos/sokil-juan.txt
git commit -m "clase04: ejercicio sql"
git push origin apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: abrí el PR de esta clase

El PR de la clase anterior ya se mergeó (quedó cerrado). Para esta entrega **abrís uno nuevo** en GitHub: **"Compare & pull request"** sobre tu rama `apellido-nombre`, título `clase04: apellido-nombre`. El docente lo mergea.

> **Tu rama es siempre la misma** (`apellido-nombre`). El **PR es uno nuevo por clase**. Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase04/ejercicios/alumnos/sokill-jaun.txt
```
