# Ejercicio 05 — Reglas de entrega

> El Ejercicio 05 vive en **[`ejercicio.ipynb`](ejercicio.ipynb)** y **no tiene SQL**: es el paso
> que viene antes. Leés un caso —**una cadena de gimnasios**: qué registra su sistema y qué cuatro
> preguntas quiere contestar el tablero— y decidís **qué es el hecho, cuáles son las dimensiones y
> qué se mide**. Es el mismo ejercicio que en la clase se desarrolla con el caso del hotel.
>
> **No hace falta el stack ni DuckDB**: el notebook no se conecta a ninguna base.
>
> Esta carpeta guarda tu entrega (`estudiantes/`) y el **material de referencia del pipeline
> productivo**: el DAG [`dag_crypto_gold.py`](dag_crypto_gold.py) (ELT: todo en SQL, con
> `CREATE TABLE ... AS SELECT`), que es un star schema de verdad, armado en grande.

> **¿Y las queries de SQL Gold?** Se mudaron a **clase04** (E9 `GROUP BY` y E10 `HAVING`): agregar
> es el primer paso hacia Gold y rinde más pegado a los fundamentos de SQL.

## ¿Qué entrego?

**Un archivo**:

```
estudiantes/<apellido>-<nombre>.txt          <- lo genera la seccion "📦 Entrega" del notebook
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la sección **📦 Entrega** (final de
> [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas,
> separados por guión). **Los compuestos van pegados**: María José García López entrega
> `garcialopez-mariajose.txt`.

## ¿Qué pongo adentro del `.txt`?

**Nada manual.** El script del notebook lo escribe con lo que respondiste. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Rama: estudiante/sokil-juan
Caso: gimnasio
Hecho: <tu respuesta (a), en una sola línea>
Dimensiones: <tu respuesta (b)>
Metricas: <tu respuesta (c)>
Codigo: A1B2C3D4E5F6
Fecha: 2026-05-01
```

Cada respuesta va **en una sola línea** (el script junta los saltos), para que el archivo se lea
de un vistazo.

> **Esta entrega no se autocorrige.** No hay una única respuesta correcta y no se compara contra
> ninguna solución: **el docente lee tus tres respuestas y te comenta cada una**. Lo único que la
> celda verifica es que las tres estén completas.
>
> **Lo que se mira es la consistencia**: que lo que llamás métrica no esté también en las
> dimensiones, que cada pregunta del tablero se pueda contestar con tu modelo, y que puedas decir
> en una frase qué representa una fila de tu hecho.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan
conflictos masivos con el resto de los estudiantes.

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

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la
Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `clase05 (Gold)` y el
`.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo
> para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review,
> corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los
> estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).

> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01;
> solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle:
> [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal,
contestá `n`, corregí la celda de datos (arriba de la Entrega) y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase05/ejercicios/estudiantes/sokill-jaun.txt
```
