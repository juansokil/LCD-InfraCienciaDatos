import streamlit as st
import plotly.express as px

from db import run_query

st.title("📅 Actividad sísmica")
st.markdown(
    "¿Cómo se distribuyeron los sismos por mes y por zona reportada? "
    "La agrupación regional es aproximada y proviene del texto `place` de USGS."
)

try:
    actividad = run_query("""
        SELECT mes, zona_reportada, cantidad_sismos,
               magnitud_promedio, magnitud_maxima, marcados_tsunami
        FROM gold.v_actividad_mensual
        ORDER BY mes, cantidad_sismos DESC
    """)
except Exception as exc:
    st.error(f"No se pudo consultar la actividad mensual en Gold: {exc}")
    st.stop()

if actividad.empty:
    st.info("No hay actividad Gold para mostrar.")
    st.stop()

mensual = (
    actividad.groupby("mes", as_index=False)["cantidad_sismos"]
    .sum()
    .sort_values("mes")
)
mes_pico = mensual.loc[mensual["cantidad_sismos"].idxmax()]
fig_mensual = px.bar(
    mensual,
    x="mes",
    y="cantidad_sismos",
    title="Sismos por mes",
    labels={"mes": "Mes", "cantidad_sismos": "Cantidad de sismos"},
)
st.plotly_chart(fig_mensual, use_container_width=True)

zonas = (
    actividad.groupby("zona_reportada", as_index=False)["cantidad_sismos"]
    .sum()
    .nlargest(15, "cantidad_sismos")
    .sort_values("cantidad_sismos")
)
zona_pico = zonas.iloc[-1]
fig_zonas = px.bar(
    zonas,
    x="cantidad_sismos",
    y="zona_reportada",
    orientation="h",
    title="15 zonas con más actividad",
    labels={
        "zona_reportada": "Zona reportada por USGS",
        "cantidad_sismos": "Cantidad de sismos",
    },
)
st.plotly_chart(fig_zonas, use_container_width=True)

st.success(
    f"Conclusión: el mes con más eventos fue "
    f"{mes_pico['mes']:%B %Y} ({int(mes_pico['cantidad_sismos']):,} sismos). "
    f"La zona más activa fue {zona_pico['zona_reportada']} "
    f"({int(zona_pico['cantidad_sismos']):,} sismos)."
)
