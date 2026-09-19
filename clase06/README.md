# Clase 06: MLOps — del pipeline al modelo en producción

> **Clase de cierre del cuatrimestre**. Workshop magistral: el docente cierra el pipeline y le enchufa un modelo — **tracking, registry, serving y monitoreo**. **No hay entrega comprometida**: el objetivo es ver cómo se opera un modelo, no cómo se entrena uno bueno.

> El modelo que se usa **pierde contra una regla de una línea**, y está puesto a propósito. Lo que se enseña es la maquinaria que permite *darse cuenta* de eso — que es exactamente lo que un pipeline de MLOps tiene que hacer.

---

## 📚 Material

- [`clase06.ipynb`](clase06.ipynb) — workshop completo en un solo notebook (Parte 1: pipeline en producción · Parte 2: ML honesto · bonus track · mensaje final).
- [`ejercicios/dag_crypto_ml.py`](ejercicios/dag_crypto_ml.py) — el DAG de scoring que cierra el fan-out (se ve en clase; se activa copiándolo a `stack/dags/`).

---

## 🚀 Setup mínimo

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`) — incluye Postgres, Airflow, el dashboard **y el MLflow Tracking Server** (`localhost:5000`).
- El **pipeline productivo corriendo** en Airflow: `crypto_bronze` → `crypto_silver` → `crypto_gold`, encadenados por **Assets**: solo bronze tiene cron (`0,15,30,45`), y silver y gold se despiertan cuando la capa de arriba emite su asset — sin reloj propio. Gold deja, además de las tablas, las **vistas semánticas** que usa esta clase: `gold.v_ultimo_snapshot`, **`gold.v_series_diaria`** (1 fila = cripto × día, la materia prima del ML) y `gold.v_kpis_mercado`.
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
6. **🚀 Switch a modo producción**: se despausan las ramas por asset, se retira el andamiaje (los DAGs de ejemplo de cada clase). El tablero queda limpio: 4 DAGs que significan algo.
7. **🔎 El punta a punta en una foto**: una celda recorre API → Bronze → Silver → Gold → salidas y diagnostica dónde se cortó el dato.
8. **📊 Monitoring**: tres niveles de observabilidad (infra / datos / negocio), el dashboard como cierre del ciclo, roadmap MLOps.

### Parte 2 — MLOps: del notebook a producción

> El modelo es **el vehículo**, no el tema. Lo que se enseña acá es cómo un
> modelo deja de ser una celda de notebook y pasa a ser **una pieza del
> pipeline**: versionada, servida por un DAG, y corregida por un tablero.

**1. 🧪 Tracking — que el experimento sea reproducible.** MLflow del stack
(`localhost:5000`, backend Postgres, artifacts persistentes). La grilla cruza
**4 algoritmos × 3 ventanas** de historia: 12 runs con params, métricas y
artifacts registrados. Cada run lleva la **ventana como tag**, para poder
aislarlos en la UI. Sin esto, "el modelo que anduvo bien la semana pasada" es
una carpeta con un `.pkl` y la memoria de alguien.

**2. 🏆 Model Registry y aliases — qué modelo va a producción.** Un modelo
registrado **por ventana** (`crypto_volatilidad_1d/3d/7d`), cada uno con su
alias `@champion`. La promoción es una **decisión humana explícita**, no un
efecto secundario de correr una celda. Cambiar el champion en el Registry
**cambia lo que predice el pipeline sin tocar una línea de código** — ese es el
punto entero de tener un registry.

**3. ⚙️ Serving — el modelo como task de un DAG.**
[`dag_crypto_ml.py`](ejercicios/dag_crypto_ml.py): scoring batch disparado **por
el asset `gold_abt`**, no por reloj. Lee el champion del Registry, escribe
`gold.predicciones` de forma **idempotente** (DELETE del día + INSERT), y
**saltea con log claro** cuando todavía no hay champion, en vez de ponerse en
rojo. El mismo encadenado por Assets de las clases 03-05, ahora con un modelo
adentro.

**4. 🔀 Training-serving skew — el error que no avisa.** La ventana con la que
armar las features **no está hardcodeada**: el DAG la lee del param
`ventana_dias` del propio champion. Si el champion fue entrenado con otras
features, **lo detecta y saltea** en vez de escribir basura. Y el SQL de las
features es **la misma query** en el notebook y en el DAG — no dos copias que
divergen. Verlo ocurrir vale más que explicarlo.

**5. 📊 Monitoring — el tablero corrige al modelo.** La página `6_Gold_ML` abre
con el **veredicto**: accuracy contra lo que efectivamente pasó, medida contra
**dos varas**, y recién después muestra la maquinaria. Porque elegir la vara
fácil y cantar victoria es el error más común del oficio:

- **La fácil** — la clase mayoritaria. Ronda 50% porque el target está
  balanceado por construcción: ganarle no prueba nada.
- **La difícil** — la persistencia, *«mañana se repite lo de hoy»*. Sin
  features, sin entrenar, sin MLflow. **Superarla es lo que justifica haber
  entrenado algo.**

Hoy el modelo **le gana a la fácil por ~20 puntos y pierde contra la difícil por
~6**. No es un fracaso de la clase: **es la clase**. Un pipeline de MLOps que
solo sabe decir "todo bien" no sirve para nada.

---

#### El modelo, en breve (el contexto mínimo para entender lo de arriba)

No es el foco, pero sin esto los puntos 1 a 5 no se leen:

- **La pregunta correcta antes que el modelo.** Se arranca prediciendo *¿sube
  mañana?* y **no funciona ni puede funcionar**: la dirección del precio no está
  en los datos públicos de precio y volumen. Se pasa a **¿cuáles van a ser las
  criptos más movidas mañana?** — la volatilidad **se agrupa en el tiempo**, y
  eso sí se aprende. **Elegir bien la pregunta rinde más que cambiar de
  algoritmo.**
- **El dato fino que el pipeline ya junta.** La volatilidad se calcula con los
  **~66 snapshots por cripto por día** que `gold.fact_crypto_markets` acumula y
  que el cierre diario descarta. Es exactamente lo que se decidió guardar en la
  clase 05, cobrando sentido una clase después.
- **Target cross-sectional**: `vol_mañana > mediana de la volatilidad de
  mañana`. Balanceado siempre, por construcción.
- **Validación honesta**: split temporal por **fechas únicas** (walk-forward),
  jamás por posición de fila. Los 12 runs se evalúan sobre **las mismas
  fechas**: si cada uno usara las que le alcanzan, no se sabría si la diferencia
  viene de las features o del test set.

### Cierre

- **🎁 Bonus Track**: el mapa completo de MLOps, con **cinco piezas marcadas como ya hechas** en esta clase y tres que quedan para después (Feature Stores, Drift, Observability Gate).
- **🎓 Mensaje final**: qué construiste este cuatrimestre y qué hacer con eso (última celda del notebook).

---

## 🎁 Bonus Track: el mapa de MLOps, y dónde estás parado

La mitad de esta tabla **ya la hiciste hoy**. Sirve para ver qué te falta, no para asustarte:

| Concepto | Para qué sirve | ¿En esta clase? |
|----------|----------------|-----------------|
| **Experiment tracking** | Que un resultado se pueda reproducir y comparar | ✅ **Sí** — MLflow del stack, 12 runs con params, métricas y artifacts |
| **Model Registry** | Versionado y promoción con aliases | ✅ **Sí** — un modelo por ventana, cada uno con su `@champion` |
| **Model serving** | Que el modelo prediga solo, sin que nadie corra nada | ✅ **Sí** — `dag_crypto_ml`, disparado por asset e idempotente |
| **Training-Serving Skew** | Features idénticas al entrenar y al predecir | ✅ **Sí** — una sola query SQL compartida, y el DAG detecta y saltea si no coinciden |
| **Monitoring del modelo** | Saber si sigue sirviendo después del deploy | ✅ **Sí** — la página `6_Gold_ML`, contra dos varas |
| **Feature Stores** (Feast, Tecton) | Reuso de features entre equipos y proyectos | ❌ No — con un solo pipeline, una vista de Gold alcanza |
| **Data Drift detection** | Alertar cuando los datos de inferencia se alejan del training | ❌ No — necesita meses de historia para calibrar |
| **Observability Gate** | Bloquear un deploy automáticamente si las métricas no dan | ❌ No — acá la promoción del champion es manual, a propósito |

Lo que falta es **carrera completa**. Si te interesa profundizar:
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
