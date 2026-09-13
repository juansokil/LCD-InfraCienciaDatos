# Ejercicio 01 — Reglas de entrega

## ¿Qué entrego?

Un **único archivo** dentro de [`estudiantes/`](estudiantes/) con el formato:

```
estudiantes/<apellido>-<nombre>.txt
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la última celda de [`ejercicio.ipynb`](ejercicio.ipynb), normalizando tu nombre y apellido (sin tildes, minúsculas, separados por guión).

**Nombres y apellidos compuestos van pegados.** El guión separa apellido de nombre, así que hay **uno solo**: María José García López entrega `garcialopez-mariajose.txt` desde la rama `estudiante/garcialopez-mariajose`. El mismo criterio vale para el archivo y para la rama — el notebook usa la misma función para los dos.

## ¿Qué pongo adentro del archivo?

**Nada manual.** El script del notebook lo escribe por vos. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Usuario GitHub: juansokil
Rama: estudiante/sokil-juan
Codigo: A1B2C3D4E5F6
Fecha: 2026-08-01
```

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase01/ejercicios/estudiantes/sokil-juan.txt
git commit -m "ejercicio01: registro"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: abrí tu PR (una sola vez)

Es tu **primer y único** PR del curso. En GitHub: **"Compare & pull request"** sobre tu rama `estudiante/apellido-nombre` (título: el que sugiere GitHub, el nombre de tu rama). **Dejalo abierto** todo el cuatrimestre.

> **El docente NO va a mergear tu PR** — y está bien que así sea. Tu rama es tu espacio de trabajo del cuatrimestre y el PR es la ventana por donde el docente mira tus entregas. No esperes el merge ni lo pidas: un PR abierto con pushes semanales es la señal de que venís bien.

> **Las dos señales que puede dejarte el docente**: un 💬 **comentario** (una observación o pregunta — respondé en el mismo hilo) o un 🔴 **"Changes requested"** (rechazó una entrega: hay algo para corregir). En ninguno de los dos casos se cierra tu PR: corregís, `commit` + `push` a la misma rama, y ese push levanta la marca. Tabla completa de estados en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).

> **Tu rama y tu PR son siempre los mismos** (`estudiante/apellido-nombre`). En los próximos ejercicios **no abrís PRs nuevos**: solo `commit` + `push` y el PR se actualiza solo. Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase01/ejercicios/estudiantes/sokill-jaun.txt
```
