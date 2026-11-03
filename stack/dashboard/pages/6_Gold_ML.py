"""
🤖 Gold · Machine Learning — el modelo en producción.

La página cuenta el ciclo de vida del modelo (MLOps), en el orden en que se
explica:

    0. Qué predice el modelo   (una pregunta, con un ejemplo real)
    1. En producción           (Model Registry: @champion y @challenger)
    2. Qué predice             (la predicción del último día cerrado)
    3. Cómo le va              (contra lo que pasó, al lado de dos referencias)
    4. Cómo llegó ahí          (las decisiones champion contra challenger)

MLflow se lee por su API REST (no hace falta el cliente de mlflow en el
dashboard): el tracking server es un servicio más del stack, igual que Postgres.
"""

import datetime as dt

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from db import run_query as q
from theme import (aplicar_tema, encabezado, pill, kpi, seccion, aviso, layout, tabla,
                   fecha_larga, SUBE, BAJA, GRIS)

aplicar_tema("Gold · ML", "🤖")

MLFLOW = "http://mlflow:5000"       # nombre del servicio dentro de la red Docker
MODELO = "crypto_volatilidad_7d"    # el que registra el notebook y sirve crypto_ml
VENTANA = 7
MIN_DIAS = 14                        # el mismo umbral que usa el notebook de clase06


@st.cache_data(ttl=60)
def mlflow_get(ruta: str, params: dict = None) -> dict:
    """GET a la API REST de MLflow. Devuelve {} si el server no responde."""
    try:
        r = requests.get(f"{MLFLOW}/api/2.0/mlflow/{ruta}", params=params or {}, timeout=8)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def version(v: str) -> dict:
    """Una versión del modelo con sus tags y lo que dice su run."""
    mv = mlflow_get("model-versions/get", {"name": MODELO, "version": v}).get("model_version", {})
    run = mlflow_get("runs/get", {"run_id": mv.get("run_id", "")}).get("run", {}).get("data", {})
    params = {x["key"]: x["value"] for x in run.get("params", [])}
    tags_run = {x["key"]: x["value"] for x in run.get("tags", [])}
    creada = dt.datetime.utcfromtimestamp(int(mv.get("creation_timestamp", 0)) / 1000)
    return {
        "version": v,
        "creada": creada,
        "tags": {x["key"]: x["value"] for x in mv.get("tags", [])},
        "algoritmo": tags_run.get("algoritmo", params.get("model_type", "—")),
        # Hasta qué día vio datos. Las versiones viejas no lo tienen: se usa
        # el día en que se registraron, como hace la sección 3.3 del notebook.
        "corte": pd.Timestamp(params.get("fecha_corte") or creada.date()),
    }


def resultado(tags: dict) -> tuple:
    """La decisión de la sección 3.3, corta: (texto, variable de color del tema)."""
    d = tags.get("decision")
    if not d:
        return "—", "--ink-3"
    if d.startswith("promovido: no habia"):
        return "Primero: no había champion", "--up"
    if d.startswith("sin comparar"):
        return "Sin comparar", "--ink-2"
    if d == "promovido":
        return "Ganó: promovido", "--up"
    if "dif_predicciones" not in tags:
        return "No promovido", "--ink-2"
    dif = int(tags["dif_predicciones"])
    if dif < 0:
        return "Perdió", "--down"
    if dif == 0:
        return "Empató", "--ink-2"
    return "Ganó por poco: no alcanza", "--ink-2"


def etiqueta(tags: dict) -> str:
    """El resultado con su color; sin punto cuando no hay decisión registrada."""
    texto, color = resultado(tags)
    punto = "" if texto == "—" else "● "
    return f"<b style='color:var({color})'>{punto}{texto}</b>"


vivo = bool(mlflow_get("experiments/search", {"max_results": 1}))
estado = pill("MLFLOW ONLINE", "--up", "tracking :5000") if vivo \
    else pill("MLFLOW CAÍDO", "--down", "docker compose up -d mlflow")
encabezado("🤖 Gold · Machine Learning",
           "El modelo en producción: qué predice, cómo le va y cómo llegó ahí", estado)

st.markdown(
    "**El ciclo:** el notebook entrena y registra un `@challenger` → se compara con el "
    "`@champion` → si le gana, se mueve el alias → `crypto_ml` predice con el `@champion`, "
    "una vez por día → este tablero lo corrige contra lo que pasó."
)

try:
    dias = int(q("SELECT count(DISTINCT fecha) AS d FROM gold.v_volatilidad_diaria").iloc[0]["d"])
except Exception:
    dias = 0
if dias < MIN_DIAS:
    aviso(f"<b>{dias} de {MIN_DIAS} días de historia.</b> Los números de abajo están "
          "medidos sobre pocos días y cambian con cada día que cierra.", "⏳")

# =========================================================================
# 0) QUÉ PREDICE EL MODELO
# =========================================================================
seccion("Qué predice el modelo", "Una pregunta por cripto y por día")
st.markdown(
    "Para cada cripto: **¿mañana va a estar entre las más movidas del mercado?** "
    "«Movida» es volatilidad: cuánto se sacude el precio durante el día, sin importar si "
    "termina arriba o abajo. Se compara contra la mediana del mercado de ese día, así que "
    "la mitad siempre queda arriba."
)
try:
    ej = q("""
        SELECT v.fecha, v.symbol, v.vol
        FROM gold.v_volatilidad_diaria v
        JOIN gold.dim_crypto d USING (crypto_id)
        WHERE v.fecha = (SELECT max(fecha) FROM gold.v_volatilidad_diaria)
          AND d.categoria <> 'stablecoin'
        ORDER BY v.vol DESC
    """)
except Exception:
    ej = pd.DataFrame()
if not ej.empty:
    alta, baja = ej.iloc[0], ej.iloc[-1]
    st.caption(
        f"Ejemplo, el {fecha_larga(alta['fecha'])}: la más movida fue **{alta['symbol']}** "
        f"(se sacudió {float(alta['vol']):.2f} % sobre su precio promedio) y la más calma, "
        f"**{baja['symbol']}** ({float(baja['vol']):.2f} %)."
    )

# =========================================================================
# 1) EN PRODUCCIÓN — el Model Registry
# =========================================================================
seccion("1 · En producción", f"El Model Registry: {MODELO}, el modelo que usa crypto_ml")
aliases = {}
if vivo:
    reg = mlflow_get("registered-models/get", {"name": MODELO}).get("registered_model", {})
    aliases = {a["alias"]: a["version"] for a in reg.get("aliases", [])}

if not vivo:
    aviso("El tracking server no responde: <code>docker compose up -d mlflow</code>.", "🔌")
elif "champion" not in aliases:
    aviso("<b>Todavía no hay <code>@champion</code>.</b> Lo promueve la sección 3.3 del "
          "notebook: el primer modelo entra directo, porque no hay contra quién compararlo.", "🏆")
else:
    champ = version(aliases["champion"])
    c1, c2 = st.columns(2)
    c1.markdown(kpi(
        "@champion · el que está en producción", f"v{champ['version']}",
        foot=f"{champ['algoritmo']} · ventana de {VENTANA} días · aprendió con datos hasta el "
             f"{fecha_larga(champ['corte'])}."), unsafe_allow_html=True)
    if "challenger" in aliases:
        chall = version(aliases["challenger"])
        c2.markdown(kpi(
            "@challenger · el que quiere reemplazarlo", f"v{chall['version']}",
            foot=etiqueta(chall["tags"])), unsafe_allow_html=True)
    else:
        c2.markdown(kpi("@challenger", "—", foot="No hay ninguno esperando."),
                    unsafe_allow_html=True)
    st.caption(f"`crypto_ml` carga `{MODELO}@champion`: mover el alias cambia lo que predice, "
               "sin tocar código.")

# =========================================================================
# 2) QUÉ PREDICE — la predicción del último día cerrado
# =========================================================================
seccion("2 · Lo que predice",
        "Sale una vez por día, a las 20:45 de Argentina, cuando cierra el día (UTC)")
hay_pred = q("SELECT to_regclass('gold.predicciones') IS NOT NULL AS e").iloc[0]["e"]
pred = q("""
    SELECT fecha_features, symbol, predijo_alta_vol, proba_alta_vol, champion_version
    FROM gold.predicciones
    WHERE origen = 'produccion'
      AND fecha_features = (SELECT max(fecha_features) FROM gold.predicciones
                            WHERE origen = 'produccion')
""") if hay_pred else pd.DataFrame()

if pred.empty:
    aviso("Todavía no hay predicciones: <code>crypto_ml</code> predice cuando hay un "
          "<code>@champion</code> y un día cerrado.", "🔮")
else:
    dia = pd.Timestamp(pred["fecha_features"].iloc[0])
    movidas = pred[pred["predijo_alta_vol"] == 1].sort_values("proba_alta_vol")
    st.markdown(
        f"Con el día cerrado del **{fecha_larga(dia)}**, el champion "
        f"**v{pred['champion_version'].iloc[0]}** predice que el "
        f"**{fecha_larga(dia + pd.Timedelta(days=1))}** van a estar entre las más movidas "
        f"**{len(movidas)} de {len(pred)}** criptos:")
    figp = go.Figure(go.Bar(
        x=movidas["proba_alta_vol"] * 100, y=movidas["symbol"], orientation="h",
        marker_color=SUBE, text=[f"{p * 100:.0f} %" for p in movidas["proba_alta_vol"]],
        textposition="outside", hovertemplate="%{y}: %{x:.0f} %<extra></extra>"))
    figp.update_layout(**layout(
        height=max(260, 22 * len(movidas)),
        xaxis=dict(title="probabilidad según el modelo", range=[0, 110]),
        yaxis=dict(title=None)))
    st.plotly_chart(figp, use_container_width=True)

# =========================================================================
# 3) CÓMO LE VA — contra lo que pasó
# =========================================================================
seccion("3 · Cómo le va",
        "Lo que predijo contra lo que pasó, al lado de dos referencias que no entrenan nada")
hay_ver = q("SELECT to_regclass('gold.v_ml_veredicto') IS NOT NULL AS e").iloc[0]["e"]
ver = q(f"SELECT * FROM gold.v_ml_veredicto WHERE ventana = {VENTANA}") if hay_ver else pd.DataFrame()

if ver.empty:
    aviso("Todavía no hay predicciones verificables: cada predicción apunta al día "
          "siguiente, y se corrige cuando ese día cierra.", "🔮")
else:
    v = ver.iloc[0]
    # Cada día tiene UN origen: o lo predijo el champion en vivo (produccion),
    # o lo completó después el DAG (reconstruido, con un modelo entrenado solo
    # con los días anteriores). La predicción en vivo reemplaza a la
    # reconstruida del mismo día: nunca conviven.
    ev = q(f"""
        SELECT dia_predicho,
               round(avg(acerto::int) * 100, 1)                           AS accuracy,
               bool_or(origen = 'produccion')                             AS en_vivo,
               max(champion_version) FILTER (WHERE origen = 'produccion') AS version
        FROM gold.v_ml_aciertos WHERE ventana = {VENTANA}
        GROUP BY dia_predicho ORDER BY dia_predicho
    """)
    n_vivo = int(ev["en_vivo"].sum())
    k1, k2, k3 = st.columns(3)
    k1.markdown(kpi("El modelo", f"{v['accuracy']:.1f} %",
                    foot=f"{int(v['predicciones'])} predicciones en {int(v['dias'])} días: "
                         f"{n_vivo} en vivo y {len(ev) - n_vivo} reconstruidos."),
                unsafe_allow_html=True)
    k2.markdown(kpi("Persistencia", "—" if pd.isna(v["base_persistencia"])
                    else f"{v['base_persistencia']:.1f} %",
                    foot="«Mañana se repite lo de hoy». Sin modelo."), unsafe_allow_html=True)
    k3.markdown(kpi("Clase mayoritaria", "—" if pd.isna(v["base_mayoritaria"])
                    else f"{v['base_mayoritaria']:.1f} %",
                    foot="Ronda el 50 %: la mitad siempre queda arriba."), unsafe_allow_html=True)

    if len(ev) >= 2:
        # Un día sin dato (stack apagado, o 20 snapshots o menos) queda como
        # HUECO en la línea: unir con una recta dos días que no son seguidos
        # hace parecer que hubo datos en el medio.
        ev["dia_predicho"] = pd.to_datetime(ev["dia_predicho"])
        ev = ev.set_index("dia_predicho").asfreq("D").reset_index()
        en_vivo = ev[ev["en_vivo"] == True]       # noqa: E712 -- tras asfreq hay NaN
        reconstruido = ev[ev["en_vivo"] == False]  # noqa: E712
        fige = go.Figure(go.Scatter(
            x=ev["dia_predicho"], y=ev["accuracy"], mode="lines", showlegend=False,
            line=dict(color=SUBE, width=2), hoverinfo="skip"))
        fige.add_trace(go.Scatter(
            x=en_vivo["dia_predicho"], y=en_vivo["accuracy"], mode="markers",
            name="en vivo: lo predijo el champion", marker=dict(size=7, color=SUBE),
            customdata=en_vivo["version"],
            hovertemplate="%{x|%d-%m}: %{y:.1f} % · en vivo, v%{customdata}<extra></extra>"))
        fige.add_trace(go.Scatter(
            x=reconstruido["dia_predicho"], y=reconstruido["accuracy"], mode="markers",
            name="reconstruido después",
            marker=dict(size=8, color=SUBE, symbol="circle-open", line=dict(width=2)),
            hovertemplate="%{x|%d-%m}: %{y:.1f} % · reconstruido<extra></extra>"))
        if pd.notna(v["base_persistencia"]):
            fige.add_hline(y=float(v["base_persistencia"]), line_dash="dash", line_color=BAJA,
                           annotation_text="persistencia", annotation_font=dict(color=BAJA))
        fige.add_hline(y=50, line_dash="dot", line_color=GRIS,
                       annotation_text="clase mayoritaria", annotation_position="bottom left",
                       annotation_font=dict(color=GRIS))
        fige.update_layout(**layout(
            height=340, yaxis=dict(title="% de aciertos", range=[0, 100]), showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0)))
        st.plotly_chart(fige, use_container_width=True)
        st.caption("Cada punto es un día que ya cerró: qué parte de las criptos acertó el modelo. "
                   "Lleno: lo predijo el champion en vivo. Hueco: ese día no hubo predicción en "
                   "vivo y el DAG la completó después, con un modelo entrenado solo con los "
                   "días anteriores. Los cortes de la línea son días sin datos suficientes.")

# =========================================================================
# 4) CÓMO LLEGÓ AHÍ — champion contra challenger
# =========================================================================
seccion("4 · Cómo llegó ahí",
        "Champion contra challenger: el nuevo reemplaza al vigente solo si le gana")
st.markdown(
    "**La regla, escrita antes de mirar:** el challenger reemplaza al champion si le gana por "
    "**más de una predicción**, sobre días que ninguno de los dos vio. Cada vez que se corre la "
    "sección 3.3 del notebook se registra una versión nueva y la decisión queda en sus tags."
)
if vivo:
    vs = mlflow_get("model-versions/search", {"filter": f"name='{MODELO}'"}).get("model_versions", [])
    alias_de = {ver_: al for al, ver_ in aliases.items()}
    filas = ""
    # Una fila por versión registrada, de la más nueva a la más vieja: la
    # historia de los challengers, con la decisión que quedó en sus tags.
    for n in sorted((m["version"] for m in vs), key=int, reverse=True):
        x = version(n)
        t = x["tags"]
        _, color = resultado(t)
        dif = int(t["dif_predicciones"]) if "dif_predicciones" in t else None
        dif_txt = "" if dif is None else ("0" if dif == 0 else f"{dif:+d}".replace("-", "−"))
        # Los tags guardan los días de las FEATURES (holdout_desde/hasta); cada
        # uno predice el día siguiente. Se muestran los días PREDICHOS, que son
        # los que aparecen en el gráfico de "Cómo le va".
        un_dia = pd.Timedelta(days=1)
        dias = (f"{pd.Timestamp(t['holdout_desde']) + un_dia:%d/%m} al "
                f"{pd.Timestamp(t['holdout_hasta']) + un_dia:%d/%m}"
                if "holdout_desde" in t and "holdout_hasta" in t else "")
        al = f"<span class='sym'>@{alias_de[n]}</span>" if n in alias_de else ""
        registrada = x["creada"] - dt.timedelta(hours=3)      # hora de Argentina
        filas += (f"<tr><td>v{n}{al}</td>"
                  f"<td>{etiqueta(t)}</td>"
                  f"<td style='color:var({color})'>{dif_txt}</td>"
                  f"<td>{t.get('vs_champion', '')}</td>"
                  f"<td>{dias}</td>"
                  f"<td>{registrada:%d/%m}</td></tr>")
    if filas:
        tabla(filas, ["Versión", "Resultado", "Diferencia", "Contra", "Días predichos",
                      "Registrada"])
        st.caption("Diferencia: cuántas predicciones más (o menos) acertó el challenger que "
                   "el champion, sobre los mismos días.")
