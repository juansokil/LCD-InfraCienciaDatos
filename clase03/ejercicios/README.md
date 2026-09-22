# Ejercicio 03 — Reglas de entrega

## ¿Qué entrego?

Un **único archivo** dentro de [`estudiantes/`](estudiantes/) con el formato:

```
estudiantes/<apellido>-<nombre>.txt
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la sección **📦 Entrega** (última parte de [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas, separado por guión).

## ¿Qué pongo adentro del archivo?

**Nada manual.** El script del notebook lo escribe por vos a partir de lo que cargaste en Bronze (las tablas `bronze.crypto_markets_raw` y `bronze.crypto_markets_demo`). Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Motor: postgres
Tablas Bronze: bronze.crypto_markets_raw + bronze.crypto_markets_demo
Filas raw: 100
Filas demo: 100
Criptos distintas: 50
Doble ingesta: SI
Ultima carga: 2026-09-22 10:30:15.123456
Codigo: A1B2C3D4E5F6
Fecha: 2026-09-22
```

> **Funciona con Postgres o DuckDB**: el ejercicio detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local). La entrega reusa **ese mismo motor** y lo registra en el campo `Motor:`. No tenés que configurar nada.
>
> El **código** se deriva de tus cargas (cuántas filas y cuándo), el motor y la fecha: sale de **tu** base, no es una constante. Si algo todavía no está, el notebook te avisa y podés generar igual con estado parcial.

> 📖 **Patrón de referencia**: [`dag_crypto_bronze.py`](dag_crypto_bronze.py), en esta misma carpeta, es este pipeline como DAG productivo de Airflow (comentado línea por línea). Ojo: para ser más simple, el DAG elige y tipa columnas ya en Bronze y no guarda el crudo — lo correcto es lo que hacés en el ejercicio: guardar todo. Leelo antes de cerrar la clase.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase03/ejercicios/estudiantes/sokil-juan.txt
git commit -m "ejercicio03: ejercicio bronze"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `ejercicio03: ...` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase03/ejercicios/estudiantes/sokill-jaun.txt
```
