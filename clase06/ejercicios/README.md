# Clase 06 — Reglas de entrega

> La entrega de esta clase es **El veredicto**, que vive en
> [`ejercicio.ipynb`](ejercicio.ipynb): en el tracking quedan **siete candidatos** con sus
> métricas y vos decidís **cuál promoverías a producción**, o si ninguno está listo. No se
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
autoreportada— más tu decisión. Vas a ver algo así:

```
Apellido: Sokil
Nombre: Juan
Tracking: server (http://localhost:5000)
Experimento: clase06_veredicto
Candidatos (leidos de MLflow, no autoreportados):
  decision_tree_1d         n_train=12   n_test=3   acc_train=0.88 acc_test=0.83 ...
  random_forest_7d         n_train=240  n_test=60  acc_train=0.71 acc_test=0.68 ...
  ...
Elegido: random_forest_7d [OK]
Motivo: ...
Que miraria despues: ...
Codigo: A1B2C3D4E5F6
Fecha: 2026-11-20
```

> **Funciona con el stack o sin él**: el ejercicio usa el MLflow del stack (`localhost:5000`) y,
> si no responde, cae a una carpeta local. El `.txt` registra cuál se usó.
>
> **No se corrige cuál elegiste, se lee por qué.** Lo único que el script verifica es que el
> candidato exista entre los siete: si escribís uno que no está, queda marcado
> `CANDIDATO_INEXISTENTE`. Y si dejaste algún texto vacío, podés entregar igual, con estado
> parcial.

## ⚠️ Importante: NO commitees el `.ipynb`

El `ejercicio.ipynb` es **template compartido**. Si lo modificás y lo commiteás, se generan
conflictos con el resto.

```bash
# CORRECTO
git add clase06/ejercicios/estudiantes/sokil-juan.txt
git commit -m "clase06: el veredicto"
git push origin estudiante/apellido-nombre

# MAL ❌ (sube tambien el ipynb modificado)
git add .
```

El `git push` actualiza tu PR abierto desde la Clase 01: **no abrís uno nuevo**.

## Y el TP Final

Esta entrega es de lectura y decisión, de diez minutos. **El trabajo grande es el TP Final**, que
se entrega la semana siguiente y está en [`TpFinal/`](../../TpFinal/): ahí armás un pipeline
end-to-end propio. Son cosas distintas y no se reemplazan.

## Qué más hay en esta carpeta

| Archivo | Qué es |
| :--- | :--- |
| [`dag_crypto_ml.py`](dag_crypto_ml.py) | El DAG de scoring del pipeline productivo: se dispara **por el asset** `gold_abt`, lee `crypto_volatilidad_{W}d@champion` del Registry de MLflow — y del propio modelo saca con qué ventana fue entrenado, así la ventana no queda hardcodeada — y escribe `gold.predicciones`. |

Es **material de referencia**, no un ejercicio. Se copia al stack como los DAGs de las clases
anteriores:

```bash
cp clase06/ejercicios/dag_crypto_ml.py stack/dags/
```
