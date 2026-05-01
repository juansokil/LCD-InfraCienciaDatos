# Ejercicio Clase 02 — Reglas de entrega

## ¿Qué entrego?

Un **único archivo** dentro de [`alumnos/`](alumnos/) con el formato:

```
alumnos/<apellido>-<nombre>.txt
```

Ejemplo: `alumnos/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la última celda de [`ejercicio.ipynb`](ejercicio.ipynb), normalizando tu nombre y apellido (sin tildes, minúsculas, separado por guión).

## ¿Qué pongo adentro del archivo?

**Nada manual.** El script del notebook lo escribe por vos. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Nivel alcanzado: 3 / 3
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los alumnos.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase02/ejercicios/alumnos/sokil-juan.txt
git commit -m "clase02: verificacion de stack"
git push origin apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase02/ejercicios/alumnos/sokill-jaun.txt
```
