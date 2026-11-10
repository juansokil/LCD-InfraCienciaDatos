import streamlit as st
import plotly.express as px

from db import run_query

st.title("🗺️ Mapa de sismos")
st.markdown(
    "Cada punto representa un evento sísmico de Silver. El tamaño indica la "
    "magnitud y el color la profundidad en kilómetros."
)

try:
    mapa = run_query("""
        SELECT sismo_id, fecha_evento, magnitud, profundidad_km,
               latitud, longitud, tsunami, zona_reportada
        FROM gold.v_mapa_sismos
        ORDER BY fecha_evento DESC
    """)
except Exception as exc:
    st.error(f"No se pudo consultar la vista del mapa: {exc}")
    st.stop()

if mapa.empty:
    st.info("No hay sismos Gold para ubicar en el mapa.")
    st.stop()

limite = st.slider(
    "Eventos más recientes a mostrar",
    min_value=500,
    max_value=min(9500, max(500, len(mapa))),
    value=min(3000, max(500, len(mapa))),
    step=500,
)
mapa = mapa.head(limite)
mapa["profundidad_km"] = mapa["profundidad_km"].fillna(0)
mapa["magnitud_marcador"] = mapa["magnitud"].clip(lower=0.1)

fig = px.scatter_geo(
    mapa,
    lat="latitud",
    lon="longitud",
    color="profundidad_km",
    size="magnitud_marcador",
    size_max=16,
    hover_name="zona_reportada",
    hover_data={
        "sismo_id": True,
        "fecha_evento": True,
        "magnitud": ":.1f",
        "magnitud_marcador": False,
        "profundidad_km": ":.1f",
        "tsunami": True,
        "latitud": False,
        "longitud": False,
    },
    color_continuous_scale="Viridis",
    projection="natural earth",
    title=f"Últimos {len(mapa):,} eventos",
)
fig.update_geos(showland=True, landcolor="rgb(243, 243, 243)")
fig.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Conclusión: la distribución espacial muestra dónde se concentraron los "
    "eventos recientes; los eventos de magnitud menor que 0 se dibujan con "
    "el tamaño mínimo. El mapa no representa riesgo ni predice sismos."
)
