# Ejercicio 02 — Reglas de entrega

## ¿Qué hay que hacer?

Dos cosas (la guía paso a paso está en [`ejercicio.ipynb`](ejercicio.ipynb)):

1. **Verificación del stack**: correr el notebook, que chequea 3 niveles (Python, Postgres y Airflow) y genera un **código de verificación** derivado de tu instancia de Postgres (`pg_control_system()`). Sin el stack corriendo, el código no se genera.
2. **5 preguntas de comprensión** sobre el `docker-compose.yml`, respondidas con tus palabras. Corto está bien (no se auto-corrigen: las lee el docente en tu PR).

> Archivo de referencia: [`../../stack/docker-compose.yml`](../../stack/docker-compose.yml) (de ahí salen las respuestas).

## ¿Qué entrego?

Un **único archivo** dentro de [`estudiantes/`](estudiantes/) con el formato:

```
estudiantes/<apellido>-<nombre>.txt
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la celda del Paso 4 de [`ejercicio.ipynb`](ejercicio.ipynb), normalizando tu nombre y apellido (sin tildes, minúsculas, separado por guión).

## ¿Qué pongo adentro del archivo?

**Nada manual.** El script del notebook lo escribe por vos. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Rama: estudiante/sokil-juan
Nivel alcanzado: 3 / 3
Pregunta (a) - Los dos Postgres:
  ...tu respuesta...
Pregunta (b) - Datos despues del down:
  ...tu respuesta...
Pregunta (c) - DAGs en el contenedor:
  ...tu respuesta...
Pregunta (d) - Puerto 8080 ocupado:
  ...tu respuesta...
Pregunta (e) - Credenciales del warehouse:
  ...tu respuesta...
Codigo: A1B2C3D4E5F6
Fecha: 2026-08-25
```

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase02/ejercicios/estudiantes/sokil-juan.txt
git commit -m "clase02 (Stack)"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `clase02 (Stack)` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase02/ejercicios/estudiantes/sokill-jaun.txt
```
