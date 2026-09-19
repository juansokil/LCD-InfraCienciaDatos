# Clase 06: Workshop End-to-End — Pipeline + ML sobre Gold

> **Clase de cierre del cuatrimestre**. Workshop magistral: el docente recorre el pipeline completo — de la orquestación en producción al ML honesto sobre Gold. **No hay entrega comprometida** — el objetivo es consolidar lo aprendido y ver el cuadro completo.

---

## 📚 Material

- [`clase06.ipynb`](clase06.ipynb) — workshop completo en un solo notebook (Parte 1: pipeline en producción · Parte 2: ML honesto · bonus track · mensaje final).
- [`ejercicios/dag_crypto_ml.py`](ejercicios/dag_crypto_ml.py) — el DAG de scoring que cierra el fan-out (se ve en clase; se activa copiándolo a `stack/dags/`).

---

## 🚀 Setup mínimo

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`) — incluye Postgres, Airflow, el dashboard **y el MLflow Tracking Server** (`localhost:5000`).
- El **pipeline productivo corriendo** en Airflow: `crypto_bronze` → `crypto_silver` → `crypto_gold`, encadenados por **Assets** (bronze con cron cada 15 minutos: `:00` → `:05` → `:10`). Gold deja, además de las tablas, las **vistas semánticas** que usa esta clase: `gold.v_ultimo_snapshot`, **`gold.v_series_diaria`** (1 fila = cripto × día, la materia prima del ML) y `gold.v_kpis_mercado`.
- Entorno Python local con `scikit-learn`, `mlflow`, `pandas` (`pip install -r requirements.txt`, raíz del repo).

> ⚠️ **clase06 requiere el stack Docker levantado y el pipeline productivo ya corrido.** Si en los ejercicios 03/04/05 hiciste la variante con **DuckDB** (sin Docker), eso **no alcanza acá**: clase06 no usa las tablas `*_demo` del ejercicio personal, sino el **pipeline productivo** completo. DuckDB sirvió para practicar cada capa; el cierre necesita el stack real.

> 📌 **Versiones**: el `requirements.txt` pinea **`mlflow==3.4.0`** — la misma versión que corre el server del stack. Cliente y server tienen que coincidir en la versión **mayor**: si difieren, `log_model` llama endpoints que el otro lado no tiene y falla. Si tu entorno tiene otra versión: `pip install mlflow==3.4.0`.

---

## 🗺️ Lo que vas a ver en clase

El docente recorre el notebook en vivo. Estructura real:

### Parte 1 — El pipeline, cerrado (de andamiaje a producción)

1. **📋 Recap del cuatrimestre**: tabla + diagrama del pipeline (Bronze → Silver → Gold → ML).
2. **🎯 Decisiones técnicas clave**: por qué SHA256 en Bronze, Pydantic + Cuarentena en Silver, Star Schema **y** ABT en Gold, MLflow hoy.
3. **⚠️ Errores típicos**: qué sale mal en cada capa — incluida la **orquestación** (mismo cron en las 3 capas, dos dueños de una tabla, consumidor de asset pausado).
4. **🔀 Flujo final del pipeline**: el mapa completo y por qué `global_market` se salta Silver (cuándo romper el patrón).
5. **🔗 La cadena completa**: las cuatro capas de crypto encadenadas por Assets — un solo cron en `crypto_bronze` y de ahí `crypto_silver` → `crypto_gold` → `crypto_ml`, cada una disparada por el dato de la anterior — y cómo verlo en la UI.
6. **🚀 Switch a modo producción**: se despausan las ramas por asset, se retira el andamiaje (gold por cron + DAGs de ejemplo). El tablero queda limpio: 4 DAGs que significan algo.
7. **🔎 El punta a punta en una foto**: una celda recorre API → Bronze → Silver → Gold → salidas y diagnostica dónde se cortó el dato.
8. **📊 Monitoring**: tres niveles de observabilidad (infra / datos / negocio), el dashboard como cierre del ciclo, roadmap MLOps.

### Parte 2 — ML honesto sobre Gold

1. **La pregunta correcta antes que el modelo.** Se arranca prediciendo *¿sube mañana?* y **no funciona ni puede funcionar**: la dirección del precio no está en los datos públicos de precio y volumen. Se pasa a **¿cuáles van a ser las criptos más movidas mañana?** — la volatilidad **se agrupa en el tiempo**, y eso sí se aprende (medido sobre los datos del curso: correlación día a día de +0,45). **Elegir bien la pregunta rinde más que cambiar de algoritmo.**

2. **Dataset con el dato fino que el pipeline ya junta.** La volatilidad se calcula con los **~66 snapshots por cripto por día** que `gold.fact_crypto_markets` acumula y que el cierre diario descarta. Features en SQL con `LAG`/ventanas (solo info ≤ t, disciplina *as-of* de clase01); target con `LEAD`, por cripto y ordenado por fecha real.

3. **Target cross-sectional**: `vol_mañana > mediana de la volatilidad de mañana`. La mitad le gana por definición, así que queda **balanceado siempre** y la clase mayoritaria se clava en 50%. Con un target absoluto esa referencia se movía con el humor del día y dejaba de ser comparable. **Pero ojo con la conclusión fácil**: que se clave en 50% la vuelve una vara *trivial de superar*, no una buena vara — ver el punto 5.

4. **🔭 ¿Mirar más atrás ayuda?** — la grilla cruza **4 algoritmos × 3 ventanas** (1, 3 y 7 días): 12 runs, la **misma** pregunta, distinta cantidad de historia. La respuesta **la da el dato del día, no el apunte**: la celda compara el salto entre ventanas contra lo que mueve una sola predicción, y si no lo supera dice que no hay diferencia. Los 12 se evalúan sobre las **mismas fechas**: si cada uno usara las que le alcanzan, no se sabría si la diferencia viene de las features o del test set.

5. **Validación honesta, y contra DOS varas.** Split temporal por **fechas únicas** (walk-forward), jamás por posición de fila. Y el modelo se mide contra dos referencias, porque elegir la fácil y cantar victoria es el error más común del oficio:

   - **La fácil** — la *clase mayoritaria de lo que ya pasó* (nunca la del día que se quiere predecir: eso sería elegir el lado ganador después del partido). Ronda 50% porque el target está balanceado por construcción, así que ganarle no prueba nada.
   - **La difícil** — la *persistencia*: «mañana se repite lo de hoy». Es la hipótesis de volatility clustering hecha regla, sin features, sin entrenar y sin MLflow. **Y acá está el filo**: si la volatilidad se agrupa —que es la razón por la que esta pregunta tiene respuesta— entonces repetir lo de ayer ya acierta mucho. Superarla es lo que justifica haber entrenado algo.

   Con los datos del curso el modelo **le gana a la fácil por ~20 puntos y pierde contra la difícil por ~6** (ventana 7d: 73,5% contra 51,9% y 79,7%). No es un fracaso de la clase: **es la clase**.

6. **MLflow del stack**: tracking server real (`localhost:5000`, backend Postgres, artifacts persistentes) → un modelo registrado **por ventana** (`crypto_volatilidad_1d/3d/7d`), cada uno con su alias `@champion` → recarga por alias. Cada run lleva la **ventana como tag**, para aislarlos en la UI.

7. **⚙️ El cierre del fan-out**: `dag_crypto_ml.py` — scoring batch disparado **por el asset `gold_abt`**, que lee el champion del Registry y escribe `gold.predicciones` (idempotente). **La ventana no está hardcodeada**: el DAG la lee del param `ventana_dias` del propio champion. Si el champion fue entrenado con otras features, **lo detecta y saltea con log claro** en vez de escribir basura — es *training-serving skew*, y verlo ocurrir vale más que explicarlo.

8. **📊 El tablero corrige al modelo, y da un veredicto.** La página `6_Gold_ML` abre con el resultado —accuracy por ventana contra **las dos varas**— y recién después muestra la maquinaria. También explica, con los datos del día, **qué significa ser volátil**: la dispersión intradía de una cripto y el corte en la mediana del mercado, dibujados.

   Abajo aparece lo que el promedio esconde: el modelo la clava en las que **siempre** son volátiles y en las que **nunca** lo son (DAI es una stablecoin), y sufre en las que alternan — que son las únicas donde hay algo que decidir. Y ahí se entiende por qué la persistencia es tan difícil de superar: **para la mayoría de las monedas, «mañana igual que hoy» es literalmente cierto**.

### Cierre

- **🎁 Bonus Track**: mapa de MLOps en producción (Feature Stores, Drift, Serving). No se enseña — es la próxima frontera.
- **🎓 Mensaje final**: qué construiste este cuatrimestre y qué hacer con eso (última celda del notebook).

---

## 🎁 Bonus Track: ¿Y producción?

| Concepto | Para qué sirve |
|----------|----------------|
| **Feature Stores** (Feast, Tecton) | Reuso consistente de features entre training y serving |
| **Model Registry** | Versionado de modelos y promoción con aliases (lo usamos hoy, de verdad) |
| **Data Drift detection** | Alertar cuando los datos de inferencia se alejan del training |
| **Training-Serving Skew** | Features idénticas en training y serving (hoy lo resolvimos con **una sola query SQL** compartida entre notebook y DAG) |
| **Observability Gate** | Validación automática previa a deploy |

Estos temas son **carrera completa**. Si te interesa profundizar:
- Material MLOps avanzado (Feature Stores, Drift, Model Serving): en preparación para próximas ediciones.
- Cursos: "Machine Learning Engineering for Production (MLOps)" (Coursera/DeepLearning.AI), "Made With ML" (Goku Mohandas).

---

## 🎓 Cierre del cuatrimestre

Si llegaste hasta acá hiciste **un pipeline completo de Data Engineering**: desde una API real hasta un modelo servido por un DAG data-aware, con tracking y registry. Eso es portfolio, eso es lo que separa a alguien que "sabe Python" de un Data Engineer junior.

**Próximos pasos sugeridos**: dejá el stack corriendo (la Parte 2 mejora sola a medida que se acumula historia) y aplicá el mismo patrón a un dataset de tu interés. Cambiá la fuente de Bronze, ajustá Silver al dominio, modelá Gold para la pregunta de negocio que querés responder. Ese ejercicio es el verdadero capstone.

El **mensaje final** completo está en la última celda del notebook.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| `gold.v_series_diaria` no existe | La crea la task `build_views` del DAG de Gold en cada corrida. Verificá que `crypto_gold` haya corrido OK en Airflow (se dispara solo cuando `crypto_silver` termina) |
| Todo aparece como **NO CONCLUYENTE** | Esperable con poca historia: el guard pide ≥ 14 fechas distintas y el warehouse suma 1 por día. Dejá el stack corriendo y volvé a correr la Parte 2 |
| `ImportError: sklearn` o `mlflow` | Activá tu entorno y `pip install -r requirements.txt` (raíz del repo) |
| MLflow no responde en `localhost:5000` | El server es **parte del stack** (no hay que correr nada a mano): `docker compose up -d mlflow` desde `stack/` |
| `log_model` falla con `404` en `/api/2.0/mlflow/logged-models` | Cliente y server difieren en la versión **mayor** de MLflow. Instalá la pineada: `pip install mlflow==3.4.0` |
| `load_model(...)` desde el notebook se cuelga y da `Read timed out` | En Windows, el port-forward de Docker Desktop no cierra bien las respuestas *chunked* del proxy de artifacts (**la descarga al host se cuelga; la subida anda salvo con artefactos grandes — ver la fila siguiente**). Por eso la celda 3.4 recarga el champion **adentro de la red** (`docker exec` → `http://mlflow:5000`) — igual que el DAG. Adentro de la red no existe el problema |
| `log_model` corta con `Read timed out` al **subir** | Mismo origen que la fila anterior: el proxy de artifacts sobre el port-forward de Docker Desktop. **No depende del tamaño** — falla hasta con un YAML de 2 kB. Por eso el zoo del paso 3.1 loguea **desde adentro de la red** (`docker exec` → `http://mlflow:5000`). Si escribís tu propio código de tracking, seguí ese patrón |
| El `docker exec` del notebook falla con `connection refused` en `127.0.0.1:2375` | Tenés una variable de entorno `DOCKER_HOST` apuntando a un daemon viejo. Borrala de las variables de usuario y reabrí la terminal / VS Code |
| `crypto_ml` no se dispara nunca | Consume el asset `gold_abt`, que emite la task `build_abt` de `crypto_gold`: hace falta que `crypto_gold` esté **despausado** y haya corriendo (el switch de la Parte 1), y que `crypto_ml` mismo no esté pausado — un consumidor pausado no se auto-dispara |
| El modelo no le gana al baseline de **persistencia** | Es un resultado posible, y hay que leerlo: la persistencia (*"mañana igual que hoy"*) **es** la hipótesis de volatility clustering hecha regla, así que es un rival serio. Con pocas fechas de test, además, la diferencia suele caer dentro del ruido — la celda imprime cuánto mueve una sola predicción, justamente para poder descartarla |
| Accuracy sospechosamente alta | Sospechá **leakage**: target disfrazado de feature, split que mezcla días, o grano intradía filtrándose en el cierre |
