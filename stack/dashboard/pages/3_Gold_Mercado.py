"""
Mercado ahora — ¿Cómo está el mercado crypto en este momento?

Toda la lógica de negocio vive en la capa semántica de Gold
(gold.v_kpis_mercado, gold.v_ultimo_snapshot): esta página NO calcula KPIs,
solo los muestra. Si un número está mal, se corrige en la vista SQL — una
sola vez, para todos los consumidores.
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from db import frescura, run_query
from theme import (aplicar_tema, encabezado, pill, hero, kpi, seccion, tabla,
                   de_donde_sale, frescura_pill,
                   PLOTLY, SUBE, BAJA, GRIS)

aplicar_tema("Gold · Mercado", "🥇")


# run_query ya viene cacheado desde db.py (ttl=60). Este alias queda solo
# por comodidad de lectura: `q(...)` es mas corto dentro de las paginas.
q = run_query


# --- datos -----------------------------------------------------------------
try:
    kpis = q("SELECT * FROM gold.v_kpis_mercado")
    ult = q("""
        SELECT name, symbol, current_price, price_change_percentage_24h,
               market_cap, market_cap_rank, snapshot_ts
        FROM gold.v_ultimo_snapshot
        ORDER BY market_cap_rank
    """)
    # v_global_serie es la serie macro a nivel SNAPSHOT (cada 15 min).
    # Antes esto leia gold.fact_global_market directo y dibujaba 1 punto por
    # dia: un sparkline de 3 puntos. La fact ahora guarda el grano fino y la
    # vista lo expone -- el dashboard lee vistas, no tablas.
    serie_mcap = q("""
        SELECT snapshot_ts, total_market_cap_usd
        FROM gold.v_global_serie ORDER BY snapshot_ts
    """)
except Exception:
    encabezado("🥇 Gold · Mercado", "Capa Gold")
    st.info("🕐 **Gold todavía no tiene datos.** El pipeline corre solo cada 15 minutos "
            "(bronze cada 15 min, y silver/gold en cadena detrás). En unos minutos esta página se llena sola.")
    st.stop()

if kpis.empty or ult.empty:
    encabezado("🥇 Gold · Mercado", "Capa Gold")
    st.info("🕐 **Las vistas existen pero aún no tienen filas.** Esperá la próxima corrida de `crypto_gold`.")
    st.stop()

k = kpis.iloc[0]
ts = pd.to_datetime(ult.iloc[0]["snapshot_ts"])
# Una sola definicion de frescura para todo el dashboard (db.frescura +
# theme.frescura_pill). Antes este bloque estaba copiado en la pagina de
# Bronze con los mismos umbrales y otras etiquetas: el mismo estado se
# llamaba distinto en dos pantallas del mismo tablero.
estado = frescura_pill(frescura("gold", "fact_crypto_markets", "snapshot_ts"))

# --- ticker ----------------------------------------------------------------
from theme import ticker  # noqa: E402
ticker([(r.symbol,
         f"{r.current_price:,.2f}" if r.current_price >= 1 else f"{r.current_price:,.4f}",
         r.price_change_percentage_24h or 0)
        for r in ult.head(18).itertuples()])

encabezado("🥇 Gold · Mercado",
           "KPIs del último snapshot · <code>gold.v_kpis_mercado</code>", estado)

# --- hero ------------------------------------------------------------------
hero(
    "Capitalización total del mercado",
    f"US$ {k['total_market_cap_usd'] / 1e12:,.3f} B".replace(",", "·").replace(".", ",").replace("·", "."),
    k["mcap_delta_pct"],
    list(serie_mcap["total_market_cap_usd"]) if not serie_mcap.empty else [],
    "El delta compara el cierre de hoy contra el de ayer. Se calcula en SQL, "
    "dentro de la vista — el tablero solo lo muestra.",
)

# --- KPIs ------------------------------------------------------------------
# Se LEE de la vista, no se calcula acá: el docstring de esta página dice que no
# calcula KPIs, y hasta recién lo hacía igual. Ahora `activos_en_alza_24h` se
# define en gold.v_kpis_mercado, junto al resto de los KPIs de mercado.
suben = int(k["activos_en_alza_24h"])
total_activos = int(k["activos_totales"])
cols = st.columns(4)
datos_kpi = [
    ("Volumen 24 h", f"US$ {k['total_volume_usd'] / 1e9:,.1f} B", k["vol_delta_pct"], "Cuánto se negoció en el día."),
    ("Dominancia BTC", f"{k['btc_dominance']:.1f} %", k["btc_dom_delta"], "Qué porción del mercado es Bitcoin."),
    ("Dominancia ETH", f"{k['eth_dominance']:.1f} %", k["eth_dom_delta"], "Ídem para Ethereum."),
    ("En alza (24 h)", f"{suben} / {total_activos}", None,
     "Ventana móvil de 24 h, según la API. La página de Análisis mide otra cosa: "
     "cierre contra cierre del día anterior."),
]
for col, (lab, val, chg, foot) in zip(cols, datos_kpi):
    col.markdown(kpi(lab, val, chg, foot=foot), unsafe_allow_html=True)

if k["mcap_delta_pct"] is None:
    st.caption("ℹ️ Los deltas aparecen con **2+ días** de historia — el pipeline recién arranca a acumular.")

# --- mapa del mercado ------------------------------------------------------
seccion("Mapa del mercado", "Área = capitalización · color = variación 24 h")

top = ult.head(30).copy()
top["chg"] = top["price_change_percentage_24h"].fillna(0)
fig = go.Figure(go.Treemap(
    labels=top["symbol"],
    parents=[""] * len(top),
    values=top["market_cap"],
    customdata=top[["name", "chg"]],
    marker=dict(
        colors=top["chg"], colorscale=[[0, "#e34948"], [.5, "#8a8987"], [1, "#2a78d6"]],
        cmid=0, cmin=-8, cmax=8, line=dict(width=2, color="rgba(0,0,0,0)"),
    ),
    texttemplate="<b>%{label}</b><br>%{customdata[1]:+.1f}%",
    hovertemplate="<b>%{customdata[0]}</b><br>Capitalización: $%{value:,.0f}"
                  "<br>24 h: %{customdata[1]:+.2f}%<extra></extra>",
    textfont=dict(family="IBM Plex Mono, monospace", size=13),
    tiling=dict(pad=2),
))
fig.update_layout(height=400, **{k_: v for k_, v in PLOTLY.items() if k_ not in ("xaxis", "yaxis")})
st.plotly_chart(fig, use_container_width=True)


# --- ganadores y perdedores ------------------------------------------------
seccion("Ganadores y perdedores", "Las 5 mayores subas y bajas de las últimas 24 h")
sub = ult.dropna(subset=["price_change_percentage_24h"]).sort_values("price_change_percentage_24h")
movers = pd.concat([sub.head(5), sub.tail(5)]).drop_duplicates(subset="symbol")
figm = go.Figure(go.Bar(
    x=movers["price_change_percentage_24h"], y=movers["name"], orientation="h",
    marker=dict(color=[SUBE if v >= 0 else BAJA for v in movers["price_change_percentage_24h"]]),
    text=[f"{v:+.1f}%" for v in movers["price_change_percentage_24h"]], textposition="outside",
    hovertemplate="<b>%{y}</b><br>24 h: %{x:+.2f}%<extra></extra>",
))
figm.add_vline(x=0, line_color=GRIS, line_width=1)
figm.update_layout(height=330, bargap=0.35,
                   xaxis=dict(title="Variación 24 h (%)", showgrid=True,
                              gridcolor="rgba(128,128,128,.15)", zeroline=False),
                   **{k: v for k, v in PLOTLY.items() if k != "xaxis"})
st.plotly_chart(figm, use_container_width=True)
st.caption("🔵 sube · 🔴 baja — el signo va escrito en la etiqueta: la lectura no depende del color.")

# --- ranking ---------------------------------------------------------------
seccion("Ranking", "Último snapshot de cada activo")
filas = "".join(
    f"<tr><td>{int(r.market_cap_rank)}</td>"
    f"<td>{r.name}<span class='sym'>{r.symbol}</span></td>"
    f"<td>US$ {r.current_price:,.2f}</td>"
    f"<td class='{'u' if (r.price_change_percentage_24h or 0) >= 0 else 'd'}'>"
    f"{(r.price_change_percentage_24h or 0):+.2f}%</td>"
    f"<td>US$ {r.market_cap / 1e9:,.1f} B"
    f"<span style='display:inline-block;height:7px;border-radius:2px;background:{SUBE};"
    f"opacity:.7;vertical-align:middle;margin-left:9px;"
    f"width:{max(3, r.market_cap / ult['market_cap'].max() * 72):.0f}px'></span></td></tr>"
    for r in ult.itertuples()
)
tabla(filas, ["#", "Activo", "Precio", "24 h", "Capitalización"])

de_donde_sale("gold.v_kpis_mercado",
              "Los KPIs de arriba, con sus deltas contra el día anterior ya "
              "calculados en SQL. La página no resta nada: lee.")
de_donde_sale("gold.v_ultimo_snapshot",
              "La foto de cada cripto: el DISTINCT ON que se queda con el "
              "snapshot más reciente de cada una.")
st.caption(f"Último snapshot: **{ts:%Y-%m-%d %H:%M} UTC** · "
           f"{int(k['active_cryptocurrencies']):,} criptos activas en {int(k['markets']):,} mercados".replace(",", "."))
