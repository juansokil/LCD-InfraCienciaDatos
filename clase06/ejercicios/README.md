# Clase 06 — Esta clase no tiene entrega

> **No falta nada acá.** Las clases 01 a 05 terminan con un entregable en
> `estudiantes/`; la 06 no, y es una decisión, no un olvido.

## Por qué

La clase 06 es un **workshop de cierre**: se recorre el pipeline completo ya
construido y se le monta un modelo encima. Pedir un entregable propio sería pedir
lo mismo que el **TP Final** — armar un pipeline end-to-end y mostrarlo
funcionando — una semana antes de que lo entregues.

El trabajo de esta semana es el TP Final. Está en [`TpFinal/`](../../TpFinal/).

## Qué hay en esta carpeta

| Archivo | Qué es |
| :--- | :--- |
| [`dag_crypto_ml.py`](dag_crypto_ml.py) | El DAG de scoring del pipeline productivo: se dispara **por el asset** `gold_abt`, lee `crypto_volatilidad_{W}d@champion` del Registry de MLflow — y del propio modelo saca con qué ventana fue entrenado, así la ventana no queda hardcodeada — y escribe `gold.predicciones`. |

Es **material de referencia**, no un ejercicio. Se copia al stack como los DAGs de
las clases anteriores:

```bash
cp clase06/ejercicios/dag_crypto_ml.py stack/dags/
```

La página del dashboard que muestra los resultados
([`6_Gold_ML`](../../stack/dashboard/pages/6_Gold_ML.py)) ya viene con el stack:
la ves en `localhost:8501` sin hacer nada.

## Qué mirar mientras corre

El workshop cierra con el pipeline prediciendo **qué criptos van a ser las más
movidas mañana**, y el dashboard corrigiendo esas predicciones contra lo que
efectivamente pasó. Tres cosas que vale la pena entender, porque son las que
reaparecen en el TP:

- **Por qué se predice volatilidad y no dirección.** La dirección del precio no
  está en los datos públicos de precio y volumen: el modelo queda en el azar. La
  volatilidad sí — se agrupa en el tiempo, un día movido sigue a otro movido.
  **Elegir la pregunta correcta rinde más que cambiar de algoritmo.**
- **Contra qué se compara el resultado.** Nunca contra el 50% a secas, sino
  contra el *baseline*: cuánto acertaría la regla más tonta posible. Un accuracy
  alto no significa nada hasta saber qué tan fácil era el problema.
- **Qué pasa cuando el modelo y sus features se desincronizan.** El DAG lo
  detecta y saltea con un log claro en vez de escribir predicciones basura. Se
  llama *training-serving skew* y es de las formas más comunes de romper un
  sistema de ML en producción.
