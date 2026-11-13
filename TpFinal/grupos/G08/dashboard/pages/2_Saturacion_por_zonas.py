import plotly.express as px
import streamlit as st

from db import run_query


st.title("Saturación por zona")
st.caption(
    "Compara qué proporción de los snapshots válidos encontró las estaciones sin bicicletas."
)

sql_zonas = """
    SELECT
        network_id,
        ciudad,
        zona,
        zona_padre,
        zona_nivel,
        hora,
        COUNT(*) AS snapshots_observados,
        COUNT(*) FILTER (WHERE saturada) AS snapshots_saturados
    FROM gold.vw_citybikes_saturacion
    GROUP BY
        network_id,
        ciudad,
        zona,
        zona_padre,
        zona_nivel,
        hora
"""

df = run_query(sql_zonas)
if df.empty:
    st.info("Todavía no hay datos de saturación por zona.")
    st.stop()

redes = sorted(df["network_id"].dropna().unique())
red = st.selectbox("Red", redes, key="red_saturacion_zona")
df_red = df[df["network_id"] == red].copy()

if red == "ecobici-buenos-aires":
    nivel = st.selectbox(
        "Desglosar CABA por",
        ["Barrio", "Comuna"],
        key="nivel_zona_caba",
    )
    if nivel == "Barrio":
        # Las estaciones fuera de los polígonos quedan en la ciudad como fallback.
        df_red["zona_grafico"] = df_red["zona"].where(
            df_red["zona_nivel"] == "barrio", "Sin barrio asignado"
        ).fillna("Sin barrio asignado")
    else:
        df_red["zona_grafico"] = df_red["zona_padre"].where(
            df_red["zona_nivel"] == "barrio", "Sin comuna asignada"
        ).fillna("Sin comuna asignada")
else:
    nivel = "Ciudad"
    df_red["zona_grafico"] = (
        df_red["ciudad"].fillna(df_red["zona"]).fillna("Sin ciudad asignada")
    )

conteos = ["snapshots_observados", "snapshots_saturados"]

# Barras: se suman numeradores y denominadores antes de calcular el porcentaje.
por_zona = df_red.groupby("zona_grafico", as_index=False)[conteos].sum()
por_zona["porcentaje_saturacion"] = (
    100 * por_zona["snapshots_saturados"] / por_zona["snapshots_observados"]
)
por_zona = por_zona.sort_values("porcentaje_saturacion", ascending=True)

fig_barras = px.bar(
    por_zona,
    x="porcentaje_saturacion",
    y="zona_grafico",
    orientation="h",
    hover_data=conteos,
    labels={
        "porcentaje_saturacion": "Snapshots saturados (%)",
        "zona_grafico": nivel,
        "snapshots_observados": "Snapshots observados",
        "snapshots_saturados": "Snapshots saturados",
    },
    color="porcentaje_saturacion",
    color_continuous_scale=[[0.0, "#2a9d8f"], [0.5, "#f4a261"], [1.0, "#d62828"]],
    range_color=(0, 100),
)
fig_barras.update_xaxes(range=[0, 100], ticksuffix="%")
fig_barras.update_yaxes(
    categoryorder="array", categoryarray=por_zona["zona_grafico"].tolist()
)
fig_barras.update_layout(
    coloraxis_showscale=False,
    height=max(420, min(900, 28 * len(por_zona))),
)

st.subheader(f"Saturación por {nivel.lower()}")
st.plotly_chart(fig_barras, use_container_width=True)

# Heatmap: cada celda vuelve a calcular la tasa con los conteos de esa zona y hora.
por_hora = df_red.groupby(["zona_grafico", "hora"], as_index=False)[conteos].sum()
por_hora["porcentaje_saturacion"] = (
    100 * por_hora["snapshots_saturados"] / por_hora["snapshots_observados"]
)
orden_zonas = por_zona.sort_values(
    "porcentaje_saturacion", ascending=False
)["zona_grafico"].tolist()
matriz = (
    por_hora.pivot(
        index="zona_grafico", columns="hora", values="porcentaje_saturacion"
    )
    .reindex(index=orden_zonas, columns=range(24))
)

fig_heatmap = px.imshow(
    matriz,
    aspect="auto",
    color_continuous_scale=[[0.0, "#2a9d8f"], [0.5, "#f4a261"], [1.0, "#d62828"]],
    zmin=0,
    zmax=100,
    labels={
        "x": "Hora local",
        "y": nivel,
        "color": "Saturación (%)",
    },
)
fig_heatmap.update_layout(height=max(420, min(900, 28 * len(orden_zonas))))
fig_heatmap.update_xaxes(tickmode="linear", tick0=0, dtick=1, tickangle=-45,)

st.subheader(f"Saturación por {nivel.lower()} y hora")
st.plotly_chart(fig_heatmap, use_container_width=True)

st.caption(
    "Las celdas sin color no tienen snapshots observados. "
    "Los porcentajes se calculan sobre los snapshots disponibles en cada zona y hora."
)
