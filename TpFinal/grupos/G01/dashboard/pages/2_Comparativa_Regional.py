import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import get_engine

st.set_page_config(
    page_title="Comparativa Regional", page_icon="📊", layout="wide"
)
st.title("📊 Comparativa Regional de Temperaturas")

@st.cache_data(ttl=3600)
def cargar_datos():
    engine = get_engine()
    query = """
        SELECT
            p.nombre_provincia,
            f.fecha,
            f.temp_promedio_c,
            f.temp_max_real_c,
            f.temp_min_real_c,
            f.lluvia_total_mm,
            f.confort_termico
        FROM gold.fact_clima_diario f
        JOIN gold.dim_provincia p ON f.id_provincia = p.id_provincia
        ORDER BY f.fecha, p.nombre_provincia
    """
    return pd.read_sql(query, engine)

df = cargar_datos()

if df.empty:
    st.warning("Sin datos disponibles todavía.")
    st.stop()

provincias = sorted(df["nombre_provincia"].unique())

seleccion = st.multiselect(
    "Seleccioná provincias a comparar",
    options=provincias,
    default=provincias,
)

if not seleccion:
    st.warning("Seleccioná al menos una provincia.")
    st.stop()

df_filtrado = df[df["nombre_provincia"].isin(seleccion)]

st.divider()

st.subheader("Temperatura promedio diaria (°C)")

fig_temp = px.line(
    df_filtrado,
    x="fecha",
    y="temp_promedio_c",
    color="nombre_provincia",
    markers=True,
    labels={
        "fecha":           "Fecha",
        "temp_promedio_c": "Temperatura (°C)",
        "nombre_provincia": "Provincia",
    },
)
fig_temp.update_layout(
    legend_title_text="Provincia",
    hovermode="x unified",
    margin=dict(t=20),
)
st.plotly_chart(fig_temp, use_container_width=True)

st.subheader("Rango térmico diario por provincia (°C)")
st.caption("Temperatura máxima y mínima real — un panel por provincia")

df_rango = df_filtrado.melt(
    id_vars=["nombre_provincia", "fecha"],
    value_vars=["temp_max_real_c", "temp_min_real_c"],
    var_name="tipo",
    value_name="temperatura",
)
df_rango["tipo"] = df_rango["tipo"].map({
    "temp_max_real_c": "Máxima",
    "temp_min_real_c": "Mínima",
})

fig_rango = px.line(
    df_rango,
    x="fecha",
    y="temperatura",
    color="tipo",
    facet_col="nombre_provincia",
    facet_col_wrap=3,
    markers=True,
    color_discrete_map={
        "Máxima": "#E05C5C",
        "Mínima": "#5B9BD5",
    },
    labels={
        "fecha":             "Fecha",
        "temperatura":       "Temperatura (°C)",
        "tipo":              "",
        "nombre_provincia":  "",
    },
)
fig_rango.update_layout(
    margin=dict(t=60),
    hovermode="x unified",
)
fig_rango.for_each_annotation(
    lambda a: a.update(text=a.text.split("=")[-1], font_size=12)
)
fig_rango.update_yaxes(matches=None, showticklabels=True)
st.plotly_chart(fig_rango, use_container_width=True)

st.subheader("Lluvia acumulada diaria (mm)")

fig_lluvia = px.bar(
    df_filtrado,
    x="fecha",
    y="lluvia_total_mm",
    color="nombre_provincia",
    barmode="group",
    labels={
        "fecha":           "Fecha",
        "lluvia_total_mm": "Lluvia (mm)",
        "nombre_provincia": "Provincia",
    },
)
fig_lluvia.update_layout(
    legend_title_text="Provincia",
    margin=dict(t=20),
)
st.plotly_chart(fig_lluvia, use_container_width=True)