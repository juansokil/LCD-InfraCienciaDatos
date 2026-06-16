"""
Vista Gold — vistas de negocio sobre las tablas GOLD (contenido; el router/estilos están en app.py).
KPIs · insight · mapa · distribución · patrón por hora · estaciones críticas · comparación.
Consume EXCLUSIVAMENTE el schema gold.
"""
from html import escape as esc

import plotly.express as px
import streamlit as st

from db import run_query
from ui import ROJO, AMBAR, VERDE, header, panel

PLOTLY_CFG = {"displayModeBar": False}  # sin barra de herramientas blanca (zoom/descargar) que no aporta


def _fig(fig, h=None, legend=False):
    """Estilo común de los gráficos (márgenes amplios para que no se tape nada)."""
    fig.update_layout(font_family="Inter", template="plotly_white",
                      margin=dict(t=55, l=64, r=24, b=58), height=h, showlegend=legend,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    if legend:
        fig.update_layout(legend=dict(orientation="h", y=1.1, x=0, title_text=""))
    fig.update_xaxes(showgrid=False, automargin=True, title_font=dict(size=14, color="#2B1B1B"))
    fig.update_yaxes(gridcolor="#EFE9E5", automargin=True, title_font=dict(size=14, color="#2B1B1B"))
    return fig


header("CityBikes · Modelo Gold", "Disponibilidad de bicis públicas",
       "Datos en vivo de la API de CityBikes — qué estaciones se quedan sin bicis o se saturan, y a qué horas.")

# ---------- Filtro: ciudad ----------
networks = run_query("SELECT network_id, name, city FROM gold.dim_network ORDER BY name")
if networks.empty:
    st.info("Aún no hay datos en Gold. El pipeline tarda ~15 min en la primera vuelta. Esperá y refrescá.")
    st.stop()

networks["label"] = networks["city"].fillna(networks["name"]).fillna(networks["network_id"])
opciones = dict(zip(networks["label"], networks["network_id"]))
labels = list(opciones.keys())

c1, _ = st.columns([2, 3])
with c1:
    with st.container(border=True):
        ciudad = st.selectbox("Ciudad a analizar", labels, index=0)
ids = [opciones[ciudad]]

# ---------- Foto actual ----------
cur = run_query("SELECT * FROM gold.station_current WHERE network_id = ANY(:ids)", {"ids": ids})
if cur.empty:
    st.info("Sin datos para esta ciudad todavía. Esperá unos minutos y refrescá.")
    st.stop()

occ = cur["occupancy_rate"].astype(float).fillna(0)
total_est = len(cur)
total_bikes = int(cur["free_bikes"].fillna(0).sum())
total_slots = int(cur["total_slots"].fillna(0).sum())
pct_vacias = 100 * (cur["free_bikes"].fillna(0) == 0).mean()
pct_llenas = 100 * (cur["empty_slots"].fillna(0) == 0).mean()
try:
    ultima = cur["snapshot_at"].max().strftime("%d/%m %H:%M")
except Exception:
    ultima = "—"

panel(f"Estado actual · {ciudad}",
      f"Última actualización: {ultima}  ·  {total_slots:,} anclajes en total".replace(",", "."))

dominante = "quedarse SIN bicis" if pct_vacias >= pct_llenas else "la SATURACIÓN (sin lugar para dejar la bici)"
st.markdown(
    f"""<div class="insight">En <b>{ciudad}</b>, ahora mismo el <b>{pct_vacias:.0f}%</b> de las estaciones
    están <b>sin bicis</b> y el <b>{pct_llenas:.0f}%</b> están <b>saturadas</b> →
    el problema dominante es <b>{dominante}</b>.</div>""",
    unsafe_allow_html=True,
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Estaciones", f"{total_est:,}".replace(",", "."))
k2.metric("Bicis disponibles", f"{total_bikes:,}".replace(",", "."))
k3.metric("% sin bicis", f"{pct_vacias:.1f}%", help="Estaciones con 0 bicis disponibles")
k4.metric("% saturadas", f"{pct_llenas:.1f}%", help="Estaciones sin ningún lugar libre")

# ============================================================
# Mapa + dona explicativa: DOS tarjetas separadas, una al lado de la otra
# ============================================================
mapa = cur.dropna(subset=["latitude", "longitude"]).copy()
cmap, cdon = st.columns(2, gap="medium")  # mismo ancho para las dos tarjetas

with cmap:
    with st.container(border=True):
        panel("Mapa de disponibilidad", "Cada punto es una estación · color = ocupación · tamaño = capacidad")
        if mapa.empty:
            st.info("Sin coordenadas para mapear.")
        else:
            def _color(o):
                if o < 0.34:
                    return ROJO
                if o < 0.67:
                    return AMBAR
                return VERDE
            mapa["color"] = mapa["occupancy_rate"].astype(float).fillna(0).apply(_color)
            mapa["size"] = mapa["total_slots"].fillna(15).clip(lower=5, upper=40) * 2.5
            st.map(mapa, latitude="latitude", longitude="longitude",
                   color="color", size="size", height=380, use_container_width=True)
            _pill = ("display:inline-flex;align-items:center;gap:7px;border-radius:999px;"
                     "padding:5px 12px;font-size:.84rem;font-weight:600")
            st.markdown(
                f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:-.4rem'>"
                f"<span style='{_pill};background:#FCEEF0;color:#A51C2C;border:1px solid #F4D6DB'>"
                f"<span style='width:9px;height:9px;border-radius:50%;background:{ROJO}'></span>Sin bicis</span>"
                f"<span style='{_pill};background:#FBF2E3;color:#946410;border:1px solid #F0E1C5'>"
                f"<span style='width:9px;height:9px;border-radius:50%;background:{AMBAR}'></span>A medias</span>"
                f"<span style='{_pill};background:#E9F5EE;color:#1C7A43;border:1px solid #C9E7D5'>"
                f"<span style='width:9px;height:9px;border-radius:50%;background:{VERDE}'></span>Con muchas bicis</span>"
                f"</div>"
                f"<div style='color:#8A8A8A;font-size:.82rem;margin-top:9px'>"
                f"El tamaño de cada punto = <b style='color:#6B635F'>capacidad</b> de la estación.</div>",
                unsafe_allow_html=True,
            )

with cdon:
    with st.container(border=True):
        panel("Estaciones por nivel", "Distribución por nivel de disponibilidad")
        nivel = occ.apply(lambda o: "Sin bicis" if o < 0.34 else ("A medias" if o < 0.67 else "Con bicis"))
        dfp = nivel.value_counts().reindex(["Sin bicis", "A medias", "Con bicis"]).fillna(0).reset_index()
        dfp.columns = ["Nivel", "Estaciones"]
        fig_p = px.pie(dfp, values="Estaciones", names="Nivel", hole=0.58, color="Nivel",
                       color_discrete_map={"Sin bicis": ROJO, "A medias": AMBAR, "Con bicis": VERDE})
        fig_p.update_traces(textinfo="percent", sort=False,
                            textfont=dict(color="#FFFFFF", size=14),
                            insidetextfont=dict(color="#FFFFFF", size=14),
                            hovertemplate="%{label}: %{value} estaciones<extra></extra>")
        fig_p.update_layout(showlegend=False, margin=dict(t=18, l=0, r=0, b=18), height=445,
                            font_family="Inter", template="plotly_white",
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_p, use_container_width=True, config=PLOTLY_CFG)

# ============================================================
# Patrón por hora (con el peor momento)
# ============================================================
with st.container(border=True):
    panel("Patrón por hora del día", "Ocupación media y % de estaciones vacías a lo largo del día")
    patron = run_query("""
        SELECT EXTRACT(HOUR FROM hour_bucket)::int AS "Hora",
               ROUND(100*AVG(avg_occupancy),1)  AS "Ocupación media %",
               ROUND(100*AVG(pct_time_empty),1) AS "% estaciones vacías"
        FROM gold.fact_station_hourly WHERE network_id = ANY(:ids)
        GROUP BY 1 ORDER BY 1
    """, {"ids": ids})
    if len(patron) < 2:
        st.info("Todavía hay pocas horas acumuladas. Este gráfico se completa a medida que el pipeline sigue corriendo.")
    else:
        peor = patron.loc[patron["% estaciones vacías"].idxmax()]
        st.markdown(
            f"<div style='color:#2B1B1B;font-size:.95rem;margin:0 0 .5rem'>"
            f"Peor momento: <b style='color:{ROJO}'>{int(peor['Hora'])}:00 hs</b> "
            f"({peor['% estaciones vacías']:.0f}% de estaciones vacías).</div>",
            unsafe_allow_html=True,
        )
        pat_long = patron.melt("Hora", var_name="Métrica", value_name="%")
        fig_h = px.line(pat_long, x="Hora", y="%", color="Métrica", markers=True,
                        color_discrete_map={"Ocupación media %": VERDE, "% estaciones vacías": ROJO})
        fig_h.update_xaxes(title="<b>Hora del día</b>", dtick=2)
        fig_h.update_yaxes(title="<b>Porcentaje (%)</b>")
        st.plotly_chart(_fig(fig_h, h=440, legend=True), use_container_width=True, config=PLOTLY_CFG)

# ============================================================
# Estaciones más críticas
# ============================================================
with st.container(border=True):
    panel("Estaciones más críticas", "Top 10 por porcentaje del tiempo sin bicis y saturadas")

    def _tabla(titulo, df, value_col, color):
        filas = ""
        for _, r in df.iterrows():
            v = r[value_col]
            val = float(v) if (v is not None and v == v) else 0.0
            w = max(0.0, min(val, 100.0))
            filas += (
                f"<tr><td class='est'>{esc(str(r['Estación']))}</td>"
                f"<td><div class='barwrap'><div class='track'>"
                f"<div class='fill' style='width:{w:.1f}%;background:{color}'></div></div>"
                f"<span class='pct'>{val:.1f}%</span></div></td></tr>"
            )
        return (
            f"<div style='color:{color};font-weight:700;font-size:1.02rem;margin:.2rem 0 .95rem'>{titulo}</div>"
            f"<table class='cb-table'><thead><tr><th>Estación</th><th>{value_col}</th></tr></thead>"
            f"<tbody>{filas}</tbody></table>"
        )

    # guard: con pocas horas de datos el % es binario (0%/100%) y engaña → esperamos a que acumule
    _h = run_query("SELECT count(DISTINCT hour_bucket) AS h FROM gold.fact_station_hourly WHERE network_id = ANY(:ids)",
                   {"ids": ids})
    _horas = int(_h.loc[0, "h"]) if not _h.empty else 0
    if _horas < 3:
        st.info(f"Acumulando datos ({_horas} h hasta ahora). Este ranking necesita varias horas para ser "
                "representativo — se completa solo a medida que el pipeline sigue corriendo.")
    else:
        col_a, col_b = st.columns(2)
        vacias = run_query("""
            SELECT d.station_name AS "Estación",
                   ROUND(100*AVG(f.pct_time_empty),1) AS "% del tiempo SIN bicis"
            FROM gold.fact_station_hourly f JOIN gold.dim_station d USING (station_id)
            WHERE f.network_id = ANY(:ids)
            GROUP BY d.station_name ORDER BY 2 DESC LIMIT 10
        """, {"ids": ids})
        with col_a:
            st.markdown(_tabla("Más tiempo SIN bicis", vacias, "% del tiempo SIN bicis", ROJO),
                        unsafe_allow_html=True)

        llenas = run_query("""
            SELECT d.station_name AS "Estación",
                   ROUND(100*AVG(f.pct_time_full),1) AS "% del tiempo SATURADA"
            FROM gold.fact_station_hourly f JOIN gold.dim_station d USING (station_id)
            WHERE f.network_id = ANY(:ids)
            GROUP BY d.station_name ORDER BY 2 DESC LIMIT 10
        """, {"ids": ids})
        with col_b:
            st.markdown(_tabla("Más tiempo SATURADAS (sin lugar)", llenas, "% del tiempo SATURADA", AMBAR),
                        unsafe_allow_html=True)

# ============================================================
# Comparación entre las 3 ciudades
# ============================================================
with st.container(border=True):
    panel("Comparación entre ciudades", "Ocupación media de cada red (cantidad de estaciones en el hover)")
    comp = run_query("""
        SELECT n.city AS "Ciudad",
               ROUND(100*AVG(f.avg_occupancy),1)  AS "Ocupación media %",
               COUNT(DISTINCT f.station_id)       AS "Estaciones"
        FROM gold.fact_station_hourly f JOIN gold.dim_network n USING (network_id)
        GROUP BY n.city ORDER BY 2 DESC
    """)
    if not comp.empty:
        fig_c = px.bar(comp, x="Ciudad", y="Ocupación media %", text="Ocupación media %",
                       color="Ciudad",
                       color_discrete_sequence=[ROJO, AMBAR, VERDE, "#5B7DB1", "#B87333", "#7E57C2", "#2B8A8A"],
                       hover_data={"Estaciones": True, "Ciudad": False})
        fig_c.update_traces(texttemplate="%{text}%", textposition="outside", cliponaxis=False)
        fig_c.update_xaxes(title="<b>Ciudad</b>")
        fig_c.update_yaxes(title="<b>Ocupación media (%)</b>")
        st.plotly_chart(_fig(fig_c, h=440), use_container_width=True, config=PLOTLY_CFG)
