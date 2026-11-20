"""Regiones y magnitudes: ¿donde se concentra y que tan fuertes son?"""

import plotly.express as px
import streamlit as st

from db import consultar, sin_datos_aun
from theme import AZUL, COLOR_MAGNITUD, ORDEN_MAGNITUD, estilo

st.title("📊 Regiones y magnitudes")

regiones = consultar("SELECT * FROM gold.v_actividad_por_region")
if regiones.empty:
    sin_datos_aun()
    st.stop()

# ----------------------------------------------------------------- ranking
st.subheader("¿Qué regiones concentran la actividad?")
criterio = st.radio(
    "Contar", ["Sismos de magnitud 4,5 o más", "Todos los sismos"], horizontal=True,
    help="Con 'todos', EE.UU. domina porque detecta hasta los microsismos. "
         "A partir de 4,5 la detección es pareja en todo el mundo: es la comparación justa.",
)
col = "sismos_m45" if criterio.startswith("Sismos de") else "sismos"
top = regiones.sort_values(col, ascending=False).head(15).sort_values(col)
fig = px.bar(top, x=col, y="region", orientation="h",
             title=f"Top 15 regiones — {criterio.lower()}",
             labels={col: "sismos", "region": ""},
             custom_data=["macrozona", "magnitud_max", "profundidad_promedio_km"])
fig.update_traces(marker_color=AZUL,
                  hovertemplate="<b>%{y}</b> (%{customdata[0]})<br>%{x} sismos"
                                "<br>Magnitud maxima %{customdata[1]:.1f}"
                                "<br>Profundidad promedio %{customdata[2]:.0f} km<extra></extra>")
st.plotly_chart(estilo(fig, alto=480), use_container_width=True)
st.caption("Fuente: `gold.v_actividad_por_region`.")

izq, der = st.columns(2)

# ------------------------------------------------------ por macrozona
with izq:
    macro = consultar("SELECT * FROM gold.v_actividad_por_macrozona").sort_values("sismos_m45")
    fig = px.bar(macro, x="sismos_m45", y="macrozona", orientation="h",
                 title="Sismos de magnitud 4,5+ por macrozona",
                 labels={"sismos_m45": "sismos M4,5+", "macrozona": ""})
    fig.update_traces(marker_color=AZUL,
                      hovertemplate="<b>%{y}</b><br>%{x} sismos M4,5+<extra></extra>")
    st.plotly_chart(estilo(fig), use_container_width=True)
    st.caption("Macrozona asignada en Silver por coordenadas (cajas aproximadas). "
               "Fuente: `gold.v_actividad_por_macrozona`.")

# ------------------------------------------------- distribucion de magnitud
with der:
    mp = consultar("SELECT * FROM gold.v_magnitud_profundidad")
    dist = (mp.groupby(["categoria_magnitud", "orden_magnitud"], as_index=False)["cantidad"].sum()
              .sort_values("orden_magnitud"))
    fig = px.bar(dist, x="categoria_magnitud", y="cantidad", log_y=True,
                 title="¿Qué tan fuertes? Sismos por categoría (escala log)",
                 color="categoria_magnitud", color_discrete_map=COLOR_MAGNITUD,
                 category_orders={"categoria_magnitud": ORDEN_MAGNITUD},
                 labels={"categoria_magnitud": "", "cantidad": "sismos"})
    fig.update_traces(hovertemplate="<b>%{x}</b><br>%{y} sismos<extra></extra>")
    st.plotly_chart(estilo(fig), use_container_width=True)
    st.caption("Escala logarítmica: por cada sismo de una categoría hay ~10 de la "
               "anterior (ley de Gutenberg-Richter). Fuente: `gold.v_magnitud_profundidad`.")

# --------------------------------------------- cruce magnitud x profundidad
st.subheader("Magnitud × profundidad")
tabla = (mp.pivot_table(index="categoria_profundidad", columns="categoria_magnitud",
                        values="cantidad", aggfunc="sum", fill_value=0)
           .reindex(index=["Superficial", "Intermedio", "Profundo"])
           .reindex(columns=[c for c in ORDEN_MAGNITUD if c in set(mp["categoria_magnitud"])])
           .fillna(0))
fig = px.imshow(tabla, text_auto=True, aspect="auto",
                title="Sismos por categoría de magnitud y de profundidad",
                color_continuous_scale=[[0, "#1a1a19"], [0.02, "#184f95"], [1, "#9ec5f4"]],
                labels={"x": "Magnitud", "y": "Profundidad", "color": "sismos"})
fig.update_traces(hovertemplate="%{y} · %{x}<br><b>%{z}</b> sismos<extra></extra>")
st.plotly_chart(estilo(fig, alto=300), use_container_width=True)
st.caption("El mismo hecho (cada sismo) cortado por dos dimensiones del modelo estrella: "
           "`dim_magnitud` y `dim_profundidad`.")

# ------------------------------------------------------- tipos de evento
st.subheader("No todo lo que tiembla es un sismo")
tipos = consultar("SELECT * FROM gold.v_eventos_por_tipo ORDER BY cantidad")
fig = px.bar(tipos, x="cantidad", y="tipo_evento", orientation="h", log_x=True,
             title="Eventos registrados por tipo (escala log)",
             labels={"cantidad": "eventos", "tipo_evento": ""})
fig.update_traces(marker_color=AZUL,
                  hovertemplate="<b>%{y}</b><br>%{x} eventos<extra></extra>")
st.plotly_chart(estilo(fig, alto=300), use_container_width=True)
st.caption("USGS también registra voladuras de canteras, explosiones y sismos glaciares. "
           "No son errores (no van a cuarentena): quedan en Silver marcados y Gold los "
           "excluye de los análisis de sismos. Fuente: `gold.v_eventos_por_tipo`.")
