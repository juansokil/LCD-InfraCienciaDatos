"""
Ranking de zonas — ¿dónde tiembla más, y dónde más fuerte?

Lee gold.agg_ranking_zonas (agregado por región sobre todo el período).
"""

import plotly.express as px
import streamlit as st

from db import boton_actualizar, exigir_gold, run_query

st.set_page_config(page_title="G12 · Ranking de zonas", page_icon="🏆", layout="wide")
boton_actualizar()
st.title("🏆 Ranking de zonas")
st.caption("Fuente: `gold.agg_ranking_zonas`")

exigir_gold()

ranking = run_query("SELECT * FROM gold.agg_ranking_zonas ORDER BY total_sismos DESC")

n_zonas = len(ranking)
top_n = (
    st.sidebar.slider("Cuántas zonas mostrar", 5, min(40, n_zonas), min(15, n_zonas))
    if n_zonas > 5
    else n_zonas
)

# --- Más actividad ------------------------------------------------------------
st.subheader(f"Las {top_n} zonas con más sismos")
top = ranking.head(top_n)
fig = px.bar(
    top.iloc[::-1],  # la mas activa arriba
    x="total_sismos",
    y="region",
    orientation="h",
    color="magnitud_promedio",
    color_continuous_scale="OrRd",
    labels={"total_sismos": "Sismos", "region": "", "magnitud_promedio": "Mag. prom."},
)
fig.update_layout(height=max(350, 28 * top_n))
st.plotly_chart(fig, use_container_width=True)

# --- Cantidad vs intensidad ---------------------------------------------------
st.subheader("¿Las zonas que más tiemblan son las que tiemblan más fuerte?")
st.caption(
    "Cada burbuja es una zona: su tamaño es la cantidad de sismos. Arriba a la "
    "derecha, sismos fuertes y profundos; abajo a la izquierda, chicos y superficiales."
)
fig = px.scatter(
    ranking,
    x="profundidad_promedio_km",
    y="magnitud_promedio",
    size="total_sismos",
    color="magnitud_maxima",
    color_continuous_scale="OrRd",
    hover_name="region",
    size_max=45,
    labels={
        "profundidad_promedio_km": "Profundidad promedio (km)",
        "magnitud_promedio": "Magnitud promedio",
        "magnitud_maxima": "Mag. máx.",
        "total_sismos": "Sismos",
    },
)
st.plotly_chart(fig, use_container_width=True)

# --- Tsunamis -----------------------------------------------------------------
con_tsunami = ranking[ranking["total_alertas_tsunami"] > 0]
st.subheader("Zonas con alerta de tsunami")
if con_tsunami.empty:
    st.success("En el período cargado ninguna zona tuvo alerta de tsunami.")
else:
    st.dataframe(
        con_tsunami[["region", "total_alertas_tsunami", "magnitud_maxima", "total_sismos"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "region": "Región",
            "total_alertas_tsunami": "Alertas",
            "magnitud_maxima": st.column_config.NumberColumn("Mag. máx.", format="%.1f"),
            "total_sismos": "Sismos",
        },
    )

with st.expander("Ver el ranking completo"):
    st.dataframe(
        ranking,
        hide_index=True,
        use_container_width=True,
        column_config={
            "region": "Región",
            "total_sismos": "Sismos",
            "magnitud_promedio": st.column_config.NumberColumn("Mag. prom.", format="%.2f"),
            "magnitud_maxima": st.column_config.NumberColumn("Mag. máx.", format="%.1f"),
            "profundidad_promedio_km": st.column_config.NumberColumn("Prof. prom. (km)", format="%.1f"),
            "total_alertas_tsunami": "Tsunami",
        },
    )
