"""
Velas diarias — ¿cómo se movió cada activo, día por día?

Una vela resume TODO un día en cuatro números: apertura, máximo, mínimo y
cierre (OHLC). El cuerpo es el recorrido apertura→cierre; las mechas, hasta
dónde llegó el precio dentro del día.

De dónde sale: gold.v_ohlc_diario agrupa los ~96 snapshots de cada día.
👉 Esto SOLO es posible porque la fact guarda `snapshot_ts`. Si Gold tuviera
una fila por día, el máximo y el mínimo no existirían en ningún lado.
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from db import run_query
from theme import (aplicar_tema, encabezado, seccion, aviso,
                   de_donde_sale, filtro_periodo, where_periodo,
                   PLOTLY, SUBE, BAJA, GRIS)

aplicar_tema("Gold · Velas", "🥇")


# run_query ya viene cacheado desde db.py (ttl=60). Este alias queda solo
# por comodidad de lectura: `q(...)` es mas corto dentro de las paginas.
q = run_query


encabezado("🥇 Gold · Velas",
           "Apertura · máximo · mínimo · cierre · <code>gold.v_ohlc_diario</code>")

# El filtro va en UNA fila, arriba de todo lo que gobierna.
periodo = filtro_periodo("velas")
st.caption("Las velas se arman agrupando los snapshots del día · mostrando **" + periodo["etiqueta"] + "**")

try:
    activos = q("""
        SELECT o.crypto_id, o.name, o.symbol, max(u.market_cap_rank) AS rnk
        FROM gold.v_ohlc_diario o
        JOIN gold.v_ultimo_snapshot u USING (crypto_id)
        GROUP BY 1, 2, 3
        ORDER BY rnk
        LIMIT 25
    """)
except Exception:
    st.info("🕐 **Gold todavía no tiene datos.** El pipeline corre cada 15 minutos; volvé en un rato.")
    st.stop()

if activos.empty:
    st.info("🕐 Sin datos en Gold todavía — esperá la próxima corrida de `crypto_gold`.")
    st.stop()

nombre_de = dict(zip(activos["crypto_id"], activos["name"]))
elegido_nombre = st.selectbox("Activo", options=list(activos["name"]), index=0)
cid = next(k for k, v in nombre_de.items() if v == elegido_nombre)

# El crypto_id sale de un selectbox armado con datos de la propia base, asi
# que no es entrada de usuario libre -- pero se escapa igual: la regla es que
# NUNCA se concatena texto en SQL, no "salvo cuando creemos que es seguro".
# (La pagina de Analisis ya lo hacia asi; acá faltaba.)
velas = q(f"""
    SELECT fecha, apertura, maximo, minimo, cierre, volumen, snapshots, rango_pct
    FROM gold.v_ohlc_diario
    WHERE crypto_id = '{cid.replace("'", "''")}'
      {where_periodo("fecha", periodo)}
    ORDER BY fecha
""")

if velas.empty:
    st.info("Sin velas para este activo todavía.")
    st.stop()

ndias = len(velas)
ult = velas.iloc[-1]

# --- Lectura OHLC del último día ------------------------------------------
k = st.columns(5)
k[0].metric("Apertura", f"${ult['apertura']:,.2f}")
k[1].metric("Máximo", f"${ult['maximo']:,.2f}")
k[2].metric("Mínimo", f"${ult['minimo']:,.2f}")
var = (ult["cierre"] / ult["apertura"] - 1) * 100 if ult["apertura"] else 0
k[3].metric("Cierre", f"${ult['cierre']:,.2f}", f"{var:+.2f}% en el día")
k[4].metric("Rango del día", f"{ult['rango_pct']:.2f}%",
            help="(máximo − mínimo) / cierre. Proxy de volatilidad que ya sirve con un solo día.")

# --- Velas -----------------------------------------------------------------
fig = go.Figure(go.Candlestick(
    x=velas["fecha"],
    open=velas["apertura"], high=velas["maximo"],
    low=velas["minimo"], close=velas["cierre"],
    increasing=dict(line=dict(color=SUBE, width=1.5), fillcolor=SUBE),
    decreasing=dict(line=dict(color=BAJA, width=1.5), fillcolor=BAJA),
    name="OHLC",
    hovertext=[f"{s} snapshots" for s in velas["snapshots"]],
))

# Media móvil 5 días: solo cuando hay suficientes velas para que signifique algo
if ndias >= 5:
    fig.add_trace(go.Scatter(
        x=velas["fecha"], y=velas["cierre"].rolling(5).mean(),
        mode="lines", name="Media móvil 5d",
        line=dict(color=GRIS, width=1.6, dash="dot"),
    ))

fig.update_layout(
    height=420, margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(rangeslider=dict(visible=False), title=None, showgrid=False),
    yaxis=dict(title=None, showgrid=True, gridcolor="rgba(128,128,128,.15)", side="right"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

# --- Honestidad sobre la historia disponible -------------------------------
if ndias < 5:
    st.info(
        f"📅 **{ndias} {'día' if ndias == 1 else 'días'} de historia.** Cada vela resume un día "
        f"(el último se armó con {int(ult['snapshots'])} snapshots). La media móvil aparece a partir "
        "de 5 velas — el gráfico se va poblando solo a medida que corre el pipeline."
    )
else:
    st.caption(f"📅 {ndias} días acumulados · última vela armada con {int(ult['snapshots'])} snapshots.")

# --- Volumen ---------------------------------------------------------------
seccion("Volumen negociado")
figv = go.Figure(go.Bar(
    x=velas["fecha"], y=velas["volumen"],
    marker=dict(color=[SUBE if c >= a else BAJA
                       for a, c in zip(velas["apertura"], velas["cierre"])]),
    hovertemplate="%{x|%d-%b}: $%{y:,.0f}<extra></extra>",
))
figv.update_layout(
    height=180, margin=dict(l=0, r=0, t=6, b=0),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,.15)", title=None, side="right"),
    xaxis=dict(title=None, showgrid=False),
    bargap=0.45,
)
st.plotly_chart(figv, use_container_width=True)

with st.expander("Ver la tabla OHLC"):
    st.dataframe(
        velas, hide_index=True, use_container_width=True,
        column_config={
            "fecha": "Fecha",
            "apertura": st.column_config.NumberColumn("Apertura", format="$%.2f"),
            "maximo": st.column_config.NumberColumn("Máximo", format="$%.2f"),
            "minimo": st.column_config.NumberColumn("Mínimo", format="$%.2f"),
            "cierre": st.column_config.NumberColumn("Cierre", format="$%.2f"),
            "volumen": st.column_config.NumberColumn("Volumen", format="compact"),
            "snapshots": st.column_config.NumberColumn("Snapshots", help="Cuántas mediciones formaron esta vela"),
            "rango_pct": st.column_config.NumberColumn("Rango %", format="%.2f%%"),
        },
    )

de_donde_sale("gold.v_ohlc_diario",
              "La vela sale de AGRUPAR los ~96 snapshots del día. Si la fact "
              "guardara una fila por día, no habría ni máximo ni mínimo: el "
              "grano fino es lo que hace posible este gráfico.")
