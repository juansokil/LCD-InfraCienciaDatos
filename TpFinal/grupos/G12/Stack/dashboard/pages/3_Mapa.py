import plotly.express as px
import streamlit as st

from db import COLORES_ALERTA, boton_actualizar, chequear_datos, consulta

st.set_page_config(page_title="Mapa", page_icon="🗺️", layout="wide")
boton_actualizar()
st.title("🗺️ Mapa de terremotos")

chequear_datos()

datos = consulta("""
    SELECT d.fecha, u.region, COALESCE(u.ubicacion, '-') AS ubicacion,
           f.latitud, f.longitud, f.magnitud, f.profundidad, a.tipo_alerta
    FROM gold.fact_terremoto f
    JOIN gold.dim_fecha d     ON d.fecha_id = f.fecha_id
    JOIN gold.dim_ubicacion u ON u.id_ubicacion = f.id_ubicacion
    JOIN gold.dim_alerta a    ON a.id_alerta = f.id_alerta
""")

# filtros
mag_min = st.sidebar.slider("Magnitud mínima", 2.5, 8.0, 2.5, 0.5)
colorear = st.sidebar.radio("Color según", ["Profundidad", "Alerta"])
datos = datos[datos["magnitud"] >= mag_min]

st.write(f"Se muestran **{len(datos)}** terremotos de magnitud {mag_min} o más. "
         "Cada punto es un terremoto y el tamaño es su magnitud.")

if colorear == "Profundidad":
    color = dict(color="profundidad", color_continuous_scale="YlOrRd")
else:
    color = dict(color="tipo_alerta", color_discrete_map=COLORES_ALERTA)

fig = px.scatter_geo(
    datos,
    lat="latitud",
    lon="longitud",
    size="magnitud",
    size_max=14,
    opacity=0.75,
    hover_name="ubicacion",
    hover_data={"region": True, "fecha": True, "magnitud": ":.1f", "profundidad": ":.0f",
                "latitud": False, "longitud": False},
    projection="natural earth",
    labels={"profundidad": "Profundidad (km)", "tipo_alerta": "Alerta"},
    **color,
)
fig.update_geos(
    showland=True, landcolor="#2a313c",
    showocean=True, oceancolor="#11151c",
    showcountries=True, countrycolor="#3d4654",
    showcoastlines=False, bgcolor="rgba(0,0,0,0)",
)
fig.update_layout(height=600, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Se nota el Cinturón de Fuego del Pacífico: la mayoría de los terremotos "
    "caen en el borde del océano Pacífico (Alaska, Japón, Indonesia, Chile)."
) 