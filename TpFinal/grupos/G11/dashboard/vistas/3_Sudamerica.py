"""Sudamerica: la zona que mas nos importa."""

import plotly.express as px
import streamlit as st

from db import consultar, sin_datos_aun
from theme import AZUL, ESCALA_CONTINUA, estilo, mapa_base

st.title("🌎 Sudamérica")

sa = consultar("""
    SELECT ocurrido_at, magnitud, categoria_magnitud, profundidad_km,
           categoria_profundidad, latitud, longitud, lugar, pais, tsunami, url
    FROM gold.v_sismos
    WHERE macrozona = 'Sudamerica'
""")
if sa.empty:
    sin_datos_aun()
    st.stop()

paises = consultar("SELECT * FROM gold.v_sudamerica_por_pais ORDER BY sismos DESC")
arg = paises[paises["pais"] == "Argentina"]

c = st.columns(2) + st.columns(2)
c[0].metric("Sismos en Sudamérica", len(sa))
c[1].metric("Magnitud máxima", f"{sa['magnitud'].max():.1f}")
c[2].metric("Profundos (> 300 km)", int((sa["profundidad_km"] > 300).sum()))
c[3].metric("En Argentina", int(arg["sismos"].iloc[0]) if not arg.empty else 0)

izq, der = st.columns([3, 2])
with izq:
    sa["tamano"] = (sa["magnitud"].astype(float).clip(lower=0) + 1) ** 2
    sa["cuando"] = sa["ocurrido_at"].dt.strftime("%d/%m %H:%M UTC")
    fig = px.scatter_geo(sa.sort_values("magnitud"), lat="latitud", lon="longitud",
                         color="profundidad_km", size="tamano", size_max=20,
                         color_continuous_scale=ESCALA_CONTINUA,
                         custom_data=["lugar", "magnitud", "profundidad_km", "cuando"])
    fig.update_traces(
        marker=dict(line=dict(width=0.5, color="#1a1a19"), opacity=0.9),
        hovertemplate="<b>%{customdata[0]}</b><br>Magnitud %{customdata[1]:.1f}"
                      "<br>Profundidad %{customdata[2]:.0f} km<br>%{customdata[3]}<extra></extra>")
    fig.update_layout(coloraxis_colorbar=dict(title="Prof. (km)", thickness=12))
    st.plotly_chart(mapa_base(fig, alto=560, alcance="south america"), use_container_width=True)
    st.caption("Color = profundidad, tamaño = magnitud.")

with der:
    top = paises.head(10).sort_values("sismos")
    fig = px.bar(top, x="sismos", y="pais", orientation="h",
                 title="Sismos por país / región",
                 labels={"sismos": "sismos", "pais": ""},
                 custom_data=["magnitud_max", "profundidad_promedio_km"])
    fig.update_traces(marker_color=AZUL,
                      hovertemplate="<b>%{y}</b><br>%{x} sismos<br>Magnitud máxima "
                                    "%{customdata[0]:.1f}<br>Profundidad promedio "
                                    "%{customdata[1]:.0f} km<extra></extra>")
    st.plotly_chart(estilo(fig, alto=280), use_container_width=True)

    fig = px.scatter(sa, x="longitud", y="profundidad_km", size="tamano", size_max=16,
                     title="Profundidad según longitud (oeste → este)",
                     labels={"longitud": "longitud", "profundidad_km": "profundidad (km)"},
                     custom_data=["lugar", "magnitud"])
    fig.update_traces(marker=dict(color=AZUL, opacity=0.7, line=dict(width=0.5, color="#1a1a19")),
                      hovertemplate="<b>%{customdata[0]}</b><br>Magnitud %{customdata[1]:.1f}"
                                    "<br>%{y:.0f} km<extra></extra>")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(estilo(fig, alto=280), use_container_width=True)

st.info(
    "**Por qué hay sismos tan profundos en el norte argentino:** la placa de Nazca se mete "
    "por debajo de Sudamérica (subducción). Cerca de la costa chilena los sismos son "
    "superficiales; cuanto más al este, más profunda está la placa — por eso en Santiago "
    "del Estero o Salta hay sismos a más de 500 km. El gráfico de profundidad según "
    "longitud dibuja esa placa hundiéndose.",
    icon="🧭",
)

st.subheader("Los más fuertes")
tabla = (sa.sort_values("magnitud", ascending=False).head(15)
         [["cuando", "magnitud", "profundidad_km", "lugar", "pais", "tsunami"]]
         .rename(columns={"cuando": "Fecha", "magnitud": "Magnitud",
                          "profundidad_km": "Profundidad (km)", "lugar": "Lugar",
                          "pais": "País / región", "tsunami": "Alerta tsunami"}))
st.dataframe(tabla, hide_index=True, use_container_width=True)
st.caption("Fuente: `gold.v_sismos` y `gold.v_sudamerica_por_pais`.")
