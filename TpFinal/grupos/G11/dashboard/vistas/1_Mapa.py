"""Mapa: ¿donde tiembla?"""

import pandas as pd
import plotly.express as px
import streamlit as st

from db import consultar, sin_datos_aun
from theme import ESCALA_CONTINUA, mapa_base

st.title("🗺️ ¿Dónde tiembla?")

sismos = consultar("""
    SELECT event_id, ocurrido_at, fecha, magnitud, categoria_magnitud,
           profundidad_km, categoria_profundidad, latitud, longitud,
           lugar, pais, macrozona, tsunami
    FROM gold.v_sismos
""")
if sismos.empty:
    sin_datos_aun()
    st.stop()

# Filtros, todos en una fila arriba del grafico
f1, f2, f3 = st.columns([1, 2, 1])
mag_min = f1.slider("Magnitud mínima", -1.0, 7.0, 2.5, 0.5,
                    help="Por defecto 2,5: debajo de eso casi todo son microsismos de EE.UU.")
zonas = sorted(sismos["macrozona"].unique())
elegidas = f2.multiselect("Macrozonas", zonas, default=zonas)
dias = f3.selectbox("Período", [1, 7, 30], index=2,
                    format_func=lambda d: "Últimas 24 h" if d == 1 else f"Últimos {d} días")

limite = sismos["ocurrido_at"].max() - pd.Timedelta(days=dias)
vista = sismos[(sismos["magnitud"] >= mag_min)
               & (sismos["macrozona"].isin(elegidas))
               & (sismos["ocurrido_at"] >= limite)].copy()

st.caption(f"**{len(vista):,}** sismos con estos filtros. Color y tamaño = magnitud."
           .replace(",", "."))

if vista.empty:
    st.warning("No hay sismos con esos filtros.")
    st.stop()

vista["tamano"] = (vista["magnitud"].astype(float).clip(lower=0) + 1) ** 2
vista["cuando"] = vista["ocurrido_at"].dt.strftime("%d/%m %H:%M UTC")
fig = px.scatter_geo(
    vista.sort_values("magnitud"),        # los fuertes se dibujan arriba
    lat="latitud", lon="longitud", color="magnitud", size="tamano",
    size_max=22, color_continuous_scale=ESCALA_CONTINUA,
    custom_data=["lugar", "magnitud", "profundidad_km", "cuando"],
)
fig.update_traces(
    marker=dict(line=dict(width=0.5, color="#1a1a19"), opacity=0.85),
    hovertemplate="<b>%{customdata[0]}</b><br>Magnitud %{customdata[1]:.1f}"
                  "<br>Profundidad %{customdata[2]:.0f} km<br>%{customdata[3]}<extra></extra>",
)
fig.update_layout(coloraxis_colorbar=dict(title="Magnitud", thickness=12))
st.plotly_chart(mapa_base(fig), use_container_width=True)

st.subheader("Los 15 más fuertes con estos filtros")
top = (vista.sort_values("magnitud", ascending=False).head(15)
       [["cuando", "magnitud", "categoria_magnitud", "profundidad_km", "lugar", "pais", "tsunami"]]
       .rename(columns={"cuando": "Fecha", "magnitud": "Magnitud",
                        "categoria_magnitud": "Categoría", "profundidad_km": "Profundidad (km)",
                        "lugar": "Lugar", "pais": "País / región", "tsunami": "Alerta tsunami"}))
st.dataframe(top, hide_index=True, use_container_width=True)
st.caption("Fuente: `gold.v_sismos` (fact_sismo unida a sus dimensiones).")
