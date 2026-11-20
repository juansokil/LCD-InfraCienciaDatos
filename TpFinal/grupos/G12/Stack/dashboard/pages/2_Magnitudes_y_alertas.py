import plotly.express as px
import streamlit as st

from db import COLORES_ALERTA, NARANJA, boton_actualizar, chequear_datos, consulta

st.set_page_config(page_title="Magnitudes y alertas", page_icon="⚠️", layout="wide")
boton_actualizar()
st.title("⚠️ Magnitudes y alertas")

chequear_datos()

datos = consulta("""
    SELECT f.magnitud, f.profundidad, f.significancia,
           m.tipo_magnitud, a.tipo_alerta, u.region
    FROM gold.fact_terremoto f
    JOIN gold.dim_magnitud m  ON m.id_magnitud = f.id_magnitud
    JOIN gold.dim_alerta a    ON a.id_alerta = f.id_alerta
    JOIN gold.dim_ubicacion u ON u.id_ubicacion = f.id_ubicacion
""")

izq, der = st.columns(2)

with izq:
    st.subheader("Distribución de magnitudes")
    fig = px.histogram(
        datos, x="magnitud", nbins=30,
        color_discrete_sequence=[NARANJA],
        labels={"magnitud": "Magnitud"},
    )
    fig.update_layout(yaxis_title="Terremotos")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("La mayoría son chicos: cuanto más grande, menos frecuente.")

with der:
    st.subheader("Escalas de magnitud")
    escalas = datos["tipo_magnitud"].value_counts().reset_index()
    escalas.columns = ["tipo_magnitud", "terremotos"]
    fig = px.pie(
        escalas, names="tipo_magnitud", values="terremotos", hole=0.5,
        color_discrete_sequence=px.colors.sequential.Oranges_r,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("El USGS usa distintas escalas (mb, ml, mww...) según el sismo y la red que lo registra.")

st.subheader("Alertas del USGS")
alertas = datos["tipo_alerta"].value_counts().reset_index()
alertas.columns = ["tipo_alerta", "terremotos"]
fig = px.bar(
    alertas, x="tipo_alerta", y="terremotos",
    color="tipo_alerta", color_discrete_map=COLORES_ALERTA,
    labels={"tipo_alerta": "", "terremotos": "Terremotos"},
)
fig.update_layout(showlegend=False)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Unknown = el USGS no informó alerta (pasa con la mayoría de los sismos chicos). "
    "No lo contamos como verde."
)

st.subheader("Profundidad vs. magnitud")
fig = px.scatter(
    datos, x="profundidad", y="magnitud",
    color="tipo_alerta", color_discrete_map=COLORES_ALERTA,
    size="significancia", size_max=18, opacity=0.7,
    hover_data=["region"],
    labels={"profundidad": "Profundidad (km)", "magnitud": "Magnitud", "tipo_alerta": "Alerta"},
)
st.plotly_chart(fig, use_container_width=True)
st.caption("El tamaño de cada punto es la significancia que calcula el USGS.") 