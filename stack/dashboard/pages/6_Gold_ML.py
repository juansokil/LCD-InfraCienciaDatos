"""
🤖 Gold · Machine Learning — la otra salida de Gold.

Gold tiene dos consumidores: el dashboard (BI) y el modelo (ML). Esta
página muestra la rama ML de punta a punta:

    ABT (features) → entrenamiento → MLflow (tracking) → champion → predicciones

Los datos de MLflow se leen por su API REST (no hace falta el cliente de
mlflow instalado en el dashboard): el tracking server es un servicio más
del stack, igual que Postgres.
"""

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from db import estado_pipeline, run_query
from theme import (aplicar_tema, encabezado, pill, kpi, seccion, aviso,
                   de_donde_sale, layout, filtro_periodo, where_periodo,
                   PLOTLY, SUBE, BAJA, GRIS)

aplicar_tema("Gold · ML", "🤖")

MLFLOW = "http://mlflow:5000"       # nombre del servicio dentro de la red Docker
EXPERIMENTO = "crypto_direccion_diaria"
MIN_DIAS = 14                        # el mismo umbral que usa el notebook de clase06


# run_query ya viene cacheado desde db.py (ttl=60). Este alias queda solo
# por comodidad de lectura: `q(...)` es mas corto dentro de las paginas.
q = run_query


@st.cache_data(ttl=60)
def mlflow_post(ruta: str, payload: dict):
    """Llama a la API REST de MLflow. Devuelve {} si el server no responde."""
    try:
        r = requests.post(f"{MLFLOW}/api/2.0/mlflow/{ruta}", json=payload, timeout=8)
        return r.json() if r.ok else {}
    except Exception:
        return {}


@st.cache_data(ttl=60)
def mlflow_get(ruta: str, params: dict = None):
    try:
        r = requests.get(f"{MLFLOW}/api/2.0/mlflow/{ruta}", params=params or {}, timeout=8)
        return r.json() if r.ok else {}
    except Exception:
        return {}


# --- estado del tracking server -------------------------------------------
vivo = bool(mlflow_get("experiments/search", None) or mlflow_post("experiments/search", {"max_results": 1}))
estado = pill("MLFLOW ONLINE", "--up", "tracking :5000") if vivo \
    else pill("MLFLOW CAÍDO", "--down", "docker compose up -d mlflow")

encabezado("🤖 Gold · Machine Learning",
           "La rama ML de Gold: features → entrenamiento → champion → predicciones", estado)

# =========================================================================
# 1) LA ABT: el dataset que consume el modelo
# =========================================================================
seccion("La ABT", "Analytical Base Table: una fila por activo, todas las features en columnas")

try:
    abt = q("SELECT * FROM gold.gold_abt_crypto")
except Exception:
    abt = pd.DataFrame()

if abt.empty:
    st.info("🕐 **`gold.gold_abt_crypto` todavía no tiene datos.** La construye `crypto_gold` "
            "en cada corrida (cada 15 minutos).")
else:
    feats = [c for c in abt.columns if not c.startswith("_")]
    dias = q("SELECT count(DISTINCT fecha) AS d FROM gold.v_series_diaria").iloc[0]["d"]
    cols = st.columns(4)
    cols[0].markdown(kpi("Filas", f"{len(abt)}",
                         foot="Una por activo. Grano de la ABT: la 'unidad' que el modelo predice."),
                     unsafe_allow_html=True)
    cols[1].markdown(kpi("Features", f"{len(feats)}",
                         foot="Ya calculadas en SQL: el modelo no transforma, solo consume."),
                     unsafe_allow_html=True)
    cols[2].markdown(kpi("Días de historia", f"{int(dias)}",
                         foot=f"Para entrenar con validación temporal honesta hacen falta ~{MIN_DIAS}."),
                     unsafe_allow_html=True)
    # Contadas de la ABT, no escritas a mano: antes decia "3" como string
    # literal y el dia que la ABT sumara una categorica el tablero iba a seguir
    # diciendo 3, sin que nada fallara.
    categoricas = [c for c in abt.columns
                   if abt[c].dtype == "object" and abt[c].nunique() <= 8
                   and c not in ("crypto_id", "symbol", "name")]
    cols[3].markdown(kpi("Categóricas derivadas", f"{len(categoricas)}",
                         foot=(" · ".join(categoricas) if categoricas else "ninguna")
                              + " — bucketizadas con CASE WHEN en SQL, no en pandas."),
                     unsafe_allow_html=True)

    with st.expander("Ver las features de la ABT"):
        st.dataframe(
            pd.DataFrame({"feature": feats,
                          "tipo": [str(abt[c].dtype) for c in feats],
                          "nulos %": [f"{abt[c].isna().mean() * 100:.0f}%" for c in feats]}),
            hide_index=True, use_container_width=True, height=380,
        )

# =========================================================================
# 2) ESTADO DEL ENTRENAMIENTO
# =============================================================
# ¿COMO SABEMOS SI EL MODELO SIRVE?
# =============================================================
seccion("¿Cómo sabemos si el modelo sirve?",
        "¿Acertó qué criptos iban a ser las más movidas? Medido contra lo que pasó")

# El filtro va ARRIBA de los paneles que gobierna, no adentro de uno: si cada
# tarjeta trae el suyo, dos paneles vecinos terminan mostrando periodos distintos
# y nadie se da cuenta.
periodo = filtro_periodo("ml", default="30 días")
W_PER = where_periodo("dia_predicho", periodo)

hay_vista = q("SELECT to_regclass('gold.v_ml_aciertos') IS NOT NULL AS e").iloc[0]["e"]
porv = q(f"""
    WITH dia AS (
        SELECT ventana, dia_predicho,
               avg(acerto::int)                 AS acc,
               avg(realmente_alta_vol::numeric)    AS subio,
               count(*)                         AS n
        FROM gold.v_ml_aciertos WHERE 1=1 {W_PER} GROUP BY ventana, dia_predicho
    ),
    con_pasado AS (
        -- Lo que se sabia ANTES de ese dia: la proporcion que venia subiendo.
        -- Es la unica informacion con la que se puede elegir la regla tonta sin
        -- hacer trampa. Mirar el resultado del propio dia para decidir que
        -- predecir es leakage: elige el lado ganador despues del partido.
        SELECT d.*,
               avg(d.subio) OVER (PARTITION BY d.ventana ORDER BY d.dia_predicho
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
                                                AS subio_hist
        FROM dia d
    )
    SELECT ventana,
           count(*)                                          AS dias,
           sum(n)                                            AS predicciones,
           round(avg(acc) * 100, 1)                          AS accuracy,
           round(avg(CASE WHEN subio_hist IS NULL THEN NULL
                          WHEN subio_hist > 0.5 THEN subio
                          ELSE 1 - subio END) * 100, 1)      AS baseline
    FROM con_pasado GROUP BY ventana ORDER BY ventana
""") if hay_vista else pd.DataFrame()

if porv.empty:
    aviso(
        "<b>Todavía no hay predicciones verificables, y es lo esperable.</b> "
        "La predicción de hoy apunta a <b>mañana</b>: recién se puede corregir "
        "cuando mañana ocurra. No se puede corregir un examen sin las respuestas.",
        "🔮",
    )
else:
    tabla = porv.assign(
        modelo=porv["ventana"].map(lambda w: f"ventana {int(w)}d"),
        # Sin baseline no se puede opinar: con un solo dia no hay historia
        # previa con la que elegir la regla tonta. "no" seria una conclusion
        # inventada; el guion dice la verdad -- todavia no se sabe.
        le_gana=[("—" if pd.isna(b) else ("sí" if a > b else "no"))
                 for a, b in zip(porv["accuracy"], porv["baseline"])],
    )[["modelo", "dias", "predicciones", "accuracy", "baseline", "le_gana"]]

    st.dataframe(
        tabla, hide_index=True, use_container_width=True,
        column_config={
            "modelo": "Modelo", "dias": "Días",
            "predicciones": st.column_config.NumberColumn("Predicciones"),
            "accuracy": st.column_config.NumberColumn("Accuracy", format="%.1f%%"),
            "baseline": st.column_config.NumberColumn("Baseline", format="%.1f%%"),
            "le_gana": "¿Le gana?",
        },
    )

    # El ejemplo sale del dia mas desbalanceado que haya: explicar el baseline
    # en abstracto no alcanza, con un numero real se entiende solo.
    ej = q(f"""
        SELECT dia_predicho, count(*) AS n, sum(realmente_alta_vol) AS subieron
        FROM gold.v_ml_aciertos WHERE 1=1 {W_PER}
        GROUP BY dia_predicho
        ORDER BY abs(avg(realmente_alta_vol::numeric) - 0.5) DESC LIMIT 1
    """)
    if not ej.empty:
        e = ej.iloc[0]
        n, sub = int(e["n"]), int(e["subieron"])
        baj = n - sub
        may, verbo = (baj, "bajan") if baj >= sub else (sub, "suben")
        aviso(
            f"<b>El baseline es la regla más tonta posible: predecir siempre lo "
            f"que venía pasando</b>, sin mirar las features. Acá ronda el 50% "
            f"porque el target está balanceado por construcción — la mitad de las "
            f"criptos supera a la mediana del día, siempre.<br><br>"
            f"<b>Ese balance es lo que hace la comparación limpia.</b> Cuando una "
            f"clase domina, un accuracy alto no significa nada; acá el 50% es un "
            f"piso real y todo lo que esté por encima es señal.<br><br>"
            f"El modelo aprende porque <b>la volatilidad se agrupa</b>: un día "
            f"movido sigue a otro movido. Es de los hechos más establecidos en "
            f"finanzas, y se calcula con los ~66 snapshots por cripto por día que "
            f"el cierre diario descarta.",
            "📏",
        )
    # --- Evolucion: una linea por ventana ------------------------------
    st.markdown("###### Evolución del accuracy")
    ev = q(f"""
        SELECT dia_predicho, ventana,
               round(avg(acerto::int) * 100, 1)                    AS accuracy,
               count(*)                                            AS n
        FROM gold.v_ml_aciertos WHERE 1=1 {W_PER}
        GROUP BY dia_predicho, ventana ORDER BY dia_predicho, ventana
    """)
    if ev["dia_predicho"].nunique() < 2:
        st.caption("Con un solo día no hay evolución que mirar. La serie se arma "
                   "sola: cada corrida del pipeline suma un punto.")
    else:
        fige = go.Figure()
        for i, (W, g) in enumerate(ev.groupby("ventana")):
            fige.add_trace(go.Scatter(
                x=g["dia_predicho"], y=g["accuracy"], mode="lines+markers",
                name=f"ventana {int(W)}d",
                line=dict(width=2), marker=dict(size=7),
                hovertemplate="<b>ventana " + str(int(W)) + "d</b><br>"
                              "%{x|%d-%m}: %{y:.1f}%<extra></extra>"))
        fige.add_hline(y=50, line_dash="dash", line_color=GRIS,
                       annotation_text="50% — el piso")
        fige.update_layout(**layout(
            height=320,
            yaxis=dict(title="% de aciertos", range=[0, 100]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        ))
        st.plotly_chart(fige, use_container_width=True)
        st.caption("Un día suelto dice poco: lo que importa es si la ventaja sobre "
                   "el 50% **se sostiene**. Una línea que cruza el piso y vuelve "
                   "es ruido; una que se mantiene arriba es señal.")

    # --- Desagregado por moneda ----------------------------------------
    st.markdown("###### ¿En qué criptos acierta?")
    pormoneda = q(f"""
        SELECT COALESCE(symbol, crypto_id)                         AS cripto,
               count(*)                                            AS predicciones,
               sum(acerto::int)                                    AS aciertos,
               round(avg(acerto::int) * 100, 1)                    AS accuracy,
               round(avg(realmente_alta_vol::numeric) * 100, 1)    AS pct_fue_volatil
        FROM gold.v_ml_aciertos WHERE 1=1 {W_PER}
        GROUP BY 1 HAVING count(*) >= 2
        ORDER BY accuracy DESC, predicciones DESC
    """)
    if pormoneda.empty:
        st.caption("Todavía no hay suficientes predicciones por cripto para abrir "
                   "el detalle.")
    else:
        st.dataframe(
            pormoneda, hide_index=True, use_container_width=True, height=280,
            column_config={
                "cripto": "Cripto",
                "predicciones": st.column_config.NumberColumn("Predicciones"),
                "aciertos": st.column_config.NumberColumn("Aciertos"),
                "accuracy": st.column_config.ProgressColumn(
                    "Accuracy", format="%.1f%%", min_value=0, max_value=100),
                "pct_fue_volatil": st.column_config.NumberColumn(
                    "Fue volátil", format="%.0f%%"),
            },
        )
        st.caption("Ordenado de mejor a peor. La última columna dice cuántas veces "
                   "esa cripto fue efectivamente de las movidas: una que siempre "
                   "lo es (o nunca) es fácil de acertar y no prueba nada — el "
                   "mérito está en las que alternan.")

    st.caption("Ojo con el tamaño de muestra: las ~50 predicciones de un mismo día "
               "comparten el régimen de mercado de esa jornada, así que valen menos "
               "que 50 casos independientes. El número que manda es la columna **Días**.")

# =========================================================================
seccion("Estado del entrenamiento", "¿Hay suficiente historia para entrenar sin engañarse?")

dias_hoy = int(q("SELECT count(DISTINCT fecha) AS d FROM gold.v_series_diaria").iloc[0]["d"]) \
    if not abt.empty else 0
progreso = min(dias_hoy / MIN_DIAS, 1.0)

st.progress(progreso, text=f"{dias_hoy} de {MIN_DIAS} días necesarios")

if dias_hoy < MIN_DIAS:
    aviso(
        f"<b>El pipeline está juntando historia: {dias_hoy} de {MIN_DIAS} días.</b><br><br>"
        "El modelo predice la <b>dirección del precio del día siguiente</b>, así que necesita "
        "una serie de cierres diarios: con pocos días, cualquier accuracy que mostráramos sería "
        "ruido disfrazado de resultado.<br><br>"
        "Mientras tanto el pipeline sigue corriendo solo y sumando un cierre por día. "
        "<b>Cuando llegue al umbral, el notebook de clase06 entrena y registra el champion "
        "sin cambiar una línea de código</b> — y esta página se llena sola.",
        "📅",
    )
else:
    st.caption("✅ Hay historia suficiente para un split temporal honesto.")

# =========================================================================
# 3) EXPERIMENTOS Y RUNS (MLflow)
# =========================================================================
seccion("Experimentos", f"Lo que quedó registrado en MLflow · experimento <code>{EXPERIMENTO}</code>")

if not vivo:
    st.info("🔌 **El tracking server no responde.** Levantalo con `docker compose up -d mlflow` "
            "y recargá esta página.")
else:
    exps = mlflow_post("experiments/search", {"max_results": 50}).get("experiments", [])
    exp = next((e for e in exps if e["name"] == EXPERIMENTO), None)

    if exp is None:
        st.info(f"📋 **El experimento `{EXPERIMENTO}` todavía no existe.** Se crea la primera vez "
                "que el notebook de clase06 loguea un run.")
    else:
        runs = mlflow_post("runs/search", {
            "experiment_ids": [exp["experiment_id"]],
            "max_results": 50,
            "order_by": ["attributes.start_time DESC"],
        }).get("runs", [])

        if not runs:
            st.info("📋 **El experimento existe pero no tiene runs todavía.** "
                    "Aparecen acá apenas el model zoo entrene por primera vez.")
        else:
            filas = []
            for r in runs:
                info, data = r.get("info", {}), r.get("data", {})
                m = {x["key"]: x["value"] for x in data.get("metrics", [])}
                p = {x["key"]: x["value"] for x in data.get("params", [])}
                tags = {x["key"]: x["value"] for x in data.get("tags", [])}
                filas.append({
                    "run": tags.get("mlflow.runName", info.get("run_id", "")[:8]),
                    # Cuanta historia miraba ese modelo. Sin esta columna, dos runs
                    # de ventanas distintas se ven identicos en la tabla.
                    "ventana": (tags["ventana"] + "d" if "ventana" in tags
                                else (p["ventana_dias"] + "d" if "ventana_dias" in p else "-")),
                    "modelo": p.get("modelo", p.get("model", "—")),
                    "accuracy": m.get("accuracy"),
                    "balanced_accuracy": m.get("balanced_accuracy"),
                    "baseline": m.get("baseline_accuracy"),
                    "inicio": pd.to_datetime(info.get("start_time"), unit="ms"),
                    "estado": info.get("status", ""),
                })
            df = pd.DataFrame(filas)

            st.dataframe(
                df, hide_index=True, use_container_width=True,
                column_config={
                    "run": "Run",
                    "ventana": "Ventana",
                    "modelo": "Modelo",
                    "accuracy": st.column_config.NumberColumn("Accuracy", format="%.3f"),
                    "balanced_accuracy": st.column_config.NumberColumn("Balanced acc.", format="%.3f"),
                    "baseline": st.column_config.NumberColumn("Baseline", format="%.3f"),
                    "inicio": st.column_config.DatetimeColumn("Cuándo", format="DD-MM HH:mm"),
                    "estado": "Estado",
                },
            )

            # Comparación contra el baseline: lo único que importa de verdad
            comp = df.dropna(subset=["accuracy"])
            if not comp.empty:
                base = comp["baseline"].dropna().max()
                figm = go.Figure(go.Bar(
                    x=comp["modelo"].fillna(comp["run"]), y=comp["accuracy"],
                    marker=dict(color=[SUBE if (base is None or a >= base) else BAJA
                                       for a in comp["accuracy"]]),
                    text=[f"{a:.3f}" for a in comp["accuracy"]], textposition="outside",
                    hovertemplate="%{x}: %{y:.3f}<extra></extra>",
                ))
                if pd.notna(base):
                    figm.add_hline(y=base, line_color=GRIS, line_dash="dot", line_width=1.5,
                                   annotation_text=f"baseline: {base:.3f}",
                                   annotation_position="top left",
                                   annotation_font=dict(size=11, color=GRIS))
                figm.update_layout(height=280, bargap=0.45, **PLOTLY)
                st.plotly_chart(figm, use_container_width=True)
                st.caption("**La línea del baseline es la que importa.** Un modelo que no le gana "
                           "a 'mañana pasa lo mismo que hoy' no aporta nada, por más sofisticado que sea.")

    # ---- champion registrado --------------------------------------------
    seccion("Modelo en producción", "El champion del Model Registry: el que se usaría para predecir")
    modelos = mlflow_get("registered-models/search").get("registered_models", [])
    if not modelos:
        st.info("🏆 **No hay ningún modelo registrado todavía.** El champion se promueve desde "
                "el notebook cuando un candidato le gana al baseline.")
    else:
        for m in modelos:
            versiones = m.get("latest_versions", [])
            v = versiones[0] if versiones else {}
            st.markdown(
                f"<div class='kpi'><div class='lab'>Modelo registrado</div>"
                f"<div class='val' style='font-size:19px'>{m['name']}</div>"
                f"<div class='foot'>Versión <b>{v.get('version', '—')}</b> · "
                f"etapa <b>{v.get('current_stage', 'None')}</b><br>"
                f"El scoring batch (<code>dag_crypto_ml</code>) lee esta versión: "
                f"cambiar el champion en el Registry cambia lo que predice el pipeline, "
                f"sin tocar código.</div></div>",
                unsafe_allow_html=True,
            )

# =========================================================================
# 4) PREDICCIONES
# =========================================================================
seccion("Predicciones", "Lo que el modelo dice sobre mañana · <code>gold.predicciones</code>")

existe_pred = q("SELECT to_regclass('gold.predicciones') IS NOT NULL AS e").iloc[0]["e"]
if not existe_pred:
    # Por que esta vacio NO es "todavia no corrio": el DAG corre desde hace
    # dias. Corre, no encuentra champion y saltea. Decirlo cambia la accion del
    # que mira: no es esperar, es promover un modelo.
    corridas = estado_pipeline(("crypto_ml",))
    veces = int(corridas.iloc[0]["corridas"]) if not corridas.empty else 0
    detalle = (
        f"El DAG <code>crypto_ml</code> ya corrió <b>{veces} veces</b> y terminó OK "
        "todas: no falló, <b>salteó</b>. Sin un modelo con alias "
        "<code>@champion</code> en el Registry no tiene con qué scorear, así que "
        "loguea <code>[SKIP]</code> y sale limpio.<br><br>"
        "Para que aparezcan predicciones hay que <b>promover un champion</b> desde "
        "el notebook de la clase 06 — esa decisión es humana a propósito y no se "
        "automatiza."
        if veces else
        "Cuando haya champion y predicciones, acá van a aparecer la señal del día "
        "por activo y el acierto acumulado contra lo que realmente pasó."
    )
    aviso(
        "<b>La tabla de predicciones todavía no existe.</b> La escribe el DAG "
        "<code>dag_crypto_ml</code>, que no corre por reloj sino <b>por dato</b>: "
        "<code>schedule=[GOLD_ABT]</code> — se despierta cuando la ABT se actualiza. "
        f"<br><br>{detalle}",
        "🔮",
    )
else:
    # La columna se llama `fecha_features` (asi la crea dag_crypto_ml), no
    # `fecha`. Estaba mal y nadie lo vio porque la tabla nunca existio.
    pred = q("""
        SELECT * FROM gold.predicciones
        ORDER BY fecha_features DESC, crypto_id
        LIMIT 200
    """)
    if pred.empty:
        st.info("La tabla existe pero está vacía — esperá la próxima corrida de `dag_crypto_ml`.")
    else:
        st.dataframe(pred, hide_index=True, use_container_width=True)

de_donde_sale("gold.v_series_diaria",
              "La fuente de las features: el cierre de cada día por cripto, con "
              "el retorno ya calculado. El modelo no ve el dato crudo, ve esto.")
