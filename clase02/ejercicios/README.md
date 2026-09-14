# Ejercicio 02 — Reglas de entrega

## ¿Qué hay que hacer?

Tres cosas (la guía paso a paso está en [`ejercicio.ipynb`](ejercicio.ipynb)):

1. **Tu primer cambio de infraestructura**: agregar el servicio `adminer` al `stack/docker-compose.yml` de **tu copia local**, mapeado a un puerto del host que elegís vos (entre **8100 y 8999**), y levantarlo. El snippet de compose está completo en el notebook — lo evaluado es integrarlo y que levante.
2. **Verificación del stack**: correr el notebook, que chequea 4 niveles (Python, Postgres, Airflow y tu Adminer) y genera un **código de verificación** derivado de tu instancia de Postgres (`pg_control_system()`). Sin el stack corriendo, el código no se genera.
3. **3 preguntas de comprensión** sobre el `docker-compose.yml`, respondidas con tus palabras (no se auto-corrigen: las lee el docente en tu PR).

> Archivos de referencia: [`../../stack/docker-compose.yml`](../../stack/docker-compose.yml) (ahí agregás `adminer` y de ahí salen las respuestas) y [`../../stack/.env`](../../stack/.env) (usuario/contraseña del warehouse).

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
Puerto elegido: 8123
Servicio agregado: adminer
Nivel alcanzado: 4 / 4
Pregunta (a) - Por que dos Postgres:
  ...tu respuesta...
Pregunta (b) - Volumen del warehouse:
  ...tu respuesta...
Pregunta (c) - Si el volumen se borra:
  ...tu respuesta...
Codigo: A1B2C3D4E5F6
Fecha: 2026-08-25
```

## ⚠️ Importante: NO commitees el `.ipynb` ni el `docker-compose.yml`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

El `stack/docker-compose.yml` con tu `adminer` **también queda solo en tu máquina**: cada estudiante eligió un puerto distinto y commitearlo pisaría el de los demás.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase02/ejercicios/estudiantes/sokil-juan.txt
git commit -m "ejercicio02: verificacion de stack + adminer"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb y el docker-compose.yml modificados)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `ejercicio02: ...` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase02/ejercicios/estudiantes/sokill-jaun.txt
```
