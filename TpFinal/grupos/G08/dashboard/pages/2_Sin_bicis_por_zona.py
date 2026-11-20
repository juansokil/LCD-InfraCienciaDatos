import numpy as np
import plotly.express as px
import streamlit as st

from comun import ESCALA_SATURACION, columna_zona, selector_red, tasa
from db import requiere_gold, run_query

st.title("Estaciones sin bicis por zona")
st.caption(
    "Qué proporción de los snapshots válidos encontró las estaciones sin bicicletas, "
    "por ciudad, barrio o comuna."
)
requiere_gold()

conteos = ["snapshots_observados", "snapshots_sin_bicis"]

# 1. Comparacion entre ciudades (todas las redes).
por_red = run_query("""
    SELECT
        d.red_nombre,
        sum(f.snapshots_validos)   AS snapshots_observados,
        sum(f.snapshots_sin_bicis) AS snapshots_sin_bicis
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_estacion d USING (network_id, station_id)
    GROUP BY d.red_nombre
""")
por_red["porcentaje_sin_bicis"] = tasa(
    por_red["snapshots_sin_bicis"], por_red["snapshots_observados"]
)
fig_redes = px.bar(
    por_red.sort_values("porcentaje_sin_bicis"),
    x="porcentaje_sin_bicis",
    y="red_nombre",
    orientation="h",
    hover_data=conteos,
    labels={
        "porcentaje_sin_bicis": "Snapshots sin bicis (%)",
        "red_nombre": "Red",
        "snapshots_observados": "Snapshots observados",
        "snapshots_sin_bicis": "Snapshots sin bicis",
    },
)
fig_redes.update_xaxes(range=[0, 100], ticksuffix="%")
fig_redes.update_layout(height=260)
st.subheader("Comparación entre ciudades")
st.plotly_chart(fig_redes, use_container_width=True)

# 2. Dentro de una red.
red, red_nombre, tiene_barrios = selector_red("red_saturacion_zona")
df = run_query("""
    SELECT
        d.ciudad, d.zona, d.zona_padre, d.zona_nivel,
        f.hora,
        sum(f.snapshots_validos)   AS snapshots_observados,
        sum(f.snapshots_sin_bicis) AS snapshots_sin_bicis
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_estacion d USING (network_id, station_id)
    WHERE f.network_id = :red
    GROUP BY d.ciudad, d.zona, d.zona_padre, d.zona_nivel, f.hora
""", {"red": red})
if df["snapshots_observados"].sum() == 0:
    st.info("Todavía no hay snapshots válidos para esta red.")
    st.stop()

df, nivel = columna_zona(df, tiene_barrios, "nivel_zona_saturacion")
if not tiene_barrios:
    st.info(
        f"{red_nombre} todavía no tiene capa de zonas (ver README → Zonas): "
        "se muestra la ciudad entera."
    )

por_zona = df.groupby("zona_grafico", as_index=False)[conteos].sum()
por_zona["porcentaje_sin_bicis"] = tasa(
    por_zona["snapshots_sin_bicis"], por_zona["snapshots_observados"]
)
por_zona = por_zona.sort_values("porcentaje_sin_bicis", ascending=True)

if tiene_barrios:
    fig_barras = px.bar(
        por_zona,
        x="porcentaje_sin_bicis",
        y="zona_grafico",
        orientation="h",
        hover_data=conteos,
        labels={
            "porcentaje_sin_bicis": "Snapshots sin bicis (%)",
            "zona_grafico": nivel,
            "snapshots_observados": "Snapshots observados",
            "snapshots_sin_bicis": "Snapshots sin bicis",
        },
        color="porcentaje_sin_bicis",
        color_continuous_scale=ESCALA_SATURACION,
        range_color=(0, 100),
    )
    fig_barras.update_xaxes(range=[0, 100], ticksuffix="%")
    fig_barras.update_yaxes(categoryorder="array", categoryarray=por_zona["zona_grafico"].tolist())
    fig_barras.update_layout(coloraxis_showscale=False,
                             height=max(420, min(900, 28 * len(por_zona))))
    st.subheader(f"Sin bicis por {nivel.lower()}")
    st.plotly_chart(fig_barras, use_container_width=True)

# Heatmap: cada celda recalcula la tasa con los conteos de esa zona y hora.
por_hora = df.groupby(["zona_grafico", "hora"], as_index=False)[conteos].sum()
por_hora["porcentaje_sin_bicis"] = tasa(
    por_hora["snapshots_sin_bicis"], por_hora["snapshots_observados"]
)
orden_zonas = por_zona.sort_values("porcentaje_sin_bicis", ascending=False)["zona_grafico"].tolist()


def a_matriz(columna):
    return (
        por_hora.pivot(index="zona_grafico", columns="hora", values=columna)
        .reindex(index=orden_zonas, columns=range(24))
    )


matriz = a_matriz("porcentaje_sin_bicis")
fig_heatmap = px.imshow(
    matriz,
    aspect="auto",
    color_continuous_scale=ESCALA_SATURACION,
    zmin=0,
    zmax=100,
    labels={"x": "Hora local", "y": nivel, "color": "Sin bicis (%)"},
)
# Hover con la muestra de cada celda: un 100% con 6 snapshots de un dia no
# pesa lo mismo que uno con cientos.
fig_heatmap.update_traces(
    hoverongaps=False,
    customdata=np.dstack([a_matriz("snapshots_observados").values,
                          a_matriz("snapshots_sin_bicis").values]),
    hovertemplate=(
        f"{nivel}: %{{y}}<br>Hora local: %{{x}}<br>Sin bicis: %{{z:.1f}}%<br>"
        "Snapshots sin bicis: %{customdata[1]:.0f} de %{customdata[0]:.0f}<extra></extra>"
    ),
)
fig_heatmap.update_layout(height=max(300, min(900, 28 * len(orden_zonas))))
fig_heatmap.update_xaxes(tickmode="linear", tick0=0, dtick=1, tickangle=-45)

st.subheader(f"Sin bicis por {nivel.lower()} y hora")
st.plotly_chart(fig_heatmap, use_container_width=True)
st.caption(
    "Las celdas sin color no tienen snapshots observados. Los porcentajes se calculan "
    "sobre los snapshots que efectivamente llegaron en cada zona y hora; el hover "
    "muestra cuántos son, porque con pocos snapshots el porcentaje es poco confiable."
)
