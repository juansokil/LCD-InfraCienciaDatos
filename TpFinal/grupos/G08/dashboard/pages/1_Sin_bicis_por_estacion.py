import plotly.express as px
import streamlit as st

from comun import DIAS, ESCALA_SATURACION, selector_red, tasa
from db import requiere_gold, run_query

st.title("Saturación por estación")
st.caption(
    "Porcentaje de los snapshots válidos en que la estación no tenía bicicletas "
    "para retirar (`free_bikes = 0`), por día de la semana y hora local."
)
requiere_gold()

red, red_nombre, _ = selector_red("red_saturacion_estaciones")

# Grano estacion x dia de semana x hora: conteos, no porcentajes, para poder
# sumar y recien despues dividir.
df = run_query("""
    SELECT
        f.station_id,
        d.station_name,
        df.dia_semana,
        f.hora,
        sum(f.snapshots_validos)   AS snapshots_observados,
        sum(f.snapshots_sin_bicis) AS snapshots_saturados
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_estacion d USING (network_id, station_id)
    JOIN gold.dim_fecha df USING (fecha)
    WHERE f.network_id = :red
    GROUP BY f.station_id, d.station_name, df.dia_semana, f.hora
    HAVING sum(f.snapshots_validos) > 0
""", {"red": red})
if df.empty:
    st.info("Todavía no hay snapshots válidos para esta red.")
    st.stop()

df["estacion"] = df["station_name"].fillna(df["station_id"])
conteos = ["snapshots_observados", "snapshots_saturados"]


def heatmap_dia_hora(datos, titulo):
    """Mapa de calor dia x hora con la tasa recalculada en cada celda."""
    celdas = datos.groupby(["dia_semana", "hora"], as_index=False)[conteos].sum()
    celdas["porcentaje"] = tasa(celdas["snapshots_saturados"], celdas["snapshots_observados"])
    matriz = (
        celdas.pivot(index="dia_semana", columns="hora", values="porcentaje")
        .reindex(index=range(1, 8), columns=range(24))
    )
    matriz.index = [DIAS[d] for d in matriz.index]
    figura = px.imshow(
        matriz,
        aspect="auto",
        text_auto=".0f",
        color_continuous_scale=ESCALA_SATURACION,
        zmin=0,
        zmax=100,
        labels={"x": "Hora local", "y": "Día de la semana", "color": "Saturación (%)"},
    )
    figura.update_xaxes(tickmode="linear", dtick=1)
    figura.update_layout(title=titulo)
    return figura


# 1. Cuando: toda la red.
st.subheader(f"¿En qué días y horarios se saturan las estaciones de {red_nombre}?")
st.plotly_chart(heatmap_dia_hora(df, "Toda la red"), use_container_width=True)

# 2. Que estaciones: ranking con un minimo de observaciones, para que una
# estacion nueva con un par de snapshots vacios no aparezca con 100%.
por_estacion = df.groupby(["station_id", "estacion"], as_index=False)[conteos].sum()
por_estacion["porcentaje"] = tasa(
    por_estacion["snapshots_saturados"], por_estacion["snapshots_observados"]
)
tope = int(por_estacion["snapshots_observados"].max())
minimo = st.slider(
    "Mínimo de snapshots observados por estación (12 ≈ 1 hora)",
    min_value=1,
    max_value=max(tope, 2),
    value=min(72, tope),
    key="minimo_snapshots_ranking",
)
elegibles = por_estacion[por_estacion["snapshots_observados"] >= minimo]
top10 = elegibles.nlargest(10, "porcentaje").sort_values("porcentaje")

st.subheader("Estaciones con mayor porcentaje de saturación")
if top10.empty:
    st.info("Ninguna estación alcanza ese mínimo de snapshots.")
else:
    fig_estaciones = px.bar(
        top10,
        x="porcentaje",
        y="estacion",
        orientation="h",
        hover_data=["station_id", *conteos],
        labels={
            "porcentaje": "Snapshots saturados (%)",
            "estacion": "Estación",
            "station_id": "ID",
            "snapshots_observados": "Snapshots observados",
            "snapshots_saturados": "Snapshots saturados",
        },
    )
    fig_estaciones.update_xaxes(range=[0, 100], ticksuffix="%")
    st.plotly_chart(fig_estaciones, use_container_width=True)
    st.caption(
        f"{len(elegibles)} de {len(por_estacion)} estaciones tienen al menos "
        f"{minimo} snapshots observados."
    )

# 3. Cuando, para una estacion puntual (por defecto, la mas saturada).
st.subheader("¿Cuándo se satura una estación en particular?")
opciones = (
    elegibles.sort_values("porcentaje", ascending=False)
    if not elegibles.empty else por_estacion.sort_values("estacion")
)
por_etiqueta = {
    f"{fila.estacion} · {fila.station_id}": fila.station_id
    for fila in opciones.itertuples()
}
etiqueta = st.selectbox("Estación", list(por_etiqueta), key="estacion_detalle")
st.plotly_chart(
    heatmap_dia_hora(df[df["station_id"] == por_etiqueta[etiqueta]], etiqueta),
    use_container_width=True,
)
st.caption("Las celdas vacías no tienen snapshots observados.")
