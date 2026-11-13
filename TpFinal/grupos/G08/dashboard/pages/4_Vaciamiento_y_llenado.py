import plotly.express as px
import streamlit as st

from db import run_query


st.title("Zonas que se vacían y se llenan")
st.caption(
    "Compara las estaciones sin bicicletas disponibles para retirar con las que "
    "no tienen anclajes libres para devolver."
)

sql_zonas = """
    SELECT
        network_id,
        ciudad,
        zona,
        zona_padre,
        zona_nivel,
        dia_semana,
        hora,
        COUNT(*) AS snapshots_observados,
        COUNT(*) FILTER (WHERE free_bikes = 0) AS snapshots_sin_bicis,
        COUNT(*) FILTER (WHERE empty_slots = 0) AS snapshots_sin_anclajes
    FROM gold.vw_citybikes_saturacion
    GROUP BY
        network_id,
        ciudad,
        zona,
        zona_padre,
        zona_nivel,
        dia_semana,
        hora
"""

df = run_query(sql_zonas)
if df.empty:
    st.info("Todavía no hay snapshots válidos para analizar.")
    st.stop()

redes = sorted(df["network_id"].dropna().unique())
red = st.selectbox("Red", redes, key="red_vaciado_llenado")
df_red = df[df["network_id"] == red].copy()

tipo_dia = st.selectbox(
    "Días incluidos",
    ["Todos", "Días hábiles", "Fin de semana"],
    key="tipo_dia_vaciado_llenado",
)
if tipo_dia == "Días hábiles":
    df_red = df_red[df_red["dia_semana"].between(1, 5)]
elif tipo_dia == "Fin de semana":
    df_red = df_red[df_red["dia_semana"].isin([6, 7])]

if df_red.empty:
    st.info("No hay snapshots para esta red y selección de días.")
    st.stop()

if red == "ecobici-buenos-aires":
    nivel = st.selectbox(
        "Desglosar CABA por",
        ["Barrio", "Comuna"],
        key="nivel_zona_vaciado_llenado",
    )
    if nivel == "Barrio":
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

conteos = [
    "snapshots_observados",
    "snapshots_sin_bicis",
    "snapshots_sin_anclajes",
]

# Comparación general por zona; se suman los conteos antes de calcular tasas.
por_zona = df_red.groupby("zona_grafico", as_index=False)[conteos].sum()
por_zona["pct_sin_bicis"] = (
    100 * por_zona["snapshots_sin_bicis"] / por_zona["snapshots_observados"]
)
por_zona["pct_sin_anclajes"] = (
    100 * por_zona["snapshots_sin_anclajes"] / por_zona["snapshots_observados"]
)
por_zona["max_pct"] = por_zona[["pct_sin_bicis", "pct_sin_anclajes"]].max(axis=1)
orden_zonas = por_zona.sort_values("max_pct", ascending=True)["zona_grafico"].tolist()

por_zona_largo = por_zona.melt(
    id_vars=["zona_grafico", *conteos],
    value_vars=["pct_sin_bicis", "pct_sin_anclajes"],
    var_name="condicion",
    value_name="porcentaje",
)
por_zona_largo["condicion"] = por_zona_largo["condicion"].map({
    "pct_sin_bicis": "Sin bicicletas",
    "pct_sin_anclajes": "Sin anclajes libres",
})

fig_comparacion = px.bar(
    por_zona_largo,
    x="porcentaje",
    y="zona_grafico",
    color="condicion",
    barmode="group",
    orientation="h",
    hover_data=conteos,
    labels={
        "porcentaje": "Snapshots de la condición (%)",
        "zona_grafico": nivel,
        "condicion": "Situación",
        "snapshots_observados": "Snapshots observados",
        "snapshots_sin_bicis": "Snapshots sin bicicletas",
        "snapshots_sin_anclajes": "Snapshots sin anclajes libres",
    },
    color_discrete_map={
        "Sin bicicletas": "#d62828",
        "Sin anclajes libres": "#277da1",
    },
)
fig_comparacion.update_xaxes(range=[0, 100], ticksuffix="%")
fig_comparacion.update_yaxes(categoryorder="array", categoryarray=orden_zonas)
fig_comparacion.update_layout(height=max(420, min(900, 30 * len(orden_zonas))))

st.subheader(f"Las dos caras de la saturación por {nivel.lower()}")
st.plotly_chart(fig_comparacion, use_container_width=True)

# Heatmaps por hora; ambos usan los mismos snapshots observados como denominador.
por_hora = df_red.groupby(["zona_grafico", "hora"], as_index=False)[conteos].sum()
por_hora["pct_sin_bicis"] = (
    100 * por_hora["snapshots_sin_bicis"] / por_hora["snapshots_observados"]
)
por_hora["pct_sin_anclajes"] = (
    100 * por_hora["snapshots_sin_anclajes"] / por_hora["snapshots_observados"]
)


def crear_heatmap(columna, titulo, escala):
    matriz = (
        por_hora.pivot(
            index="zona_grafico", columns="hora", values=columna
        )
        .reindex(index=orden_zonas, columns=range(24))
    )
    figura = px.imshow(
        matriz,
        aspect="auto",
        color_continuous_scale=escala,
        zmin=0,
        zmax=100,
        labels={
            "x": "Hora local",
            "y": nivel,
            "color": "Snapshots (%)",
        },
    )
    figura.update_xaxes(tickmode="linear", tick0=0, dtick=2, tickangle=-45)
    figura.update_layout(title=titulo, height=max(420, min(900, 30 * len(orden_zonas))))
    return figura


st.plotly_chart(
    crear_heatmap(
        "pct_sin_bicis",
        "Sin bicicletas para retirar",
        [[0.0, "#263238"], [0.5, "#f4a261"], [1.0, "#d62828"]],
    ),
    use_container_width=True,
)
st.plotly_chart(
    crear_heatmap(
        "pct_sin_anclajes",
        "Sin anclajes para devolver",
        [[0.0, "#263238"], [0.5, "#90be6d"], [1.0, "#277da1"]],
    ),
    use_container_width=True,
)

st.caption(
    "Las dos tasas usan como denominador los snapshots válidos observados en cada zona y hora. "
    "Una estación puede contar en ambas condiciones si simultáneamente tiene cero bicicletas "
    "y cero anclajes libres. Los horarios pueden sugerir patrones de movimiento; las zonas "
    "todavía no están clasificadas formalmente como residenciales o de oficinas."
)
