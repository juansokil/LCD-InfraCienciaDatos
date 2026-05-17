# Ejercicio Clase 03 — Reglas de entrega

## ¿Qué entrego?

Un **único archivo** dentro de [`alumnos/`](alumnos/) con el formato:

```
alumnos/<apellido>-<nombre>.txt
```

Ejemplo: `alumnos/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la sección **📦 Entrega** (última parte de [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas, separado por guión).

## ¿Qué pongo adentro del archivo?

**Nada manual.** El script del notebook lo escribe por vos a partir de la tabla `bronze.crypto_markets_demo` que cargaste en el ejercicio. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Motor: postgres
Tabla Bronze: bronze.crypto_markets_demo
Filas cargadas: 50
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

> **Funciona con Postgres o DuckDB**: el ejercicio detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local). La entrega reusa **ese mismo motor** y lo registra en el campo `Motor:`. No tenés que configurar nada.
>
> El **código** se deriva de las filas que efectivamente cargaste (+ el motor) — es evidencia de que corriste el ejercicio. Si todavía no cargaste la tabla, el notebook te avisa y podés generar igual con estado parcial.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los alumnos.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase03/ejercicios/alumnos/sokil-juan.txt
git commit -m "clase03: ejercicio bronze"
git push origin apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: abrí el PR de esta clase

El PR de la clase anterior ya se mergeó (quedó cerrado). Para esta entrega **abrís uno nuevo** en GitHub: **"Compare & pull request"** sobre tu rama `apellido-nombre`, título `clase03: apellido-nombre`. El docente lo mergea.

> **Tu rama es siempre la misma** (`apellido-nombre`). El **PR es uno nuevo por clase**. Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase03/ejercicios/alumnos/sokill-jaun.txt
```
