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
                   filtro_categoria, where_categoria, aviso, layout,
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
    # El MISMO 24 h, calculado por nosotros: cierre contra cierre sobre
    # v_ohlc_diario. La API manda el suyo ya masticado; este sale de los
    # hechos que viene juntando el pipeline.
    doble = q("""
        SELECT symbol, name, categoria, market_cap_rank, current_price,
               market_cap, var_api_pct, var_gold_pct, brecha_pts, fecha_cierre
        FROM gold.v_mercado_24h
        ORDER BY market_cap_rank
    """)
    # Donde cae el valor de hoy dentro de la serie acumulada.
    ctx = q("SELECT * FROM gold.v_mercado_contexto")
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

# Esta es la UNICA pagina sin filtro de periodo, y hasta recien eso no estaba
# dicho en ningun lado. No es un olvido: es una foto, no una serie. Pero
# "foto" tampoco es del todo cierto -- dos bloques miran hacia atras -- y
# quien la lee tiene derecho a saber cual es cual.
aviso(
    "<b>Esta página no tiene filtro de período, a propósito: es la foto del "
    "último snapshot</b>, no una serie. El ticker, el mapa y el ranking son "
    "esa foto.<br><br>"
    "Dos cosas sí miran hacia atrás, y conviene tenerlas separadas: los "
    "<b>deltas</b> comparan contra el cierre de <b>ayer</b>, y el "
    "<b>sparkline</b> del número grande dibuja <b>toda la historia "
    "acumulada</b>. Para recorrer el tiempo están Velas y Análisis.",
    "📸",
)

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


def puesto(metrica: str) -> str:
    """"El 2do mas alto de 9 dias" -- la frase que la API no puede decir.

    CoinGecko devuelve el valor de ahora y nada mas: no guarda TU historia.
    Ubicar ese valor dentro de la serie acumulada solo es posible porque el
    pipeline viene escribiendo un cierre por dia desde que arranco. Es
    exactamente lo que agrega tener warehouse en vez de consumir la API.
    """
    if ctx.empty:
        return ""
    f = ctx[ctx["metrica"] == metrica]
    if f.empty or pd.isna(f.iloc[0]["puesto"]):
        return ""
    pos, dias = int(f.iloc[0]["puesto"]), int(f.iloc[0]["dias"])
    if dias < 2:
        return ""
    orden = {1: "el más alto", 2: "el 2º más alto", 3: "el 3º más alto"}
    return (f"<br><b style='color:var(--ink-2)'>{orden.get(pos, f'el {pos}º más alto')} "
            f"de los {dias} días acumulados.</b> Eso no está en la API: "
            "sale de tu serie.")


# Las criptas en alza se recuentan con el dato PROPIO. No es cosmetico: como
# los dos numeros no coinciden, el conteo tampoco -- y que dos partes de la
# misma pantalla cuenten distinto es justo el lio que esta pagina explica.
suben_gold = int((doble["var_gold_pct"] > 0).sum()) if not doble.empty else 0
medibles = int(doble["var_gold_pct"].notna().sum()) if not doble.empty else 0

cols = st.columns(4)
datos_kpi = [
    ("Volumen 24 h", f"US$ {k['total_volume_usd'] / 1e9:,.1f} B", k["vol_delta_pct"],
     "Cuánto se negoció en el día." + puesto("volumen")),
    ("Dominancia BTC", f"{k['btc_dominance']:.1f} %", k["btc_dom_delta"],
     "Qué porción del mercado es Bitcoin." + puesto("dominancia_btc")),
    ("Dominancia ETH", f"{k['eth_dominance']:.1f} %", k["eth_dom_delta"],
     "Ídem para Ethereum."),
    ("En alza · dato propio", f"{suben_gold} / {medibles}", None,
     "Cierre contra cierre, calculado en <code>v_ohlc_diario</code>. "
     f"Con el número que trae la API serían <b>{suben}</b> de "
     f"{total_activos}: miden ventanas distintas."),
]
for col, (lab, val, chg, foot) in zip(cols, datos_kpi):
    col.markdown(kpi(lab, val, chg, foot=foot), unsafe_allow_html=True)

if k["mcap_delta_pct"] is None:
    st.caption("ℹ️ Los deltas aparecen con **2+ días** de historia — el pipeline recién arranca a acumular.")

# --- el mismo numero, dos veces -------------------------------------------
# El corazon de la pagina, y la razon de que exista Gold. Antes esta pantalla
# mostraba SOLO el 24 h de CoinGecko: si borraras el warehouse entero se habria
# visto casi igual, que es la prueba de que no estaba mostrando Gold.
seccion("El mismo número, dos veces",
        "La API lo trae masticado · el warehouse lo construye · no coinciden")

comp = doble.dropna(subset=["var_api_pct", "var_gold_pct"]).copy()
if comp.empty:
    st.caption("Hace falta un segundo día de cierres para poder calcular el "
               "nuestro. El pipeline lo suma solo.")
else:
    comp["abs_brecha"] = comp["brecha_pts"].abs()
    peor = comp.nlargest(10, "abs_brecha").sort_values("abs_brecha")

    izq, der = st.columns([1.05, .95])
    with izq:
        st.markdown(
            "La misma pregunta — *¿cuánto se movió en 24 horas?* — tiene "
            "**dos respuestas distintas**, y ninguna está mal:\n\n"
            "- **`var_api_pct`** lo calcula CoinGecko sobre una **ventana "
            "móvil**: ahora contra hace exactamente 24 h. Viene listo en el "
            "JSON, y no lo podés auditar ni reproducir.\n"
            "- **`var_gold_pct`** es **cierre contra cierre**, con el corte "
            "en el día calendario. Sale de agrupar los snapshots que juntó "
            "tu pipeline, y lo podés rehacer con un `SELECT`.\n\n"
            "Miden ventanas distintas, así que **se separan** — y cuanto más "
            "se movió el activo, más se separan."
        )
        st.code(
            "-- el de la API: llega en bronze, tal cual lo mando CoinGecko\n"
            "SELECT price_change_percentage_24h FROM gold.v_ultimo_snapshot\n"
            "\n"
            "-- el nuestro: se CONSTRUYE con los hechos acumulados\n"
            "SELECT (cierre / LAG(cierre) OVER (PARTITION BY crypto_id\n"
            "                                   ORDER BY fecha) - 1) * 100\n"
            "FROM gold.v_ohlc_diario",
            language="sql",
        )
    with der:
        # Dumbbell: dos puntos por activo unidos por una linea. Se lee de un
        # golpe como "una pregunta, dos respuestas"; dos barras lado a lado se
        # leerian como dos metricas distintas, que es justo lo contrario.
        figd = go.Figure()
        for r in peor.itertuples():
            figd.add_trace(go.Scatter(
                x=[r.var_gold_pct, r.var_api_pct], y=[r.symbol, r.symbol],
                mode="lines", line=dict(color=GRIS, width=2),
                showlegend=False, hoverinfo="skip"))
        figd.add_trace(go.Scatter(
            x=peor["var_gold_pct"], y=peor["symbol"], mode="markers",
            name="calculado por vos (Gold)",
            marker=dict(size=11, color=SUBE),
            hovertemplate="<b>%{y}</b> · Gold: %{x:+.2f}%<extra></extra>"))
        figd.add_trace(go.Scatter(
            x=peor["var_api_pct"], y=peor["symbol"], mode="markers",
            name="traído de la API",
            marker=dict(size=11, color=BAJA, symbol="diamond"),
            hovertemplate="<b>%{y}</b> · API: %{x:+.2f}%<extra></extra>"))
        figd.add_vline(x=0, line_color=GRIS, line_width=1, line_dash="dot")
        figd.update_layout(**layout(
            height=330,
            xaxis=dict(title="Variación 24 h (%)", showgrid=True,
                       gridcolor="rgba(128,128,128,.15)", zeroline=False),
            yaxis=dict(showgrid=False, title=None),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            margin=dict(l=0, r=0, t=6, b=0),
        ))
        st.plotly_chart(figd, use_container_width=True)
        _p = comp.nlargest(1, "abs_brecha").iloc[0]
        st.caption(
            f"Los 10 activos donde más se separan. El peor caso de hoy es "
            f"**{_p['symbol']}**: la API dice {_p['var_api_pct']:+.2f}% y tus "
            f"hechos dicen {_p['var_gold_pct']:+.2f}% — "
            f"**{abs(_p['brecha_pts']):.2f} puntos** de diferencia sobre el "
            "mismo activo y el mismo día."
        )

    aviso(
        "<b>Acá se ve para qué sirve el medallion.</b> Bronze <b>copia</b> lo "
        "que manda la API, incluido un porcentaje que alguien calculó por vos "
        "con un criterio que no podés ver. Gold <b>construye</b> el suyo a "
        "partir de los hechos guardados, con una definición escrita en una "
        "vista y auditable.<br><br>"
        "El día que el negocio pregunte <i>«¿por qué este número?»</i>, del "
        "primero solo podés decir <i>«viene así»</i>. Del segundo podés "
        "mostrar el SQL.",
        "🥉",
    )
    de_donde_sale("gold.v_mercado_24h",
                  "Las dos columnas al lado: la que trajo la API y la que "
                  "calcula el warehouse con LAG sobre los cierres diarios.")

st.divider()

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
# El ranking de movimiento se arma con el dato PROPIO cuando existe. Como los
# dos numeros no coinciden, ordenar por uno o por otro cambia QUIEN entra en el
# top 5: la pantalla se compromete con su definicion en vez de con la ajena.
_col = "var_gold_pct" if not comp.empty else "price_change_percentage_24h"
_fuente = comp if not comp.empty else ult.dropna(subset=["price_change_percentage_24h"])
seccion("Ganadores y perdedores",
        ("Las 5 mayores subas y bajas · ordenadas por el <b>cierre contra "
         "cierre</b> que calcula Gold") if not comp.empty else
        "Las 5 mayores subas y bajas de las últimas 24 h")
_ord = _fuente.sort_values(_col)
movers = pd.concat([_ord.head(5), _ord.tail(5)]).drop_duplicates(subset="symbol")
figm = go.Figure(go.Bar(
    x=movers[_col], y=movers["name"], orientation="h",
    marker=dict(color=[SUBE if v >= 0 else BAJA for v in movers[_col]]),
    text=[f"{v:+.1f}%" for v in movers[_col]], textposition="outside",
    hovertemplate="<b>%{y}</b><br>24 h: %{x:+.2f}%<extra></extra>",
))
figm.add_vline(x=0, line_color=GRIS, line_width=1)
figm.update_layout(height=330, bargap=0.35,
                   xaxis=dict(title="Variación 24 h (%)", showgrid=True,
                              gridcolor="rgba(128,128,128,.15)", zeroline=False),
                   **{k: v for k, v in PLOTLY.items() if k != "xaxis"})
st.plotly_chart(figm, use_container_width=True)
st.caption(
    "🔵 sube · 🔴 baja — el signo va escrito en la etiqueta: la lectura "
    "no depende del color."
    + ("  ·  Ordenado por `var_gold_pct`: con el número de la API el top 5 "
       "**no sería el mismo**." if not comp.empty else ""))

# --- ranking ---------------------------------------------------------------
seccion("Ranking", "Último snapshot de cada activo")

# El filtro va SOLO acá y no arriba de toda la pagina, a proposito: el hero,
# los KPIs y el mapa son del mercado COMPLETO (v_kpis_mercado agrega todas
# las criptas en una fila). Un control arriba de todo daria a entender que
# tambien los recorta, y no es asi.
try:
    _cats = list(q("SELECT DISTINCT categoria FROM gold.dim_crypto "
                   "WHERE categoria IS NOT NULL ORDER BY 1")["categoria"])
except Exception:
    _cats = []
_sel = filtro_categoria("mercado", opciones=_cats) if _cats else []
_W = where_categoria("categoria", _sel, universo=_cats)

# Se vuelve a consultar en vez de filtrar el DataFrame en pandas: el corte por
# `categoria` es un WHERE contra la dimension, que es para lo que existe el
# star schema. Filtrar en el cliente traeria las 53 criptas para tirar 40.
rank = q("""
    SELECT name, symbol, current_price, var_api_pct, var_gold_pct, brecha_pts,
           market_cap, market_cap_rank
    FROM gold.v_mercado_24h
    WHERE 1=1 """ + _W + """
    ORDER BY market_cap_rank
""") if _W else doble

if rank.empty:
    st.caption("Ninguna cripto en esa categoría.")
    rank = doble.head(0)

_mcap_max = rank["market_cap"].max() if not rank.empty else 1


def _pct(v, tenue=False):
    """La celda de un porcentaje, o un guion cuando todavia no se puede calcular.

    El guion importa: var_gold_pct es NULL mientras esa cripta no tenga un
    segundo cierre. Escribir 0.00% ahi seria inventar que no se movio.
    """
    if v is None or pd.isna(v):
        return "<td style='color:var(--ink-3)'>—</td>"
    if tenue:
        return f"<td style='color:var(--ink-3)'>{v:+.2f}%</td>"
    return f"<td class='{'u' if v >= 0 else 'd'}'>{v:+.2f}%</td>"


def _brecha(v):
    """Se marca solo cuando supera medio punto.

    Por debajo de eso son dos formas de redondear la misma jornada; pintar
    todas las filas haria que la senal deje de leerse.
    """
    if v is None or pd.isna(v):
        return "<td style='color:var(--ink-3)'>—</td>"
    if abs(v) >= .5:
        return f"<td style='color:var(--down)'>{abs(v):.2f}</td>"
    return "<td style='color:var(--ink-3)'>·</td>"


filas = "".join(
    f"<tr><td>{int(r.market_cap_rank)}</td>"
    f"<td>{r.name}<span class='sym'>{r.symbol}</span></td>"
    f"<td>US$ {r.current_price:,.2f}</td>"
    + _pct(r.var_gold_pct)
    + _pct(r.var_api_pct, tenue=True)
    + _brecha(r.brecha_pts)
    + f"<td>US$ {r.market_cap / 1e9:,.1f} B"
      f"<span style='display:inline-block;height:7px;border-radius:2px;background:{SUBE};"
      f"opacity:.7;vertical-align:middle;margin-left:9px;"
      f"width:{max(3, r.market_cap / _mcap_max * 72):.0f}px'></span></td></tr>"
    for r in rank.itertuples()
)
tabla(filas, ["#", "Activo", "Precio", "24 h · Gold", "24 h · API",
              "Brecha", "Capitalización"])
_disc = int((rank["brecha_pts"].abs() >= .5).sum()) if not rank.empty else 0
st.caption(
    f"La columna que manda es **24 h · Gold**: es la que podés explicar. "
    f"**Brecha** marca en rojo las {_disc} filas donde las dos definiciones "
    "se separan más de medio punto — mismo activo, mismo día, dos respuestas."
)

de_donde_sale("gold.v_kpis_mercado",
              "Los KPIs de arriba, con sus deltas contra el día anterior ya "
              "calculados en SQL. La página no resta nada: lee.")
de_donde_sale("gold.v_ultimo_snapshot",
              "La foto de cada cripto: el DISTINCT ON que se queda con el "
              "snapshot más reciente de cada una.")
st.caption(f"Último snapshot: **{ts:%Y-%m-%d %H:%M} UTC** · "
           f"{int(k['active_cryptocurrencies']):,} criptos activas en {int(k['markets']):,} mercados".replace(",", "."))
