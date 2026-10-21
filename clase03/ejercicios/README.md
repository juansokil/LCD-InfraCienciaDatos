# Ejercicio 03 — Reglas de entrega

## ¿Qué entrego?

Un **único archivo** dentro de [`estudiantes/`](estudiantes/) con el formato:

```
estudiantes/<apellido>-<nombre>.txt
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo genera automáticamente la sección **📦 Entrega** (última parte de [`ejercicio.ipynb`](ejercicio.ipynb)), normalizando tu nombre y apellido (sin tildes, minúsculas, separados por guión). **Los compuestos van pegados**: María José García López entrega `garcialopez-mariajose.txt`.

## ¿Qué pongo adentro del archivo?

**Casi nada manual**: lo único que escribís vos son las tres respuestas del Paso 5. El resto lo arma el script del notebook a partir de lo que guardaste — los archivos crudos de la **zona raw** (`stack/data/raw/crypto_markets/`) y la tabla de **Bronze** (`bronze.crypto_markets_demo`). Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Rama: estudiante/sokil-juan
Motor: postgres
Archivos crudos: 2
Filas demo: 100
Criptos distintas: 50
Cripto mas cara: bitcoin
Precio mas alto: 83069.0
Doble ingesta: SI
Ultima carga: 2026-09-22 10:30:15.123456
Pregunta (a) - La zona raw y la tabla:
  <tu respuesta>
Pregunta (b) - replace y append:
  <tu respuesta>
Pregunta (c) - Dos cargas identicas:
  <tu respuesta>
Codigo: A1B2C3D4E5F6
Fecha: 2026-09-22
```

> **`Cripto mas cara` sale del archivo crudo**, no de la tabla ni de una variable del notebook: el script abre el JSON más nuevo del lake y busca el `current_price` más alto. Es una manera de comprobar que el crudo que guardaste sirve para contestar preguntas sin volver a pedirle nada a la API.

> **Funciona con Postgres o DuckDB**: el ejercicio detecta solo qué motor usás (Postgres si levantaste el stack, DuckDB si trabajás local). La entrega reusa **ese mismo motor** y lo registra en el campo `Motor:`. No tenés que configurar nada.
>
> El **código** se deriva de tus cargas (cuántos archivos, cuántas filas, qué cripto era la más cara y cuándo cargaste), el motor y la fecha: sale de **tus** datos, no es una constante. Si algo todavía no está, el notebook te avisa y podés generar igual con estado parcial.
>
> Los archivos crudos de `stack/data/raw/` quedan en tu máquina: git los ignora, así que no viajan con la entrega.

> 📖 **Patrón de referencia**: [`dag_crypto_bronze.py`](dag_crypto_bronze.py), en esta misma carpeta, es este pipeline como DAG productivo de Airflow (comentado línea por línea). Escribe la zona raw igual que vos, pero su tabla **elige y tipa columnas** —deja afuera `image` y `roi`, que la API sí manda—, mientras la de acá se queda con **todas**. Es una decisión de la tabla, no de la zona raw: lo que la tabla no mapea sigue estando en el archivo. Leelo antes de cerrar la clase.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase03/ejercicios/estudiantes/sokil-juan.txt
git commit -m "clase03 (Bronze)"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `clase03 (Bronze)` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review, corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).


> Tu PR es el mismo de siempre (`estudiante/apellido-nombre` → `main`), abierto desde la Clase 01; solo se actualiza con tu push. **Una rama para siempre, un PR para siempre.** Detalle: [README raíz → "Cómo Consumir el Repo Semana a Semana"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal, contestá `n`, corregí la celda de datos y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase03/ejercicios/estudiantes/sokill-jaun.txt
```
