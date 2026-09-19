"""
🤖 Gold · Machine Learning — la otra salida de Gold.

Gold tiene dos consumidores: el dashboard (BI) y el modelo (ML). Esta página
muestra la rama ML de punta a punta:

    ABT (features) → entrenamiento → MLflow (tracking) → champion → predicciones

La página arranca por el VEREDICTO y termina en la maquinaria, no al revés.
Antes empezaba por la ABT y el resultado quedaba sepultado en el medio: el
que abría la pantalla veía plomería antes que respuesta.

Y el veredicto se da contra DOS varas, no una. El target está balanceado por
construcción, así que ganarle a la clase mayoritaria (~50%) no prueba nada.
La vara que importa es la persistencia — "mañana se repite lo de hoy" —, que
no necesita features ni entrenamiento. La notebook de clase 06 ya la medía;
esta página la ignoraba y declaraba victoria con la fácil.

Los datos de MLflow se leen por su API REST (no hace falta el cliente de
mlflow instalado en el dashboard): el tracking server es un servicio más del
stack, igual que Postgres.
"""

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from db import estado_pipeline, run_query
from theme import (aplicar_tema, encabezado, pill, kpi, seccion, aviso,
                   de_donde_sale, layout, filtro_periodo, where_periodo,
                   fecha_larga, PLOTLY, SUBE, BAJA, GRIS)

aplicar_tema("Gold · ML", "🤖")

MLFLOW = "http://mlflow:5000"       # nombre del servicio dentro de la red Docker
EXPERIMENTO = "crypto_volatilidad"
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
           "¿El modelo sirve? · y después, cómo está hecho", estado)

# --- cuánta historia hay, dicho UNA vez y arriba de todo ------------------
# Antes esto era una seccion propia AL FINAL, con barra de progreso, que
# contradecia los resultados que la pantalla ya venia mostrando arriba
# ("9 de 14 dias necesarios" debajo de una tabla llena de accuracy). El
# umbral es real, pero no bloquea nada: la notebook corre igual y marca sus
# metricas [NO CONCLUYENTE]. Mismo criterio aca -- un sello, no una espera.
try:
    dias_hoy = int(q("SELECT count(DISTINCT fecha) AS d "
                     "FROM gold.v_series_diaria").iloc[0]["d"])
except Exception:
    dias_hoy = 0

CONCLUYENTE = dias_hoy >= MIN_DIAS
if not CONCLUYENTE:
    aviso(
        f"<b>{dias_hoy} de {MIN_DIAS} días de historia · los números de abajo "
        "son NO CONCLUYENTES.</b> El mecanismo funciona y las métricas son "
        "reales, pero medidas sobre un puñado de días son ruido con formato "
        "de número. El pipeline suma un cierre por día y esto se destraba "
        f"solo. <i>(Es el mismo umbral que usa la notebook de clase 06: "
        f"<code>MIN_FECHAS = {MIN_DIAS}</code>.)</i>",
        "⏳",
    )

# =========================================================================
# 1) EL VEREDICTO — lo primero que se ve
# =========================================================================
seccion("¿El modelo sirve?",
        "Acertar qué criptos iban a ser las más movidas · medido contra lo que pasó")

hay_veredicto = q("SELECT to_regclass('gold.v_ml_veredicto') IS NOT NULL AS e").iloc[0]["e"]
ver = q("SELECT * FROM gold.v_ml_veredicto") if hay_veredicto else pd.DataFrame()

if ver.empty:
    aviso(
        "<b>Todavía no hay predicciones verificables, y es lo esperable.</b> "
        "La predicción de hoy apunta a <b>mañana</b>: recién se puede corregir "
        "cuando mañana ocurra. No se puede corregir un examen sin las "
        "respuestas.",
        "🔮",
    )
else:
    # El campeon es la ventana con mejor accuracy. Se elige aca y no en SQL
    # porque es una decision de PRESENTACION (cual destacar), no una metrica.
    mejor = ver.loc[ver["accuracy"].idxmax()]
    pers = mejor["base_persistencia"]
    mayo = mejor["base_mayoritaria"]
    gana_pers = pd.notna(pers) and mejor["accuracy"] > pers
    color_v = SUBE if gana_pers else BAJA

    c = st.columns([1.15, 1, 1])
    c[0].markdown(kpi(
        f"El modelo · ventana {int(mejor['ventana'])}d",
        f"{mejor['accuracy']:.1f} %",
        foot=f"{int(mejor['predicciones'])} predicciones sobre "
             f"{int(mejor['dias'])} días verificados."), unsafe_allow_html=True)
    c[1].markdown(kpi(
        "Vara difícil · mañana = hoy",
        "—" if pd.isna(pers) else f"{pers:.1f} %",
        foot="La volatilidad se agrupa: repetir lo de ayer ya acierta mucho. "
             "<b>Sin features, sin entrenar, sin MLflow.</b>"),
        unsafe_allow_html=True)
    c[2].markdown(kpi(
        "Vara fácil · clase mayoritaria",
        "—" if pd.isna(mayo) else f"{mayo:.1f} %",
        foot="Ronda 50% porque el target está balanceado por construcción. "
             "Ganarle a esto no prueba nada."), unsafe_allow_html=True)

    if pd.isna(pers):
        st.caption("Hace falta un día más para poder calcular la persistencia.")
    else:
        d_p = mejor["accuracy"] - pers
        d_m = mejor["accuracy"] - mayo if pd.notna(mayo) else float("nan")
        st.markdown(
            f"<div class='aviso' style='border-left:3px solid {color_v}'>"
            f"<span>{'🏆' if gana_pers else '🧊'}</span><div>"
            f"<b>Le gana a la vara fácil por {d_m:+.1f} puntos</b> — pero eso "
            f"era casi gratis.<br>"
            f"<b>Contra la vara difícil {'gana' if gana_pers else 'pierde'} "
            f"por {abs(d_p):.1f} puntos.</b><br><br>"
            + ("Entrenar compró algo: el modelo ve en las features lo que la "
               "regla trivial no ve."
               if gana_pers else
               "Conclusión honesta: <b>todavía no justifica haber entrenado</b>. "
               "Una regla de una línea —<i>«la que se movió mucho hoy se va a "
               "mover mucho mañana»</i>— acierta más, sin ABT, sin registry y "
               "sin DAG de scoring.")
            + "</div></div>",
            unsafe_allow_html=True,
        )

    # --- la tabla completa, las tres ventanas --------------------------
    tab = ver.assign(
        modelo=ver["ventana"].map(lambda w: f"ventana {int(w)}d"),
        vs_persistencia=ver["accuracy"] - ver["base_persistencia"],
        le_gana=[("—" if pd.isna(b) else ("sí" if a > b else "no"))
                 for a, b in zip(ver["accuracy"], ver["base_persistencia"])],
    )[["modelo", "dias", "predicciones", "accuracy", "base_mayoritaria",
       "base_persistencia", "vs_persistencia", "le_gana"]]

    st.dataframe(
        tab, hide_index=True, use_container_width=True,
        column_config={
            "modelo": "Modelo", "dias": st.column_config.NumberColumn("Días", width="small"),
            "predicciones": st.column_config.NumberColumn("Predicciones"),
            "accuracy": st.column_config.NumberColumn("Modelo", format="%.1f%%"),
            "base_mayoritaria": st.column_config.NumberColumn("Vara fácil", format="%.1f%%"),
            "base_persistencia": st.column_config.NumberColumn("Vara difícil", format="%.1f%%"),
            "vs_persistencia": st.column_config.NumberColumn(
                "Diferencia", format="%+.1f", help="Modelo − vara difícil, en puntos"),
            "le_gana": "¿Le gana?",
        },
    )
    st.caption(
        "**La columna que importa es «Diferencia».** Elegir la vara fácil y "
        "declarar victoria es el error más común del oficio, y se comete sin "
        "mala fe: el número sube, el gráfico queda lindo y nadie pregunta "
        "contra qué se comparó."
    )
    de_donde_sale("gold.v_ml_veredicto",
                  "Las dos varas calculadas en SQL. La persistencia sale de un "
                  "LAG sobre la verdad observada: literalmente «lo de ayer».")

    # --- evolucion -----------------------------------------------------
    periodo = filtro_periodo("ml", default="30 días")
    W_PER = where_periodo("dia_predicho", periodo)

    st.markdown("###### Evolución del accuracy")
    ev = q(f"""
        SELECT dia_predicho, ventana,
               round(avg(acerto::int) * 100, 1) AS accuracy,
               count(*)                         AS n
        FROM gold.v_ml_aciertos WHERE 1=1 {W_PER}
        GROUP BY dia_predicho, ventana ORDER BY dia_predicho, ventana
    """)
    if ev.empty or ev["dia_predicho"].nunique() < 2:
        st.caption("Con un solo día no hay evolución que mirar. La serie se "
                   "arma sola: cada corrida del pipeline suma un punto.")
    else:
        fige = go.Figure()
        for W, g in ev.groupby("ventana"):
            fige.add_trace(go.Scatter(
                x=g["dia_predicho"], y=g["accuracy"], mode="lines+markers",
                name=f"ventana {int(W)}d",
                line=dict(width=2), marker=dict(size=7),
                hovertemplate="<b>ventana " + str(int(W)) + "d</b><br>"
                              "%{x|%d-%m}: %{y:.1f}%<extra></extra>"))
        # LAS DOS varas dibujadas, no una. Con una sola linea a 50% cualquier
        # serie parece estar ganando; la de arriba es la que hay que cruzar.
        if not ver.empty and pd.notna(ver["base_persistencia"].max()):
            fige.add_hline(y=float(ver["base_persistencia"].max()),
                           line_dash="dash", line_color=BAJA,
                           annotation_text="mañana = hoy · la vara que importa",
                           annotation_font=dict(size=11, color=BAJA))
        fige.add_hline(y=50, line_dash="dot", line_color=GRIS,
                       annotation_text="50% · tirar la moneda",
                       annotation_position="bottom left",
                       annotation_font=dict(size=11, color=GRIS))
        fige.update_layout(**layout(
            height=340,
            yaxis=dict(title="% de aciertos", range=[0, 100]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        ))
        st.plotly_chart(fige, use_container_width=True)
        st.caption("Un día suelto dice poco: lo que importa es si la línea "
                   "**se sostiene** por encima de la vara roja. Cruzarla una "
                   "vez y volver es ruido.")

# =========================================================================
# 2) LO QUE HAY QUE SABER PARA LEER LO DE ARRIBA — colapsado
# =========================================================================
# =========================================================================
# 2) QUE SIGNIFICA SER VOLATIL — mostrado, no explicado
# =========================================================================
# Antes esto era un expander con dos formulas adentro. La definicion es
# visual por naturaleza (dispersion de una serie, y un corte en la mediana
# de una poblacion): dibujarla con datos reales la hace evidente, y
# describirla con simbolos la hace parecer arbitraria.
st.divider()
seccion("¿Qué significa que una cripto sea «volátil»?",
        "No hay umbral fijo · son dos pasos, los dos medibles")

vol_ok = q("SELECT to_regclass('gold.v_volatilidad_diaria') IS NOT NULL AS e").iloc[0]["e"]
vdia = q("""
    SELECT * FROM gold.v_volatilidad_diaria
    WHERE fecha = (SELECT max(fecha) FROM gold.v_volatilidad_diaria)
    ORDER BY vol DESC
""") if vol_ok else pd.DataFrame()

if vdia.empty:
    st.caption("Todavía no hay suficientes snapshots por día para medir "
               "dispersión intradía. Hacen falta más de 10 por cripto.")
else:
    fecha_v = vdia["fecha"].iloc[0]
    mediana_v = float(vdia["mediana_del_dia"].iloc[0])

    # El ejemplo se elige SOLO: la mas movida del dia. Fijar una moneda a
    # mano (BTC, por decir) daria un caso aburrido la mitad de los dias.
    ej = vdia.iloc[0]
    tranqui = vdia.iloc[-1]

    st.markdown(
        f"Los dos pasos, sobre el **{fecha_larga(fecha_v)}** y con "
        f"**{len(vdia)} criptos** medidas."
    )

    p1, p2 = st.columns([1, 1])

    # ------------------------------------------------ PASO 1: la dispersion
    with p1:
        st.markdown(f"##### 1 · Cuánto se movió — *{ej['symbol']}*")
        serie = q(f"""
            SELECT snapshot_ts, current_price
            FROM gold.fact_crypto_markets
            WHERE crypto_id = '{ej['crypto_id'].replace("'", "''")}'
              AND snapshot_ts::date = DATE '{fecha_v:%Y-%m-%d}'
            ORDER BY snapshot_ts
        """)
        if serie.empty:
            st.caption("Sin snapshots para dibujar el intradía.")
        else:
            media = float(ej["precio_medio"])
            desv = float(ej["desvio"])
            figp = go.Figure()
            # La banda ±1 desvio: es literalmente lo que mide la formula.
            figp.add_hrect(y0=media - desv, y1=media + desv,
                           fillcolor=SUBE, opacity=.12, line_width=0)
            figp.add_hline(y=media, line_color=GRIS, line_dash="dot",
                           line_width=1.4)
            figp.add_trace(go.Scatter(
                x=serie["snapshot_ts"], y=serie["current_price"],
                mode="lines", line=dict(color=SUBE, width=2),
                hovertemplate="%{x|%H:%M} · $%{y:,.4f}<extra></extra>",
                name=ej["symbol"]))
            figp.update_layout(**layout(
                height=250, showlegend=False,
                yaxis=dict(title="Precio (US$)", showgrid=True,
                           gridcolor="rgba(128,128,128,.15)"),
                xaxis=dict(title=None, showgrid=False),
                margin=dict(l=0, r=0, t=6, b=0),
            ))
            st.plotly_chart(figp, use_container_width=True)
            st.markdown(
                f"La línea punteada es el **promedio del día** "
                f"(${media:,.4f}). La banda azul es **un desvío** "
                f"(±${desv:,.4f}).\n\n"
                f"La volatilidad es esa banda medida **en porcentaje del "
                f"promedio**:\n\n"
                f"`{desv:,.4f} ÷ {media:,.4f} × 100 = `**`{ej['vol']:.3f}%`**\n\n"
                f"Se divide por el promedio para que sea **comparable entre "
                f"monedas**: sin eso, Bitcoin a US$ 121.000 «se movería» miles "
                f"de veces más que una moneda de US$ 0,30, solo por la escala."
            )
            st.caption(
                f"Esa banda se calculó con **{int(ej['snapshots'])} snapshots** "
                "de ese día. Con el cierre diario — un número — no existiría: "
                "un solo punto no tiene dispersión."
            )

    # ------------------------------------------- PASO 2: la vara del mercado
    with p2:
        st.markdown("##### 2 · Contra qué se compara — *la mediana del día*")
        top = vdia.head(26)
        figv = go.Figure(go.Bar(
            x=top["symbol"], y=top["vol"],
            marker_color=[SUBE if a else GRIS for a in top["alta_vol"]],
            customdata=top[["name", "alta_vol"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b><br>vol %{y:.3f}%<extra></extra>",
        ))
        figv.add_hline(y=mediana_v, line_color=BAJA, line_dash="dash",
                       line_width=2,
                       annotation_text=f"mediana del día: {mediana_v:.3f}%",
                       annotation_font=dict(size=11, color=BAJA))
        figv.update_layout(**layout(
            height=250,
            yaxis=dict(title="Volatilidad del día (%)", showgrid=True,
                       gridcolor="rgba(128,128,128,.15)"),
            xaxis=dict(title=None, showgrid=False, tickangle=-60),
            margin=dict(l=0, r=0, t=6, b=0),
        ))
        st.plotly_chart(figv, use_container_width=True)
        st.markdown(
            f"Cada barra es una cripto. La línea roja es la **mediana de todas**: "
            f"{mediana_v:.3f}%.\n\n"
            f"**Azul = por encima = «de las movidas».** Gris = por debajo.\n\n"
            f"Por eso «volátil» es **relativo**, no absoluto: la vara la pone "
            f"**el mercado de ese día**. En un día de pánico general no son "
            f"todas volátiles — siempre hay una mitad arriba y una abajo."
        )
        st.caption(
            f"Hoy {int(vdia['alta_vol'].sum())} de {len(vdia)} quedaron del "
            f"lado alto. Que sea **siempre la mitad** es lo que hace que "
            "adivinar sin mirar nada acierte 50% — y por eso ese 50% no es "
            "una vara que valga la pena ganarle."
        )

    # ------------------------------------------ PASO 3: y esto como se PREDICE
    st.markdown("##### 3 · Y entonces, ¿qué predice el modelo?")
    pas = q("""
        SELECT v.symbol, v.fecha, v.vol, v.alta_vol
        FROM gold.v_volatilidad_diaria v
        WHERE v.fecha >= (SELECT max(fecha) - 6 FROM gold.v_volatilidad_diaria)
        ORDER BY v.symbol, v.fecha
    """)
    cA, cB = st.columns([1, 1])
    with cA:
        st.markdown(
            "El modelo **no** adivina el precio. Contesta una pregunta de "
            "sí o no, una por cripto, una vez por día:\n\n"
            "> *«¿esta moneda va a estar en la mitad movida **mañana**?»*\n\n"
            "Lo que mira para contestar son las features del **día de hoy** "
            "(y de los últimos W días): su vol de hoy, su rango de hoy, su "
            "volumen relativo, cuánto se despega de su propio promedio. "
            "Ninguna feature usa datos de mañana — eso sería hacer trampa.\n\n"
            "Y la etiqueta correcta —la que se usa para corregir— es "
            "**exactamente el paso 2 aplicado a mañana**: se espera a que "
            "mañana pase, se calcula la vol de todas, se traza la mediana y "
            "se ve de qué lado cayó cada una."
        )
        st.code(
            "-- lo que SABE hoy (features)      -- lo que TIENE que adivinar\n"
            "vol_hoy, rango_hoy, volumen_rel   →   alta_vol de MAÑANA\n"
            "\n"
            "-- y mañana, la corrección:\n"
            "acerto = (predijo_alta_vol = alta_vol_real)",
            language="sql",
        )
    with cB:
        # Por que es dificil: se muestra la SERIE de la etiqueta para unas
        # pocas monedas. Las que son siempre azul o siempre gris son gratis;
        # las que alternan son donde esta el merito. Eso explica, sin
        # estadistica, por que la persistencia es una vara tan dura.
        if not pas.empty and pas["fecha"].nunique() >= 2:
            simbolos = list(vdia.head(14)["symbol"])
            sub_p = pas[pas["symbol"].isin(simbolos)]
            piv = sub_p.pivot_table(index="symbol", columns="fecha",
                                    values="alta_vol", aggfunc="max")
            # ordenar: primero las que mas alternan
            alterna = piv.apply(lambda r: r.dropna().diff().abs().sum(), axis=1)
            piv = piv.loc[alterna.sort_values(ascending=False).index]
            figh = go.Figure(go.Heatmap(
                z=piv.values, x=[f"{d:%d-%m}" for d in piv.columns],
                y=list(piv.index), zmin=0, zmax=1,
                colorscale=[[0, "#2a3240"], [1, SUBE]], showscale=False,
                xgap=2, ygap=2,
                hovertemplate="%{y} · %{x}<extra></extra>",
            ))
            figh.update_layout(**layout(
                height=300,
                xaxis=dict(title=None, showgrid=False),
                yaxis=dict(title=None, showgrid=False),
                margin=dict(l=0, r=0, t=6, b=0),
            ))
            st.plotly_chart(figh, use_container_width=True)
            st.caption(
                "**Azul = fue de las movidas ese día.** Ordenadas de la que "
                "más alterna a la que menos. Mirá las de abajo: filas casi "
                "enteras de un solo color. Esas son **gratis de acertar** — "
                "y son las que inflan el accuracy.<br><br>"
                "Ahí se ve por qué *«mañana se repite lo de hoy»* es tan "
                "difícil de superar: para la mayoría de las filas, **es "
                "verdad**. El mérito del modelo está solo en las de arriba.",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Hace falta un día más para mostrar la serie de "
                       "etiquetas.")

    de_donde_sale("gold.v_volatilidad_diaria",
                  "La definición completa en una vista: la dispersión de los "
                  "snapshots de cada día y la mediana con la que se corta. "
                  "v_ml_aciertos LEE de acá, así que el examen se corrige con "
                  "la misma vara con la que se armó la pregunta.")

if hay_veredicto and not ver.empty:
    with st.expander("🎯 ¿En qué criptos acierta?"):
        pormoneda = q(f"""
            SELECT COALESCE(symbol, crypto_id)                      AS cripto,
                   count(*)                                         AS predicciones,
                   sum(acerto::int)                                 AS aciertos,
                   round(avg(acerto::int) * 100, 1)                 AS accuracy,
                   round(avg(realmente_alta_vol::numeric) * 100, 1) AS pct_fue_volatil
            FROM gold.v_ml_aciertos WHERE 1=1 {W_PER}
            GROUP BY 1 HAVING count(*) >= 2
            ORDER BY accuracy DESC, predicciones DESC
        """)
        if pormoneda.empty:
            st.caption("Todavía no hay suficientes predicciones por cripto "
                       "para abrir el detalle.")
        else:
            # Las "faciles" son las que nunca cambian de lado: su respuesta es
            # siempre la misma, asi que acertarlas no prueba nada. Separarlas
            # es lo que revela donde esta el merito real.
            faciles = pormoneda[(pormoneda["pct_fue_volatil"] >= 90)
                                | (pormoneda["pct_fue_volatil"] <= 10)]
            alternan = pormoneda.drop(faciles.index)
            cA, cB = st.columns(2)
            cA.metric("Criptos que nunca cambian de lado", len(faciles),
                      f"{len(faciles) / len(pormoneda) * 100:.0f}% del total",
                      delta_color="off")
            if not alternan.empty:
                cB.metric("Accuracy en las que SÍ alternan",
                          f"{alternan['accuracy'].mean():.1f} %",
                          "acá está el mérito real", delta_color="off")
            st.dataframe(
                pormoneda, hide_index=True, use_container_width=True, height=300,
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
            st.caption(
                "La última columna dice cuántas veces esa cripto fue "
                "efectivamente de las movidas. Una que **siempre** lo es (o "
                "nunca) es gratis de acertar: el mérito está en las que "
                "alternan. Ojo también con el tamaño de muestra — las ~50 "
                "predicciones de un mismo día comparten el régimen de mercado "
                "de esa jornada, así que valen menos que 50 casos "
                "independientes. El número que manda es **Días**."
            )

# =========================================================================
# 3) LA MAQUINARIA — todo lo de MLOps, abajo y colapsado
# =========================================================================
st.divider()
seccion("La maquinaria", "Cómo está hecho: ABT → MLflow → champion → predicciones")

with st.expander("📦 La ABT · el dataset que consume el modelo"):
    try:
        abt = q("SELECT * FROM gold.gold_abt_crypto")
    except Exception:
        abt = pd.DataFrame()

    if abt.empty:
        st.info("🕐 **`gold.gold_abt_crypto` todavía no tiene datos.** La "
                "construye `crypto_gold` en cada corrida (cada 15 minutos).")
    else:
        feats = [c for c in abt.columns if not c.startswith("_")]
        cols = st.columns(4)
        cols[0].markdown(kpi("Filas", f"{len(abt)}",
                             foot="Una por activo. Grano de la ABT: la 'unidad' "
                                  "que el modelo predice."), unsafe_allow_html=True)
        cols[1].markdown(kpi("Features", f"{len(feats)}",
                             foot="Ya calculadas en SQL: el modelo no "
                                  "transforma, solo consume."), unsafe_allow_html=True)
        cols[2].markdown(kpi("Días de historia", f"{dias_hoy}",
                             foot=f"Para una validación temporal concluyente "
                                  f"hacen falta ~{MIN_DIAS}."), unsafe_allow_html=True)
        # Contadas de la ABT, no escritas a mano: antes decia "3" como string
        # literal y el dia que la ABT sumara una categorica el tablero iba a
        # seguir diciendo 3, sin que nada fallara.
        categoricas = [c for c in abt.columns
                       if abt[c].dtype == "object" and abt[c].nunique() <= 8
                       and c not in ("crypto_id", "symbol", "name")]
        cols[3].markdown(kpi("Categóricas derivadas", f"{len(categoricas)}",
                             foot=(" · ".join(categoricas) if categoricas else "ninguna")
                                  + " — bucketizadas con CASE WHEN en SQL, no en pandas."),
                         unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame({"feature": feats,
                          "tipo": [str(abt[c].dtype) for c in feats],
                          "nulos %": [f"{abt[c].isna().mean() * 100:.0f}%" for c in feats]}),
            hide_index=True, use_container_width=True, height=300,
        )

with st.expander(f"🧪 Los runs de MLflow · experimento `{EXPERIMENTO}`"):
    if not vivo:
        st.info("🔌 **El tracking server no responde.** Levantalo con "
                "`docker compose up -d mlflow` y recargá esta página.")
    else:
        exps = mlflow_post("experiments/search", {"max_results": 50}).get("experiments", [])
        exp = next((e for e in exps if e["name"] == EXPERIMENTO), None)

        if exp is None:
            st.info(f"📋 **El experimento `{EXPERIMENTO}` todavía no existe.** "
                    "Se crea la primera vez que el notebook de clase06 loguea un run.")
        else:
            runs = mlflow_post("runs/search", {
                "experiment_ids": [exp["experiment_id"]],
                "max_results": 100,
                "order_by": ["attributes.start_time DESC"],
            }).get("runs", [])

            if not runs:
                st.info("📋 **El experimento existe pero no tiene runs todavía.**")
            else:
                filas = []
                for r in runs:
                    info, data = r.get("info", {}), r.get("data", {})
                    m = {x["key"]: x["value"] for x in data.get("metrics", [])}
                    p = {x["key"]: x["value"] for x in data.get("params", [])}
                    tags = {x["key"]: x["value"] for x in data.get("tags", [])}
                    filas.append({
                        "run": tags.get("mlflow.runName", info.get("run_id", "")[:8]),
                        # Cuanta historia miraba ese modelo. Sin esta columna,
                        # dos runs de ventanas distintas se ven identicos.
                        "ventana": (tags["ventana"] + "d" if "ventana" in tags
                                    else (p["ventana_dias"] + "d" if "ventana_dias" in p else "-")),
                        # ------------------------------------------------
                        # LOS NOMBRES REALES de las metricas que loguea la
                        # notebook. Antes esto pedia "accuracy",
                        # "balanced_accuracy" y "baseline_accuracy", que NO
                        # existen: las claves son accuracy_wf,
                        # balanced_accuracy_wf y acc_baseline_persistencia.
                        # Resultado: las cuatro columnas salian vacias y el
                        # grafico de abajo nunca se dibujaba, porque el
                        # dropna() dejaba el DataFrame en cero filas. No
                        # fallaba: se veia como si no hubiera runs.
                        # ------------------------------------------------
                        "modelo": p.get("model_type", p.get("modelo", "—")),
                        "accuracy": m.get("accuracy_wf", m.get("accuracy")),
                        "balanced": m.get("balanced_accuracy_wf", m.get("balanced_accuracy")),
                        "persistencia": m.get("acc_baseline_persistencia"),
                        "vs_persistencia": m.get("vs_persistencia"),
                        "inicio": pd.to_datetime(info.get("start_time"), unit="ms"),
                    })
                df = pd.DataFrame(filas)

                st.dataframe(
                    df, hide_index=True, use_container_width=True, height=300,
                    column_config={
                        "run": "Run", "ventana": "Ventana", "modelo": "Modelo",
                        "accuracy": st.column_config.NumberColumn("Accuracy", format="%.3f"),
                        "balanced": st.column_config.NumberColumn("Balanced", format="%.3f"),
                        "persistencia": st.column_config.NumberColumn(
                            "Vara difícil", format="%.3f"),
                        "vs_persistencia": st.column_config.NumberColumn(
                            "Diferencia", format="%+.3f"),
                        "inicio": st.column_config.DatetimeColumn("Cuándo", format="DD-MM HH:mm"),
                    },
                )

                comp = df.dropna(subset=["accuracy"])
                if not comp.empty:
                    base = comp["persistencia"].dropna().max()
                    figm = go.Figure(go.Bar(
                        x=comp["run"], y=comp["accuracy"],
                        marker=dict(color=[SUBE if (pd.isna(base) or a >= base) else BAJA
                                           for a in comp["accuracy"]]),
                        text=[f"{a:.3f}" for a in comp["accuracy"]],
                        textposition="outside",
                        hovertemplate="%{x}: %{y:.3f}<extra></extra>",
                    ))
                    if pd.notna(base):
                        figm.add_hline(y=base, line_color=BAJA, line_dash="dash",
                                       line_width=1.5,
                                       annotation_text=f"vara difícil: {base:.3f}",
                                       annotation_position="top left",
                                       annotation_font=dict(size=11, color=BAJA))
                    figm.update_layout(height=300, bargap=0.4, **{
                        k: v for k, v in PLOTLY.items() if k != "xaxis"},
                        xaxis=dict(tickangle=-45, showgrid=False, title=None))
                    st.plotly_chart(figm, use_container_width=True)
                    st.caption(
                        "Cada barra es un run del model zoo. **Azul = le gana a "
                        "la vara difícil, rojo = no.** Un modelo que no le gana "
                        "a *«mañana pasa lo mismo que hoy»* no aporta nada, por "
                        "más sofisticado que sea."
                    )

with st.expander("🏆 El champion · el modelo en producción"):
    if not vivo:
        st.info("🔌 El tracking server no responde.")
    else:
        modelos = mlflow_get("registered-models/search").get("registered_models", [])
        if not modelos:
            st.info("🏆 **No hay ningún modelo registrado todavía.** El champion "
                    "se promueve desde el notebook cuando un candidato le gana "
                    "al baseline.")
        else:
            for m in modelos:
                versiones = m.get("latest_versions", [])
                v = versiones[0] if versiones else {}
                st.markdown(
                    f"<div class='kpi'><div class='lab'>Modelo registrado</div>"
                    f"<div class='val' style='font-size:19px'>{m['name']}</div>"
                    f"<div class='foot'>Versión <b>{v.get('version', '—')}</b> · "
                    f"etapa <b>{v.get('current_stage', 'None')}</b><br>"
                    f"El scoring batch (<code>dag_crypto_ml</code>) lee esta "
                    f"versión: cambiar el champion en el Registry cambia lo que "
                    f"predice el pipeline, sin tocar código.</div></div>",
                    unsafe_allow_html=True,
                )

with st.expander("🔮 Las predicciones · `gold.predicciones`"):
    existe_pred = q("SELECT to_regclass('gold.predicciones') IS NOT NULL AS e").iloc[0]["e"]
    if not existe_pred:
        # Por que esta vacio NO es "todavia no corrio": el DAG corre desde hace
        # dias. Corre, no encuentra champion y saltea. Decirlo cambia la accion
        # del que mira: no es esperar, es promover un modelo.
        corridas = estado_pipeline(("crypto_ml",))
        veces = int(corridas.iloc[0]["corridas"]) if not corridas.empty else 0
        detalle = (
            f"El DAG <code>crypto_ml</code> ya corrió <b>{veces} veces</b> y "
            "terminó OK todas: no falló, <b>salteó</b>. Sin un modelo con alias "
            "<code>@champion</code> en el Registry no tiene con qué scorear, así "
            "que loguea <code>[SKIP]</code> y sale limpio.<br><br>"
            "Para que aparezcan predicciones hay que <b>promover un champion</b> "
            "desde el notebook de la clase 06 — esa decisión es humana a "
            "propósito y no se automatiza."
            if veces else
            "Cuando haya champion y predicciones, acá van a aparecer la señal "
            "del día por activo y el acierto acumulado contra lo que pasó."
        )
        aviso(
            "<b>La tabla de predicciones todavía no existe.</b> La escribe el DAG "
            "<code>dag_crypto_ml</code>, que no corre por reloj sino <b>por "
            "dato</b>: <code>schedule=[GOLD_ABT]</code> — se despierta cuando la "
            f"ABT se actualiza.<br><br>{detalle}",
            "🔮",
        )
    else:
        pred = q("""
            SELECT * FROM gold.predicciones
            ORDER BY fecha_features DESC, crypto_id
            LIMIT 200
        """)
        if pred.empty:
            st.info("La tabla existe pero está vacía — esperá la próxima "
                    "corrida de `dag_crypto_ml`.")
        else:
            st.dataframe(pred, hide_index=True, use_container_width=True, height=320)

de_donde_sale("gold.v_series_diaria",
              "La fuente de las features: el cierre de cada día por cripto, con "
              "el retorno ya calculado. El modelo no ve el dato crudo, ve esto.")
