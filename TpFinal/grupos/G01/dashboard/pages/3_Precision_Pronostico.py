import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import get_engine

st.set_page_config(
    page_title="Precisión del Pronóstico", page_icon="🎯", layout="wide"
)
st.title("Precisión del Pronóstico Meteorológico")
st.caption("Comparación: Open-Meteo vs realidad")

@st.cache_data(ttl=3600)
def cargar_datos():
    engine = get_engine()
    query = """
        SELECT
            p.nombre_provincia,
            d.fecha_evaluada,
            t.dia_semana,
            d.temp_max_pronosticada,
            d.temp_max_real,
            d.error_max_c,
            d.lluvio_pronostico,
            d.lluvio_real,
            d.acierto_lluvia
        FROM gold.fact_desvio_pronostico d
        JOIN gold.dim_provincia p ON d.id_provincia   = p.id_provincia
        JOIN gold.dim_tiempo    t ON d.fecha_evaluada = t.fecha
        ORDER BY d.fecha_evaluada DESC, p.nombre_provincia
    """
    return pd.read_sql(query, engine)

df = cargar_datos()

if df.empty:
    st.info("Todavía no hay datos de desvío. El pipeline necesita al menos un día completo de mediciones.")
    st.stop()

st.subheader("Resumen general")

total_evaluaciones = len(df)
error_promedio     = df["error_max_c"].mean()
precision_lluvia   = df["acierto_lluvia"].mean() * 100
sin_error          = (df["error_max_c"] == 0).sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Evaluaciones totales",    total_evaluaciones)
col2.metric("Error promedio (°C)",     f"{error_promedio:.2f}")
col3.metric("Precisión lluvia",        f"{precision_lluvia:.0f}%")
col4.metric("Pronósticos exactos",     f"{sin_error} de {total_evaluaciones}")

st.divider()

st.subheader("Error promedio por provincia (°C)")
st.caption("Cuántos grados se equivocó el pronóstico en promedio para cada región")

error_prov = (
    df.groupby("nombre_provincia")["error_max_c"]
    .mean()
    .reset_index()
    .sort_values("error_max_c")
)
error_prov.columns = ["Provincia", "Error promedio (°C)"]

fig_error = px.bar(
    error_prov,
    x="Error promedio (°C)",
    y="Provincia",
    orientation="h",
    color="Error promedio (°C)",
    color_continuous_scale="RdYlGn_r",
    text="Error promedio (°C)",
)
fig_error.update_traces(texttemplate="%{text:.2f}°C", textposition="outside")
fig_error.update_layout(
    coloraxis_showscale=False,
    margin=dict(t=20),
    yaxis_title="",
)
st.plotly_chart(fig_error, use_container_width=True)

st.divider()

st.subheader("Temperatura máxima: pronóstico vs realidad")
st.caption("Comparación directa por provincia — barras agrupadas")

df_barras = df[["nombre_provincia", "fecha_evaluada",
                "temp_max_pronosticada", "temp_max_real"]].copy()

df_melted = df_barras.melt(
    id_vars=["nombre_provincia", "fecha_evaluada"],
    value_vars=["temp_max_pronosticada", "temp_max_real"],
    var_name="tipo",
    value_name="temperatura",
)
df_melted["tipo"] = df_melted["tipo"].map({
    "temp_max_pronosticada": "Pronosticada",
    "temp_max_real":         "Real",
})
df_melted["etiqueta"] = (
    df_melted["nombre_provincia"] + "\n"
    + df_melted["fecha_evaluada"].astype(str)
)

fig_barras = px.bar(
    df_melted,
    x="nombre_provincia",
    y="temperatura",
    color="tipo",
    barmode="group",
    facet_col="fecha_evaluada" if df["fecha_evaluada"].nunique() > 1 else None,
    color_discrete_map={
        "Pronosticada": "#5B9BD5",
        "Real":         "#ED7D31",
    },
    labels={
        "temperatura":       "Temperatura (°C)",
        "nombre_provincia":  "Provincia",
        "tipo":              "",
        "fecha_evaluada":    "Fecha",
    },
    text_auto=".1f",
)
fig_barras.update_traces(textposition="outside", textfont_size=11)
fig_barras.update_layout(
    legend_title_text="",
    margin=dict(t=40),
    uniformtext_minsize=8,
)
fig_barras.for_each_annotation(
    lambda a: a.update(text=a.text.split("=")[-1])
)
st.plotly_chart(fig_barras, use_container_width=True)

if df["fecha_evaluada"].nunique() > 1:
    st.divider()
    st.subheader("Evolución del error a lo largo del tiempo")

    fig_evol = px.line(
        df,
        x="fecha_evaluada",
        y="error_max_c",
        color="nombre_provincia",
        markers=True,
        labels={
            "fecha_evaluada":  "Fecha",
            "error_max_c":     "Error (°C)",
            "nombre_provincia": "Provincia",
        },
    )
    fig_evol.update_layout(hovermode="x unified", margin=dict(t=20))
    st.plotly_chart(fig_evol, use_container_width=True)

st.divider()

st.subheader("Detalle completo")

tabla = df[[
    "nombre_provincia", "fecha_evaluada", "dia_semana",
    "temp_max_pronosticada", "temp_max_real", "error_max_c",
    "lluvio_pronostico", "lluvio_real", "acierto_lluvia"
]].copy()

tabla["lluvio_pronostico"] = tabla["lluvio_pronostico"].map({True: "Sí", False: "No"})
tabla["lluvio_real"]       = tabla["lluvio_real"].map({True: "Sí", False: "No"})
tabla["acierto_lluvia"]    = tabla["acierto_lluvia"].map({True: "✅", False: "❌"})

tabla.columns = [
    "Provincia", "Fecha", "Día",
    "Máx Pronosticada (°C)", "Máx Real (°C)", "Error (°C)",
    "¿Llovió pronosticado?", "¿Llovió real?", "Acierto lluvia"
]

st.dataframe(tabla, use_container_width=True, hide_index=True)