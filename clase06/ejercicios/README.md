# Ejercicio 06 — Reglas de entrega

> La entrega de esta clase es **El veredicto**, que vive en
> [`ejercicio.ipynb`](ejercicio.ipynb): en el tracking quedan **siete candidatos** con sus
> métricas y respondés **cinco preguntas** sobre ellos; una es cuál pondrías en producción. No se
> entrena nada: lo que se practica es **consultar MLflow y leer lo que devuelve**, que es lo que
> hace alguien de MLOps cuando le toca promover.

## ¿Qué entrego?

**Un archivo**:

```
estudiantes/<apellido>-<nombre>.txt          <- lo genera la seccion "Entrega" de ejercicio.ipynb
```

Ejemplo: `estudiantes/sokil-juan.txt`.

> **No tipees el filename a mano** — lo arma el script con tu nombre y apellido (sin tildes,
> minúsculas, separados por guión). **Los compuestos van pegados**: María José García López
> entrega `garcialopez-mariajose.txt`.

## ¿Qué pongo adentro?

**Nada manual.** El script escribe la tabla de los siete candidatos **leída de MLflow** —no
autoreportada— más tus cinco respuestas. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Rama: estudiante/sokil-juan
Tracking: server (http://localhost:5000)
Experimento: clase06_veredicto
Candidatos (leidos de MLflow, no autoreportados):
  decision_tree_1d         n_train=12   n_test=3   acc_train=0.88 acc_test=0.83
  gradient_boosting_7d     n_train=240  n_test=60  acc_train=0.64 acc_test=0.61
  ...
Elegido: <tu candidato de la (d)> [OK]
Pregunta (a) - El acc_test mas alto:
  ...
Pregunta (b) - El acc_train mas alto:
  ...
Pregunta (c) - El acc_test mas bajo:
  ...
Pregunta (d) - Cual pondrias en produccion:
  ...
Pregunta (e) - Como te darias cuenta de que empeora:
  ...
Codigo: A1B2C3D4E5F6
Fecha: 2026-11-20
```

> **Funciona con el stack o sin él**: usa el MLflow del stack (`localhost:5000`); si no
> responde, cae a una carpeta local, y si MLflow no está instalado, la tabla sale igual, directo
> de los candidatos. Los números son los mismos en los tres casos, y el `.txt` registra cuál se
> usó.
>
> **Las respuestas no se autocorrigen**: las lee el docente en tu PR. Las cinco son
> obligatorias: si falta alguna, la Entrega no genera el archivo. Lo único que el script verifica
> es que el candidato de la (d) exista entre los siete: si escribís uno que no está, queda
> marcado `CANDIDATO_INEXISTENTE`.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan
conflictos masivos con el resto de los estudiantes.

**Regla**: usá `git add` con el path explícito a tu `.txt`, no `git add .`:

```bash
# CORRECTO
git add clase06/ejercicios/estudiantes/sokil-juan.txt
git commit -m "clase06 (MachineLearning)"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

## Después del push: tu PR se actualiza solo

**No abrís un PR nuevo.** El `git push` de arriba actualiza tu PR abierto (el que creaste en la
Clase 01). El docente revisa tu entrega ahí — la identifica por el commit `clase06
(MachineLearning)` y el `.txt` nuevo.

> **¿Viste una marca roja "Changes requested" en tu PR?** El docente rechazó una entrega: hay algo
> para corregir. **Tu PR sigue abierto** — no abras uno nuevo ni crees otra rama. Leé el review,
> corregí, `commit` + `push` a la misma rama y ese push levanta la marca. Detalle de todos los
> estados del PR en el [README raíz → "Cómo leer el estado de tu PR"](../../README.md).

## Si te equivocaste con el nombre/apellido

El script te muestra el filename antes de escribir y te pide confirmación. Si tipeaste mal,
contestá `n`, corregí la celda de datos (arriba de la Entrega) y volvé a correr.

Si ya creaste un archivo basura (ej: `sokill-jaun.txt`), borralo y volvé a correr el script:

```bash
rm clase06/ejercicios/estudiantes/sokill-jaun.txt
```

## Y el TP Final

Esta entrega es de lectura y decisión, de diez minutos. **El trabajo grande es el TP Final**, que
se entrega la semana siguiente y está en [`TpFinal/`](../../TpFinal/): ahí armás un pipeline
end-to-end propio. Son cosas distintas y no se reemplazan.

## Qué más hay en esta carpeta

| Archivo | Qué es |
| :--- | :--- |
| [`dag_crypto_ml.py`](dag_crypto_ml.py) | El DAG de scoring del pipeline productivo: se dispara **por el asset** de Silver (`silver_crypto_markets`), en paralelo a Gold. Una vez por día, cuando cierra el día, rearma la ABT (`gold.gold_abt_crypto`, una fila por cripto y por día) y emite `gold_abt`; después lee `crypto_volatilidad_7d@champion` del Registry de MLflow —y del propio modelo saca con qué ventana fue entrenado, así la ventana no queda hardcodeada—, predice con el último día de la ABT y escribe `gold.predicciones`. |

Es **material de referencia**, no un ejercicio. Se copia al stack como los DAGs de las clases
anteriores:

```bash
cp clase06/ejercicios/dag_crypto_ml.py stack/dags/04-ml/
```
