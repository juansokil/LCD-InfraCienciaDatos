import numpy as np
import plotly.express as px
import streamlit as st

from comun import columna_zona, selector_red, selector_tipo_dia, tasa
from db import requiere_gold, run_query

st.title("Zonas que se vacían y se llenan")
st.caption(
    "Las dos caras de la saturación: estaciones sin bicicletas para retirar "
    "(`free_bikes = 0`) y estaciones sin anclajes libres para devolver (`empty_slots = 0`)."
)
requiere_gold()

red, red_nombre, tiene_barrios = selector_red("red_vaciado_llenado")
tipos_dia = selector_tipo_dia("tipo_dia_vaciado_llenado")

df = run_query("""
    SELECT
        d.ciudad, d.zona, d.zona_padre, d.zona_nivel,
        f.hora,
        sum(f.snapshots_validos)      AS snapshots_observados,
        sum(f.snapshots_sin_bicis)    AS snapshots_sin_bicis,
        sum(f.snapshots_sin_anclajes) AS snapshots_sin_anclajes,
        -- Ocupacion ponderada por snapshots: se guardan numerador y base para
        -- poder reagregar por zona y hora sin promediar promedios.
        sum(f.ocupacion_promedio * f.snapshots_validos)
            FILTER (WHERE f.ocupacion_promedio IS NOT NULL) AS ocupacion_ponderada,
        sum(f.snapshots_validos)
            FILTER (WHERE f.ocupacion_promedio IS NOT NULL) AS snapshots_con_ocupacion
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_estacion d USING (network_id, station_id)
    JOIN gold.dim_fecha df USING (fecha)
    WHERE f.network_id = :red
      AND df.tipo_dia = ANY(CAST(:tipos AS text[]))
    GROUP BY d.ciudad, d.zona, d.zona_padre, d.zona_nivel, f.hora
""", {"red": red, "tipos": tipos_dia})
if df.empty or df["snapshots_observados"].sum() == 0:
    st.info("No hay snapshots válidos para esta red y selección de días.")
    st.stop()

df, nivel = columna_zona(df, tiene_barrios, "nivel_zona_vaciado_llenado")
conteos = ["snapshots_observados", "snapshots_sin_bicis", "snapshots_sin_anclajes"]
ocupacion = ["ocupacion_ponderada", "snapshots_con_ocupacion"]


def ocupacion_pct(datos):
    """% de anclajes operativos con bici, ponderado por snapshots."""
    return tasa(datos["ocupacion_ponderada"], datos["snapshots_con_ocupacion"])


# Comparacion general por zona: se suman los conteos antes de calcular tasas.
por_zona = df.groupby("zona_grafico", as_index=False)[conteos + ocupacion].sum()
por_zona["pct_sin_bicis"] = tasa(por_zona["snapshots_sin_bicis"], por_zona["snapshots_observados"])
por_zona["pct_sin_anclajes"] = tasa(por_zona["snapshots_sin_anclajes"], por_zona["snapshots_observados"])
por_zona["ocupacion"] = ocupacion_pct(por_zona)
# Plotly dibuja el primer elemento abajo: ocupacion descendente deja arriba las
# zonas mas vacias, en las barras y (invertido) en el heatmap.
# Zonas sin ocupacion (NaN) van primero para que queden abajo de todo.
orden_zonas = por_zona.sort_values(
    "ocupacion", ascending=False, na_position="first"
)["zona_grafico"].tolist()

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
        "porcentaje": "Snapshots en esa condición (%)",
        "zona_grafico": nivel,
        "condicion": "Situación",
        "snapshots_observados": "Snapshots observados",
        "snapshots_sin_bicis": "Snapshots sin bicicletas",
        "snapshots_sin_anclajes": "Snapshots sin anclajes libres",
    },
    color_discrete_map={"Sin bicicletas": "#d62828", "Sin anclajes libres": "#277da1"},
)
fig_comparacion.update_xaxes(rangemode="tozero", ticksuffix="%")
fig_comparacion.update_yaxes(categoryorder="array", categoryarray=orden_zonas)
fig_comparacion.update_layout(height=max(300, min(900, 30 * len(orden_zonas))))
st.subheader(f"Las dos caras de la saturación por {nivel.lower()}")
st.plotly_chart(fig_comparacion, use_container_width=True)
st.caption("Ordenado por ocupación promedio: arriba las zonas con menos bicis.")

# Ocupacion por hora: muestra el ida y vuelta (a la manana se vacian unas zonas
# y se llenan otras; a la tarde, al reves). A diferencia de contar estaciones
# vacias o llenas, ve la tendencia aunque la zona no llegue a los extremos.
por_hora = df.groupby(["zona_grafico", "hora"], as_index=False)[conteos + ocupacion].sum()
por_hora["ocupacion"] = ocupacion_pct(por_hora)


def a_matriz(columna):
    return (
        por_hora.pivot(index="zona_grafico", columns="hora", values=columna)
        .reindex(index=orden_zonas[::-1], columns=range(24))
    )


matriz = a_matriz("ocupacion")
fig_ocupacion = px.imshow(
    matriz,
    aspect="auto",
    color_continuous_scale=[[0.0, "#d62828"], [0.5, "#f1f1f1"], [1.0, "#277da1"]],
    zmin=0,
    zmax=100,
    labels={"x": "Hora local", "y": nivel, "color": "Ocupación (%)"},
)
# Hover con la muestra de cada celda, igual que en las paginas 1 y 2.
fig_ocupacion.update_traces(
    hoverongaps=False,
    customdata=np.dstack([a_matriz(c).values for c in conteos]),
    hovertemplate=(
        f"{nivel}: %{{y}}<br>Hora local: %{{x}}<br>Ocupación: %{{z:.0f}}%<br>"
        "Sin bicis: %{customdata[1]:.0f} de %{customdata[0]:.0f} snapshots<br>"
        "Sin anclajes: %{customdata[2]:.0f} de %{customdata[0]:.0f} snapshots<extra></extra>"
    ),
)
fig_ocupacion.update_xaxes(tickmode="linear", tick0=0, dtick=1, tickangle=-45)
fig_ocupacion.update_layout(height=max(300, min(900, 30 * len(orden_zonas))))
st.subheader("¿En qué horario se vacía o se llena cada zona?")
st.plotly_chart(fig_ocupacion, use_container_width=True)
st.caption(
    "Ocupación = % de los anclajes operativos (bicis + anclajes libres) que tiene bici, "
    "promedio de los snapshots de esa zona y hora. Rojo: la zona está vacía (típico de "
    "barrios residenciales a la mañana, cuando salen las bicis). Azul: está llena (típico "
    "de zonas de oficinas). Blanco: mitad y mitad. Las celdas vacías no tienen snapshots. "
    "El hover muestra además cuántos snapshots estaban sin bicis o sin anclajes."
)
