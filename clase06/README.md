# Clase 06: MLOps — Gold servido a un modelo

> 📚 **Cómo está estructurada esta clase** (patrón compartido por clase03/04/05/06):
>
> 1. **Notebook teórico** ([`clase06.ipynb`](clase06.ipynb)) — conceptos + un DAG demo sobre datos sintéticos (`silver.ventas_demo`, la misma fuente de la clase 05)
> 2. **Ejercicio práctico (con entrega)** ([`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb)) — *El veredicto*: siete candidatos en MLflow y una decisión
> 3. **DAG productivo** ([`ejercicios/dag_crypto_ml.py`](ejercicios/dag_crypto_ml.py)) — para copy-paste a Airflow

> **La misma capa Gold de la clase 05, servida al otro consumidor.** Ahí el dato se modeló para que lo mire una persona: un hecho, sus dimensiones, un tablero. Acá se modela para que lo coma un modelo: una **ABT**, una fila por caso — y después hay que **servirla** (un DAG que scorea solo), **versionar** lo que se entrenó (MLflow) y **corregirlo** contra lo que efectivamente pasó. El objetivo es ver cómo se **opera** un modelo, no cómo se entrena uno.

> El modelo se mide contra dos referencias sin entrenamiento, la clase mayoritaria y la persistencia, y la página 6 del tablero muestra los tres números lado a lado. Lo que se enseña es la maquinaria que permite *medirlo* — que es exactamente lo que un pipeline de MLOps tiene que hacer.

---

## 🎯 Objetivos

- Distinguir las dos formas de Gold —el **star schema** para BI y la **ABT** para ML— y construir una ABT verificando su grano.
- Dejar el pipeline en **modo producción**: las cuatro capas encadenadas por el dato, y ver quién disparó cada corrida.
- Medir un modelo **sin engañarse**: features sin futuro, validación por fechas y dos referencias (la clase mayoritaria y la persistencia).
- Registrar experimentos en **MLflow** y reemplazar el modelo en producción **solo si el nuevo le gana** (champion contra challenger).
- Servir el modelo con un **DAG disparado por el dato** y corregirlo con un tablero contra lo que efectivamente pasó.

---

## 📚 Material

- [`clase06.ipynb`](clase06.ipynb) — el workshop (Parte 1: pipeline en producción · Parte 2: ML honesto · bonus track · mensaje final).
- El notebook genera además un **DAG pedagógico** (vía `%%writefile`): `gold_02_abt.py`, que arma una **ABT** sobre los datos sintéticos de la clase 05 —una fila por cliente, con las features en SQL— y verifica su grano.
- [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) — **El veredicto**, la entrega de la clase: siete candidatos en MLflow y una decisión. Tu `.txt` cae en [`ejercicios/estudiantes/`](ejercicios/estudiantes/) (reglas en [`ejercicios/README.md`](ejercicios/README.md)).
- [`ejercicios/dag_crypto_ml.py`](ejercicios/dag_crypto_ml.py) — el DAG de scoring que cierra el fan-out (se ve en clase; se activa copiándolo a `stack/dags/`).

---

## 🚀 Setup mínimo

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`) — incluye Postgres, Airflow, el dashboard **y el MLflow Tracking Server** (`localhost:5000`).
- El **pipeline productivo corriendo** en Airflow: `crypto_bronze` → `crypto_silver` → `crypto_gold`, encadenados por **Assets**: solo bronze tiene cron (`0,15,30,45`), y silver y gold se despiertan cuando la capa de arriba emite su asset — sin reloj propio. Gold deja, además de las tablas, las **vistas semánticas** que consume el dashboard (`gold.v_ultimo_snapshot`, `gold.v_series_diaria`, `gold.v_kpis_mercado`). El modelo de esta clase, en cambio, se entrena desde **Silver** (`silver.crypto_markets`): necesita el grano de los snapshots para calcular la volatilidad de cada día, que la serie diaria ya colapsó.
- Entorno Python local con `scikit-learn`, `mlflow`, `pandas` (`pip install -r requirements.txt`, raíz del repo).

**Sincronizá tu rama con el material nuevo.** Cada clase trae material nuevo en `main`. Antes de empezar a trabajar, traete los cambios:

```bash
# 1. Bajar lo nuevo de main
git checkout main
git pull origin main

# 2. Volver a tu rama personal y mergear
git checkout estudiante/apellido-nombre   # reemplazá por tu rama
git merge main --no-edit
```

> Vas a repetir esto al empezar **cada** clase. El detalle de cada comando está en el [README raíz](../README.md), sección "Cómo Consumir el Repo Semana a Semana".

> ⚠️ **clase06 requiere el stack Docker levantado y el pipeline productivo ya corrido.** Si en los ejercicios 03/04/05 hiciste la variante con **DuckDB** (sin Docker), eso **no alcanza acá**: clase06 no usa las tablas `*_demo` del ejercicio personal, sino el **pipeline productivo** completo. DuckDB sirvió para practicar cada capa; el cierre necesita el stack real.

> 📌 **Versiones**: el `requirements.txt` pinea **`mlflow==3.4.0`** — la misma versión que corre el server del stack. Cliente y server tienen que coincidir en la versión **mayor**: si difieren, `log_model` llama endpoints que el otro lado no tiene y falla. Si tu entorno tiene otra versión: `pip install mlflow==3.4.0`.

---

## 📋 Cómo trabajar la clase

### Paso 1 — Recorrer el notebook

Abrí [`clase06.ipynb`](clase06.ipynb) y corrélo de arriba abajo, con el stack levantado. La **Parte 1** deja el pipeline en producción y la **Parte 2** le mete un modelo adentro; el detalle de cada sección está en *Lo que vas a ver en clase*, acá abajo. El copy-paste de `dag_crypto_ml.py` al stack lo hace por vos la celda del switch a producción.

### Paso 2 — El ejercicio y la entrega

Abrí [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb): **El veredicto**. Se entrega un `.txt`; cómo generarlo y subirlo está en *La entrega de esta clase*, más abajo.

---

## 🗺️ Lo que vas a ver en clase

El docente recorre el notebook en vivo. Estructura real:

### Parte 1 — El pipeline, en producción

1. **🔗 La cadena completa**: las cuatro capas de crypto encadenadas por Assets — un solo cron en `crypto_bronze`, de ahí `crypto_silver`, y de Silver, en paralelo, `crypto_gold` (BI) y `crypto_ml` (ML), cada uno disparado por el dato que lee.
2. **🚀 Switch a modo producción**: se copia `dag_crypto_ml.py` al stack (y se vuelve a copiar `dag_crypto_gold.py`, que ahora baja solo sus vistas) y se despausan los cuatro `crypto_*`, mirando el resultado de cada uno: un DAG pausado no se dispara por asset, y no da ningún error.
3. **👀 Quién disparó cada corrida**: una consulta a la metadata de Airflow muestra la última cadena en el orden en que arrancó, y qué disparó cada corrida — a bronze, el reloj; a silver, el asset de bronze; a gold y a ml, los dos, el de silver.

### Parte 2 — MLOps: del notebook a producción

> El modelo es **el vehículo**, no el tema. Lo que se enseña acá es cómo un
> modelo deja de ser una celda de notebook y pasa a ser **una pieza del
> pipeline**: versionada, servida por un DAG, y corregida por un tablero.

**Primero, la forma: 🧱 la ABT.** Un mini-lab pone el star de la clase 05 al lado
de una ABT sobre las mismas ventas, verifica el grano y lo rompe con un refactor;
después `gold_02_abt.py` arma esa ABT como DAG, con una task que verifica el grano.

**1. 🧪 El dataset y la medición, lo mínimo honesto.** Las features salen de una
query SQL sobre `silver.crypto_markets` (solo información ≤ t) y el target de
un `LEAD`. La validación es temporal, **por fechas únicas**, y se mide contra dos
referencias. No es una clase de modelado: es el piso sin el cual las métricas que
vienen después mienten.

**2. 🧪 Tracking — que el experimento sea reproducible.** MLflow del stack
(`localhost:5000`, backend Postgres, artifacts persistentes). La grilla cruza
**2 algoritmos × 3 ventanas** de historia: 6 runs con params, métricas y
artifacts registrados. Cada run lleva la **ventana como tag**, para poder
aislarlos en la UI. Sin esto, "el modelo que anduvo bien la semana pasada" es
una carpeta con un `.pkl` y la memoria de alguien.

**3. 🏆 Model Registry y aliases — qué modelo va a producción.** Un solo
modelo registrado, `crypto_volatilidad_7d`: el que usa el DAG (la grilla compara
las tres ventanas como runs, en Experiments). El modelo nuevo
**no entra directo**: entra como `@challenger` y reemplaza al `@champion` **solo
si le gana**, sobre días que ninguno de los dos vio y por más que el ruido de una
predicción. La regla se escribe antes de mirar el resultado, y la decisión
—promover o no— queda en el Registry con sus números. Cambiar el champion
**cambia lo que predice el pipeline sin tocar una línea de código** — ese es el
punto entero de tener un registry.

**4. ⚙️ Airflow para ML — el modelo como task de un DAG.**
[`dag_crypto_ml.py`](ejercicios/dag_crypto_ml.py) predice en batch, disparado
**por el asset de Silver**, en paralelo a Gold, no por reloj. Predice **una vez
por día**: con la corrida que trae el último snapshot del día (23:45 UTC, 20:45
en Argentina); las demás corridas del día la saltean. En la grilla de Airflow se
ve por el color: `score_con_champion` queda en **verde** en la corrida que
predice y en **rosa** (*skipped*) en las demás. Carga el champion del Registry,
escribe `gold.predicciones` de forma
**idempotente** (DELETE del día + INSERT) y **saltea con log claro** cuando
todavía no hay champion, en vez de ponerse en rojo. En la misma corrida arma
`gold.gold_abt_crypto`, la ABT con el último estado de cada cripto (una fila
por cripto); el modelo no la usa, porque necesita una fila por cripto y por día.
El notebook cierra mirando qué escribió el DAG: con qué versión del champion, y
qué criptos ve más probables entre las movidas de mañana.

**5. 🔀 Training-serving skew — el error que no avisa.** La ventana con la que
armar las features **no está hardcodeada**: el DAG la lee del param
`ventana_dias` del propio champion. Si el champion fue entrenado con otras
features, **lo detecta y saltea** en vez de escribir basura. Y el SQL de las
features es **la misma query** en el notebook y en el DAG: está copiada,
idéntica, en los dos.

**6. 📊 Monitoring — el tablero corrige al modelo.** La página `6_Gold_ML`
cuenta el ciclo del modelo en cuatro bloques: qué versión está en producción
(`@champion`) y cuál espera (`@challenger`), qué predice, **cómo le va** contra
lo que efectivamente pasó y cómo llegó ahí (las decisiones champion contra
challenger). El "cómo le va" se mide al lado de **dos referencias** sin
entrenamiento:

- **La clase mayoritaria**. Ronda 50% porque el target está balanceado por
  construcción.
- **La persistencia**, *«mañana se repite lo de hoy»*. Sin features, sin
  entrenar, sin MLflow.

Son dos mediciones distintas y conviene no mezclarlas. El **walk-forward del
notebook** evalúa sobre las fechas que hay en ese momento. El **tablero** mide las
predicciones que el DAG fue escribiendo en `gold.predicciones` contra lo que
después pasó, al lado de las dos referencias. Por eso los dos números no tienen
por qué coincidir, y los del tablero cambian una vez por día, cuando entra el
día que cerró.

---

#### El modelo, en breve (el contexto mínimo, y nada más)

**El modelo no es el tema de la clase**: es el vehículo para ver las
herramientas. Lo que hay que saber para seguir los seis puntos:

- **Qué se predice**: cuáles van a ser **las criptos más movidas mañana**
  (`vol_mañana > mediana de la volatilidad de mañana`). Al ser un target
  relativo queda balanceado por construcción, así que el número es comparable
  entre días.
- **Con qué**: la volatilidad intradía, el rango, el volumen y el rank de cada
  día, más los de ayer y sus promedios móviles. Salen de los snapshots por cripto
  y por día que `silver.crypto_markets` acumula y que el cierre diario descarta
  — exactamente lo que se decidió guardar en la clase 05. Cuántos son depende de
  las horas que tengas el stack prendido: uno cada 15 minutos, o sea **hasta 96
  por día** con el reloj solo, y menos si el stack estuvo apagado un rato. Y
  `features_sql` descarta el día entero si tiene 20 snapshots o menos
  (`HAVING count(*) > 20`, unas 5 horas de stack prendido): con menos no hay
  volatilidad representativa.
- **Cuándo cuenta un día**: el día del pipeline es UTC (en Argentina, de 21 a
  21) y entra cuando ya está su último snapshot, el de las 23:45 UTC (20:45 en
  Argentina). Antes, su volatilidad todavía cambia; por eso el modelo predice una
  vez por día, con el día cerrado.
- **Cómo se mide**: split temporal por **fechas únicas** (walk-forward), jamás
  por posición de fila. Los 6 runs se evalúan sobre **las mismas fechas**: si
  cada uno usara las que le alcanzan, no se sabría si la diferencia viene de las
  features o del test set.
- **Qué es la volatilidad y para qué sirve predecirla**: cuánto se sacude el
  precio en el día (desvío ÷ promedio, en %), sin importar hacia dónde. Viene en
  rachas, por eso se puede predecir; la dirección, no: un modelo que la predice
  con estos datos acierta lo mismo que tirar una moneda. Un pronóstico de
  volatilidad no dice *comprá* ni *vendé*: dice cuánto riesgo hay mañana — para
  ampliar un stop, elegir cuándo ejecutar o subir garantías en un exchange. El
  notebook lo explica y lo dibuja con datos reales antes del Paso 1.

### Cierre

- **🎁 Bonus Track**: el mapa completo de MLOps, con **cinco piezas marcadas como ya hechas** en esta clase, una **a medias** (Observability Gate) y dos que quedan para después (Feature Stores, Drift).
- **🎓 Mensaje final**: qué construiste este cuatrimestre y qué hacer con eso (última celda del notebook).

---

## ✅ Verificación end-to-end

Después del switch a producción y de promover un champion, estas cuatro respuestas dicen si la rama ML quedó cerrada.

```bash
# 1 · ¿La cadena quedó sin errores de import?
docker exec airflow_standalone airflow dags list-import-errors
# Esperado: "No data found"
```

```sql
-- 2 · ¿crypto_ml escribió predicciones, y con qué modelo?
SELECT champion_version AS version, count(*) AS filas,
       count(DISTINCT fecha_features) AS dias, max(fecha_features) AS ultimo_dia
FROM gold.predicciones GROUP BY champion_version ORDER BY ultimo_dia;
-- Esperado: filas > 0, una fila por cada versión que fue champion.

-- 3 · ¿El tablero puede comparar contra las dos referencias?
SELECT ventana, dias, accuracy, base_persistencia, base_mayoritaria
FROM gold.v_ml_veredicto ORDER BY ventana;
-- Esperado: 1 fila, la ventana de 7 días. Si viene vacía, la predicción
-- de hoy todavía no se puede corregir: apunta a mañana.

-- 4 · ¿La ABT quedó escrita? Es la FOTO: una fila por cripto, sin historia.
SELECT count(*) AS filas, max(_processed_at) AS armada FROM gold.gold_abt_crypto;
-- Esperado: filas > 0, armada en la última corrida de crypto_ml.
```

Y en MLflow (`localhost:5000` → **Models**): `crypto_volatilidad_7d` tiene que tener una versión con el alias `@champion`. **Sin ese alias el DAG no falla**: loguea `[SKIP]` y sale limpio, así que las predicciones pueden faltar sin que nada se ponga en rojo. Es el diseño anti-rojo de la clase, y es la primera cosa a mirar si la query 2 devuelve vacío.

Y la versión que entró como challenger en la última corrida tiene los **tags de la decisión** (`decision`, `acc_champion`, `acc_challenger`, `holdout_desde`, `holdout_hasta`): si promovió, ahora lleva el alias `@champion`; si no, sigue como `@challenger`.

Si las cuatro dan, la rama ML está **servida, corregida y mirable**: el DAG se dispara solo cuando Silver publica su asset y predice una vez por día, el tablero compara contra la persistencia y la decisión de promover queda registrada en el Registry.

---

## 🎁 Bonus Track: el mapa de MLOps, y dónde estás parado

La mitad de esta tabla **ya la hiciste hoy**. Sirve para ver qué te falta, no para asustarte:

| Concepto | Para qué sirve | ¿En esta clase? |
|----------|----------------|-----------------|
| **Experiment tracking** | Que un resultado se pueda reproducir y comparar | ✅ **Sí** — MLflow del stack, 6 runs con params, métricas y artifacts |
| **Model Registry** | Versionado y promoción con aliases | ✅ **Sí** — un modelo, el que sirve el DAG; el nuevo entra como `@challenger` y reemplaza al `@champion` solo si le gana |
| **Model serving** | Que el modelo prediga solo, sin que nadie corra nada | ✅ **Sí** — `dag_crypto_ml`, disparado por asset e idempotente |
| **Training-Serving Skew** | Features idénticas al entrenar y al predecir | ✅ **Sí** — la misma query en el notebook y en el DAG, y el DAG saltea si el modelo espera otras features |
| **Monitoring del modelo** | Saber si sigue sirviendo después del deploy | ✅ **Sí** — la página `6_Gold_ML`, contra dos referencias |
| **Feature Stores** (Feast, Tecton) | Reuso de features entre equipos y proyectos | ❌ No — con un solo pipeline, una vista de Gold alcanza |
| **Data Drift detection** | Alertar cuando los datos de inferencia se alejan del training | ❌ No — necesita meses de historia para calibrar |
| **Observability Gate** | Bloquear un deploy automáticamente si las métricas no dan | 🟡 **A medias** — la regla está escrita (champion contra challenger), pero la corrés vos desde el notebook. Automatizarla es meter esa celda en un DAG |

Lo que falta es **carrera completa**. Si te interesa profundizar:
- Material MLOps avanzado (Feature Stores, Drift, Model Serving): en preparación para próximas ediciones.
- Cursos: "Machine Learning Engineering for Production (MLOps)" (Coursera/DeepLearning.AI), "Made With ML" (Goku Mohandas).

---

## 📦 La entrega de esta clase

Abrí [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb): la **Parte 1** deja siete candidatos en MLflow y te muestra cómo consultarlos; la **Parte 2** es tu veredicto — cuál promoverías a producción (o si ninguno está listo) y qué dice tu tablero cuando pone al modelo del pipeline al lado de la persistencia. La sección **📦 Entrega** relee el tracking y genera `ejercicios/estudiantes/<apellido>-<nombre>.txt`.

**Commit y push.** Es **un** archivo. Desde la raíz del repo:

```bash
git add clase06/ejercicios/estudiantes/<apellido>-<nombre>.txt
git commit -m "clase06 (MachineLearning)"
git push origin estudiante/apellido-nombre
```

> ⚠️ **Lo único que commiteás es tu `.txt`.** No uses `git add .`, y no commitees el `.ipynb` ni nada de `stack/` — son archivos que comparte todo el curso. Si tuviste que cambiar algo ahí para que te funcione (un puerto, una versión), dejalo en tu máquina **sin commitear**. Y si encontraste algo roto en el material, **abrí un issue** en vez de arreglarlo en tu rama: así se corrige para todos.

> **Una rama para siempre, un PR para siempre**: tu rama `estudiante/apellido-nombre` y tu PR son los mismos desde la Clase 01; el push actualiza ese mismo PR (no abrís uno nuevo). Reglas completas en [`ejercicios/README.md`](ejercicios/README.md).

> Esta entrega es de **lectura y decisión**, de diez minutos. **No reemplaza al TP Final**, que es el trabajo grande del cierre y se entrega la semana siguiente.

---

## 🎓 Cierre del cuatrimestre

Si llegaste hasta acá hiciste **un pipeline completo de Data Engineering**: desde una API real hasta un modelo servido por un DAG data-aware, con tracking y registry. Eso es portfolio, eso es lo que separa a alguien que "sabe Python" de un Data Engineer junior.

**Próximos pasos sugeridos**: dejá el stack corriendo (la Parte 2 mejora sola a medida que se acumula historia) y aplicá el mismo patrón a un dataset de tu interés. Cambiá la fuente de Bronze, ajustá Silver al dominio, modelá Gold para la pregunta de negocio que querés responder. Ese ejercicio es el verdadero capstone.

El **mensaje final** completo está en la última celda del notebook.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| `silver.crypto_markets` está vacía | La llena `crypto_silver` en cada corrida, con lo que trae Bronze. Verificá que `crypto_bronze` y `crypto_silver` hayan corrido OK en Airflow |
| Todo aparece como **NO CONCLUYENTE** | Esperable con poca historia: el guard pide ≥ 14 fechas distintas y el warehouse suma 1 por día. Dejá el stack corriendo y volvé a correr la Parte 2 |
| `ImportError: sklearn` o `mlflow` | Activá tu entorno y `pip install -r requirements.txt` (raíz del repo) |
| MLflow no responde en `localhost:5000` | El server es **parte del stack** (no hay que correr nada a mano). Primero mirá si el container está vivo: `docker compose ps mlflow`. Si no está, levantalo con `docker compose up -d mlflow` desde `stack/` |
| El container `mlflow` figura `Exited` | Mirá sus logs: `docker compose logs mlflow`. Si dice `ImportError: cannot import name 'FallbackAsyncAdaptedQueuePool' from 'sqlalchemy.pool'`, la imagen se construyó con una SQLAlchemy que mlflow 3.4.0 no soporta. Bajá lo nuevo de `main` y **reconstruí la imagen**: `docker compose build mlflow && docker compose up -d mlflow`. Con `up` solo no alcanza |
| `log_model` falla con `404` en `/api/2.0/mlflow/logged-models` | Cliente y server difieren en la versión **mayor** de MLflow. Instalá la pineada: `pip install mlflow==3.4.0` |
| `load_model(...)` desde el notebook se cuelga y da `Read timed out` | En Windows, el port-forward de Docker Desktop no cierra bien las respuestas *chunked* del proxy de artifacts (**la descarga al host se cuelga; la subida anda salvo con artefactos grandes — ver la fila siguiente**). Por eso la celda 3.4 recarga el champion **adentro de la red** (`docker exec` → `http://mlflow:5000`) — igual que el DAG. Adentro de la red no existe el problema |
| `log_model` corta con `Read timed out` al **subir** | Mismo origen que la fila anterior: el proxy de artifacts sobre el port-forward de Docker Desktop. **No depende del tamaño** — falla hasta con un YAML de 2 kB. Por eso la grilla del paso 3.1 loguea **desde adentro de la red** (`docker exec` → `http://mlflow:5000`). Si escribís tu propio código de tracking, seguí ese patrón |
| El `docker exec` del notebook falla con `connection refused` en `127.0.0.1:2375` | Tenés una variable de entorno `DOCKER_HOST` apuntando a un daemon viejo. Borrala de las variables de usuario y reabrí la terminal / VS Code |
| `crypto_ml` no se dispara nunca | Consume el asset `silver_crypto_markets`, que emite `crypto_silver`: hace falta que `crypto_silver` esté **despausado** y corriendo (el switch de la Parte 1), y que `crypto_ml` mismo no esté pausado — un consumidor pausado no se auto-dispara |
| `airflow dags test crypto_ml` falla con `Task Instance not found` al terminar una task | El DAG está despausado, y el scheduler también agarra la corrida que creó `dags test`: los dos ejecutan la misma task, el scheduler le cambia el id y `dags test` termina con uno que ya no existe. No es el código del DAG. Para probarlo en el momento: `airflow dags pause crypto_ml`, `airflow dags test crypto_ml` y `airflow dags unpause crypto_ml`; o dispará una corrida real con `airflow dags trigger crypto_ml` |
| El modelo queda por debajo de la **persistencia** | Es un resultado posible: la persistencia (*"mañana igual que hoy"*) **es** la hipótesis de volatility clustering hecha regla. Con pocas fechas de test, la diferencia suele ser menor que lo que mueve una sola predicción; la celda imprime ese número |
| Accuracy sospechosamente alta | Sospechá **leakage**: target disfrazado de feature, split que mezcla días, o grano intradía filtrándose en el cierre |
